import time
from datetime import datetime, timezone

import requests
from django.core.management.base import BaseCommand, CommandError

from leaguehub.models import Season, Transaction


class Command(BaseCommand):
    help = "Sync add/drop/trade transactions for a season from Yahoo"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--access-token", type=str, required=True)
        parser.add_argument("--full-league-key", type=str, help="Override league key, e.g. 449.l.46828")
        parser.add_argument("--count", type=int, default=100, help="Max transactions to fetch (default 100)")
        parser.add_argument("--debug", action="store_true", help="Print raw Yahoo response and exit")

    def handle(self, *args, **options):
        season_year = options["season"]
        access_token = options["access_token"]

        season = Season.objects.filter(year=season_year).first()
        if not season:
            raise CommandError(f"Season {season_year} not found.")

        if options.get("full_league_key"):
            full_league_key = options["full_league_key"]
        else:
            if not season.yahoo_game_key or not season.yahoo_league_key:
                raise CommandError("Season keys are blank. Set them or pass --full-league-key.")
            full_league_key = f"{season.yahoo_game_key}.l.{season.yahoo_league_key}"

        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        def get(url, **params):
            for attempt in range(3):
                r = requests.get(url, headers=headers, params={"format": "json", **params}, timeout=30)
                if r.status_code == 429 or (r.ok and not r.text.strip()):
                    wait = 10 * (attempt + 1)
                    self.stdout.write(f"  Rate limited, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                if not r.ok:
                    raise CommandError(f"Yahoo API error {r.status_code} for {url}\n{r.text[:500]}")
                try:
                    return r.json()
                except Exception:
                    raise CommandError(f"Non-JSON response for {url}:\n{r.text[:500]}")
            raise CommandError("Rate-limited after 3 attempts. Token may have expired.")

        base = "https://fantasysports.yahooapis.com/fantasy/v2"
        count = options["count"]
        url = f"{base}/league/{full_league_key}/transactions;types=add,drop,trade;count={count}"
        payload = get(url)

        if options.get("debug"):
            import json
            self.stdout.write(json.dumps(payload, indent=2)[:5000])
            return

        league_list = payload.get("fantasy_content", {}).get("league", [])
        if len(league_list) < 2:
            self.stdout.write("No transactions found in response.")
            return

        raw_txns = league_list[1].get("transactions", {})
        txn_count = int(raw_txns.get("count", 0))
        self.stdout.write(f"Found {txn_count} transaction(s) from Yahoo.")

        created = 0
        skipped = 0

        for i in range(txn_count):
            entry = raw_txns.get(str(i), {}).get("transaction", [])
            if not entry or not isinstance(entry, list) or not entry[0]:
                continue

            meta = entry[0] if isinstance(entry[0], dict) else {}
            yahoo_id = str(meta.get("transaction_id", ""))
            txn_type_raw = meta.get("type", "")
            timestamp = meta.get("timestamp")

            # Map Yahoo types to our types
            if txn_type_raw in ("add", "add/drop"):
                base_type = Transaction.TYPE_ADD
            elif txn_type_raw == "drop":
                base_type = Transaction.TYPE_DROP
            elif txn_type_raw == "trade":
                base_type = Transaction.TYPE_TRADE
            else:
                continue

            occurred_at = (
                datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                if timestamp else None
            )
            if not occurred_at:
                continue

            players_block = entry[1].get("players", {}) if len(entry) > 1 else {}
            player_count = int(players_block.get("count", 0))

            for pi in range(player_count):
                player_entry = players_block.get(str(pi), {}).get("player", [])
                if not player_entry:
                    continue

                # Player metadata is a list of dicts
                player_meta = {}
                for part in player_entry:
                    if isinstance(part, list):
                        for item in part:
                            if isinstance(item, dict):
                                player_meta.update(item)
                    elif isinstance(part, dict) and "transaction_data" not in part:
                        player_meta.update(part)

                tx_data = {}
                for part in player_entry:
                    if isinstance(part, dict) and "transaction_data" in part:
                        raw = part["transaction_data"]
                        if isinstance(raw, list):
                            for d in raw:
                                if isinstance(d, dict):
                                    tx_data.update(d)
                        elif isinstance(raw, dict):
                            tx_data = raw

                player_name = player_meta.get("full_name", player_meta.get("name", {}).get("full", "Unknown"))
                move_type = tx_data.get("type", "")

                # Determine per-player type and team
                if move_type == "add":
                    this_type = Transaction.TYPE_ADD
                    team_name = tx_data.get("destination_team_name", "")
                    source = tx_data.get("source_type", "")
                    detail = f"from {source}" if source else ""
                elif move_type == "drop":
                    this_type = Transaction.TYPE_DROP
                    team_name = tx_data.get("source_team_name", "")
                    detail = ""
                elif move_type == "trade":
                    this_type = Transaction.TYPE_TRADE
                    team_name = tx_data.get("destination_team_name", "")
                    from_team = tx_data.get("source_team_name", "")
                    detail = f"from {from_team}" if from_team else ""
                else:
                    # add/drop combo — treat by move_type fallback
                    this_type = base_type
                    team_name = tx_data.get("destination_team_name", tx_data.get("source_team_name", ""))
                    detail = ""

                # Build a unique ID per player movement within the transaction
                unique_id = f"{yahoo_id}_{pi}" if yahoo_id else ""

                if unique_id and Transaction.objects.filter(yahoo_transaction_id=unique_id, season=season).exists():
                    skipped += 1
                    continue

                Transaction.objects.create(
                    season=season,
                    type=this_type,
                    team_name=team_name,
                    player_name=player_name,
                    detail=detail,
                    occurred_at=occurred_at,
                    yahoo_transaction_id=unique_id,
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {created} transaction(s) created, {skipped} already existed."
        ))
