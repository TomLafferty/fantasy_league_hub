import requests
from django.core.management.base import BaseCommand, CommandError

from leaguehub.models import Season
from leaguehub.services import sync_matchups_from_yahoo


class Command(BaseCommand):
    help = "Sync all weekly matchup scores for a season from Yahoo"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--access-token", type=str, required=True)
        parser.add_argument("--full-league-key", type=str, help="Override league key, e.g. 449.l.46828")
        parser.add_argument("--weeks", type=str, help="Comma-separated weeks to sync, e.g. '1,2,3'. Defaults to 1 through end_week.")
        parser.add_argument("--debug-week", type=int, help="Print raw scoreboard JSON for this week and exit.")

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
            r = requests.get(url, headers=headers, params={"format": "json", **params}, timeout=30)
            if not r.ok:
                raise CommandError(f"Yahoo API error {r.status_code} for {url}\n{r.text}")
            return r.json()

        base = "https://fantasysports.yahooapis.com/fantasy/v2"

        # Determine weeks
        if options.get("weeks"):
            weeks = [int(w.strip()) for w in options["weeks"].split(",")]
        else:
            league_payload = get(f"{base}/league/{full_league_key}")
            league_meta = league_payload.get("fantasy_content", {}).get("league", [{}])[0]
            end_week = int(league_meta.get("end_week", 16))
            weeks = list(range(1, end_week + 1))

        if options.get("debug_week"):
            import json
            w = options["debug_week"]
            payload = get(f"{base}/league/{full_league_key}/scoreboard;week={w}")
            league_list = payload.get("fantasy_content", {}).get("league", [])
            self.stdout.write(f"league_list length: {len(league_list)}")
            resources = league_list[1] if len(league_list) > 1 else {}
            self.stdout.write(f"resources keys: {list(resources.keys())}")
            scoreboard = resources.get("scoreboard", {})
            self.stdout.write(f"scoreboard type: {type(scoreboard).__name__}, keys: {list(scoreboard.keys()) if isinstance(scoreboard, dict) else 'n/a'}")
            matchups = scoreboard.get("matchups", {}) if isinstance(scoreboard, dict) else {}
            self.stdout.write(f"matchups type: {type(matchups).__name__}, keys: {list(matchups.keys()) if isinstance(matchups, dict) else 'n/a'}")
            # Show first matchup entry raw
            first_key = next((k for k in matchups if k != "count"), None) if isinstance(matchups, dict) else None
            if first_key:
                self.stdout.write(f"\nFirst matchup entry (key={first_key}):")
                self.stdout.write(json.dumps(matchups[first_key], indent=2)[:3000])
            else:
                self.stdout.write("\nFull resources dump:")
                self.stdout.write(json.dumps(resources, indent=2)[:4000])
            return

        total = 0
        for week in weeks:
            payload = get(f"{base}/league/{full_league_key}/scoreboard;week={week}")
            n = sync_matchups_from_yahoo(season, week, payload)
            self.stdout.write(f"  Week {week}: {n} matchup(s) synced")
            total += n

        self.stdout.write(self.style.SUCCESS(f"\nDone. {total} matchup(s) stored for {season.year}."))
