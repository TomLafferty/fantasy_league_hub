"""
Sync a Sleeper dynasty league into the DB.

Usage:
    python manage.py sync_sleeper --league-id 1313580977724850176 --season 2026 --current
    python manage.py sync_sleeper --league-id 1313580977724850176 --season 2026 --sync-players
    python manage.py sync_sleeper --league-id 1313580977724850176 --season 2026 --mark-champion
    python manage.py sync_sleeper --league-id 1313580977724850176 --season 2026 --historical
"""

import time
import requests

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import datetime

from leaguehub.models import (
    ManagerProfile,
    SleeperLeague,
    SleeperRoster,
    SleeperPlayer,
    SleeperMatchup,
    SleeperTransaction,
    SleeperTradedPick,
    SleeperDraftPick,
    SleeperChampion,
)

BASE_URL = "https://api.sleeper.app/v1"
SLEEP_BETWEEN = 0.3
BULK_BATCH = 500


def _get(path, debug=False):
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if debug:
            import json
            print(json.dumps(data[:2] if isinstance(data, list) else data, indent=2, default=str))
        return data
    except Exception:
        return None


def _pct(done, total):
    return f"{int(done / total * 100)}%" if total else "—"


class Command(BaseCommand):
    help = "Sync a Sleeper dynasty league from the public Sleeper API"

    def add_arguments(self, parser):
        parser.add_argument("--league-id", required=True)
        parser.add_argument("--season", required=True, type=int)
        parser.add_argument("--current", action="store_true", help="Mark this league as is_current")
        parser.add_argument("--sync-players", action="store_true", help="Re-fetch all NFL players (~4 MB, slow)")
        parser.add_argument("--mark-champion", action="store_true", help="Create SleeperChampion for rank-1 roster")
        parser.add_argument("--historical", action="store_true", help="Walk previous_league_id chain recursively")
        parser.add_argument("--debug", action="store_true", help="Print raw API JSON and exit without writing")

    def handle(self, *args, **options):
        self._sync(
            league_id=options["league_id"],
            season=options["season"],
            is_current=options["current"],
            sync_players=options["sync_players"],
            mark_champion=options["mark_champion"],
            historical=options["historical"],
            debug=options["debug"],
        )

    def _sync(self, league_id, season, is_current, sync_players, mark_champion, historical, debug):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Syncing league {league_id} (season {season}) ==="))

        # ── 1. Players (optional) ─────────────────────────────────────────────
        if sync_players:
            self.stdout.write("  [1/9] Players — downloading from Sleeper API (~4 MB)...")
            players_data = _get("/players/nfl", debug=debug)
            if debug:
                return
            if players_data:
                objs = []
                for sleeper_id, p in players_data.items():
                    if not p.get("full_name") and not p.get("first_name"):
                        continue
                    objs.append(SleeperPlayer(
                        sleeper_id=sleeper_id,
                        full_name=p.get("full_name") or "",
                        first_name=p.get("first_name") or "",
                        last_name=p.get("last_name") or "",
                        position=(p.get("position") or "")[:10],
                        nfl_team=(p.get("team") or "")[:10],
                        status=(p.get("status") or "")[:50],
                    ))
                total = len(objs)
                self.stdout.write(f"  [1/9] Players — inserting {total:,} players in batches of {BULK_BATCH}...")
                for i in range(0, total, BULK_BATCH):
                    batch = objs[i:i + BULK_BATCH]
                    SleeperPlayer.objects.bulk_create(
                        batch,
                        update_conflicts=True,
                        unique_fields=["sleeper_id"],
                        update_fields=["full_name", "first_name", "last_name", "position", "nfl_team", "status", "updated_at"],
                    )
                    done = min(i + BULK_BATCH, total)
                    self.stdout.write(f"         {done:,}/{total:,} ({_pct(done, total)})")
                self.stdout.write(self.style.SUCCESS(f"  [1/9] Players — done ({total:,} upserted)"))
            time.sleep(SLEEP_BETWEEN)
        else:
            self.stdout.write("  [1/9] Players — skipped (use --sync-players to refresh)")

        # ── 2. League metadata ────────────────────────────────────────────────
        self.stdout.write("  [2/9] League metadata...")
        meta = _get(f"/league/{league_id}", debug=debug)
        if debug:
            return
        if not meta:
            raise CommandError(f"Could not fetch league {league_id}")

        league, _ = SleeperLeague.objects.update_or_create(
            league_id=league_id,
            defaults={
                "season_year": season,
                "name": meta.get("name", ""),
                "status": meta.get("status", ""),
                "previous_league_id": meta.get("previous_league_id") or "",
                "total_rosters": meta.get("total_rosters", 10),
                "is_current": is_current,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"  [2/9] League — {league.name} (status: {league.status})"))
        time.sleep(SLEEP_BETWEEN)

        # ── 3. Users ──────────────────────────────────────────────────────────
        self.stdout.write("  [3/9] Users...")
        users_data = _get(f"/league/{league_id}/users") or []
        user_display = {u["user_id"]: u.get("display_name", "") for u in users_data}
        user_avatar = {u["user_id"]: u.get("avatar", "") for u in users_data}
        self.stdout.write(self.style.SUCCESS(f"  [3/9] Users — {len(users_data)} found"))
        time.sleep(SLEEP_BETWEEN)

        # ── 4. Rosters ────────────────────────────────────────────────────────
        self.stdout.write("  [4/9] Rosters...")
        rosters_data = _get(f"/league/{league_id}/rosters") or []
        manager_map = {m.sleeper_user_id: m for m in ManagerProfile.objects.exclude(sleeper_user_id="")}
        roster_objs = []
        for i, r in enumerate(rosters_data, 1):
            owner_id = r.get("owner_id") or ""
            settings = r.get("settings") or {}
            roster, _ = SleeperRoster.objects.update_or_create(
                league=league,
                roster_id=r["roster_id"],
                defaults={
                    "owner_id": owner_id,
                    "manager": manager_map.get(owner_id),
                    "team_name": user_display.get(owner_id, ""),
                    "avatar_id": user_avatar.get(owner_id, ""),
                    "wins": settings.get("wins", 0),
                    "losses": settings.get("losses", 0),
                    "ties": settings.get("ties", 0),
                    "points_for": round(
                        (settings.get("fpts", 0) or 0) + (settings.get("fpts_decimal", 0) or 0) / 100, 2
                    ),
                    "points_against": round(
                        (settings.get("fpts_against", 0) or 0) + (settings.get("fpts_against_decimal", 0) or 0) / 100, 2
                    ),
                    "players": r.get("players") or [],
                    "taxi_players": r.get("taxi") or [],
                    "reserve_players": r.get("reserve") or [],
                },
            )
            roster_objs.append(roster)
            self.stdout.write(f"         Roster {i}/{len(rosters_data)} ({_pct(i, len(rosters_data))}) — {user_display.get(owner_id) or owner_id or 'unknown'}")
        time.sleep(SLEEP_BETWEEN)

        # ── 5. Rank computation ───────────────────────────────────────────────
        sorted_rosters = sorted(roster_objs, key=lambda r: (-r.wins, -float(r.points_for)))
        for rank, r in enumerate(sorted_rosters, 1):
            SleeperRoster.objects.filter(pk=r.pk).update(rank=rank)
        self.stdout.write(self.style.SUCCESS(f"  [4/9] Rosters — {len(roster_objs)} synced and ranked"))

        # ── 6. Matchups ───────────────────────────────────────────────────────
        if league.status == "pre_draft":
            self.stdout.write("  [5/9] Matchups — skipped (league is pre-draft)")
        else:
            roster_lookup = {r.roster_id: r for r in roster_objs}
            self.stdout.write("  [5/9] Matchups — fetching week by week (up to 18)...")
            total_matchup_rows = 0
            last_week = 0
            for week in range(1, 19):
                data = _get(f"/league/{league_id}/matchups/{week}") or []
                if not data:
                    break
                last_week = week
                for entry in data:
                    roster_id = entry.get("roster_id")
                    roster = roster_lookup.get(roster_id)
                    if not roster:
                        continue
                    SleeperMatchup.objects.update_or_create(
                        league=league,
                        week=week,
                        roster=roster,
                        defaults={
                            "matchup_id": entry.get("matchup_id") or 0,
                            "points": entry.get("points") or 0,
                        },
                    )
                    total_matchup_rows += 1
                self.stdout.write(f"         Week {week}/18 ({_pct(week, 18)}) — {len(data)} entries")
                time.sleep(SLEEP_BETWEEN)
            self.stdout.write(self.style.SUCCESS(f"  [5/9] Matchups — {total_matchup_rows} rows across {last_week} weeks"))

        # ── 7. Transactions ───────────────────────────────────────────────────
        self.stdout.write("  [6/9] Transactions — fetching week by week (up to 18)...")
        total_txns = 0
        last_week = 0
        for week in range(1, 19):
            data = _get(f"/league/{league_id}/transactions/{week}") or []
            if not data:
                break
            last_week = week
            for txn in data:
                txn_id = txn.get("transaction_id")
                if not txn_id:
                    continue
                txn_settings = txn.get("settings") or {}
                created_epoch = txn.get("created") or 0
                created_at = datetime.fromtimestamp(created_epoch / 1000, tz=timezone.utc) if created_epoch else timezone.now()
                SleeperTransaction.objects.update_or_create(
                    sleeper_txn_id=str(txn_id),
                    defaults={
                        "league": league,
                        "type": txn.get("type", ""),
                        "status": txn.get("status", ""),
                        "week": week,
                        "adds": txn.get("adds") or {},
                        "drops": txn.get("drops") or {},
                        "roster_ids": txn.get("roster_ids") or [],
                        "waiver_bid": txn_settings.get("waiver_bid"),
                        "draft_picks": txn.get("draft_picks") or [],
                        "created_at": created_at,
                    },
                )
                total_txns += 1
            self.stdout.write(f"         Week {week}/18 ({_pct(week, 18)}) — {len(data)} transactions")
            time.sleep(SLEEP_BETWEEN)
        self.stdout.write(self.style.SUCCESS(f"  [6/9] Transactions — {total_txns} total"))

        # ── 8. Traded picks ───────────────────────────────────────────────────
        self.stdout.write("  [7/9] Traded picks...")
        picks_data = _get(f"/league/{league_id}/traded_picks") or []
        SleeperTradedPick.objects.filter(league=league).delete()
        traded_pick_objs = []
        for p in picks_data:
            traded_pick_objs.append(SleeperTradedPick(
                league=league,
                season_year=int(p.get("season", season)),
                round=p.get("round", 1),
                roster_id=p.get("roster_id", 0),
                previous_owner_id=p.get("previous_owner_id", 0),
                owner_id=p.get("owner_id", 0),
            ))
        seen = set()
        unique_picks = []
        for p in traded_pick_objs:
            key = (p.league_id, p.season_year, p.round, p.roster_id, p.owner_id)
            if key not in seen:
                seen.add(key)
                unique_picks.append(p)
        SleeperTradedPick.objects.bulk_create(unique_picks, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"  [7/9] Traded picks — {len(unique_picks)} stored"))
        time.sleep(SLEEP_BETWEEN)

        # ── 9. Drafts ─────────────────────────────────────────────────────────
        self.stdout.write("  [8/9] Drafts...")
        drafts_data = _get(f"/league/{league_id}/drafts") or []
        total_picks = 0
        for di, draft in enumerate(drafts_data, 1):
            draft_id = draft.get("draft_id")
            if not draft_id:
                continue
            self.stdout.write(f"         Draft {di}/{len(drafts_data)} (id={draft_id})...")
            draft_picks = _get(f"/draft/{draft_id}/picks") or []
            for pick in draft_picks:
                player_id = pick.get("player_id")
                player_obj = SleeperPlayer.objects.filter(sleeper_id=str(player_id)).first() if player_id else None
                SleeperDraftPick.objects.update_or_create(
                    league=league,
                    draft_id=draft_id,
                    round=pick.get("round", 1),
                    pick_no=pick.get("pick_no", 0),
                    defaults={
                        "roster_id": pick.get("roster_id") or pick.get("picked_by") or 0,
                        "player": player_obj,
                        "player_name": (pick.get("metadata") or {}).get("first_name", "") + " " + (pick.get("metadata") or {}).get("last_name", ""),
                    },
                )
                total_picks += 1
            self.stdout.write(f"         → {len(draft_picks)} picks synced")
            time.sleep(SLEEP_BETWEEN)
        self.stdout.write(self.style.SUCCESS(f"  [8/9] Drafts — {total_picks} picks total"))

        # ── 10. Champion (optional) ───────────────────────────────────────────
        if mark_champion:
            self.stdout.write("  [9/9] Champion...")
            champ_roster = SleeperRoster.objects.filter(league=league, rank=1).first()
            if champ_roster:
                SleeperChampion.objects.update_or_create(
                    league=league,
                    defaults={"roster": champ_roster},
                )
                self.stdout.write(self.style.SUCCESS(f"  [9/9] Champion — {champ_roster.manager or champ_roster.team_name}"))
            else:
                self.stdout.write(self.style.WARNING("  [9/9] Champion — no rank-1 roster found, skipped"))
        else:
            self.stdout.write("  [9/9] Champion — skipped (use --mark-champion to set)")

        # ── 11. Historical recursion ──────────────────────────────────────────
        if historical and league.previous_league_id:
            prev_id = league.previous_league_id
            self.stdout.write(f"\n  Following history chain → {prev_id}")
            prev_meta = _get(f"/league/{prev_id}")
            if prev_meta:
                prev_season = int(prev_meta.get("season", season - 1))
                self._sync(
                    league_id=prev_id,
                    season=prev_season,
                    is_current=False,
                    sync_players=False,
                    mark_champion=False,
                    historical=True,
                    debug=False,
                )

        self.stdout.write(self.style.SUCCESS(f"\n✓ Done — league {league_id} synced.\n"))
