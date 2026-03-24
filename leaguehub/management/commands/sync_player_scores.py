import time
import requests
from django.core.management.base import BaseCommand, CommandError

from leaguehub.models import Season, Team
from leaguehub.services import sync_player_scores_from_yahoo


class Command(BaseCommand):
    help = "Sync weekly player scores (points + starter/bench status) for all teams in a season"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--access-token", type=str, required=True)
        parser.add_argument("--full-league-key", type=str, help="Override league key, e.g. 449.l.46828")
        parser.add_argument("--weeks", type=str, help="Comma-separated weeks, e.g. '1,2,3'. Defaults to 1 through end_week.")
        parser.add_argument("--debug-team-week", type=str, help="Print raw roster+stats JSON for 'team_key:week', e.g. '449.l.8026.t.1:1'")

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
                    self.stdout.write(f"  Rate limited / empty response, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                if not r.ok:
                    raise CommandError(f"Yahoo API error {r.status_code} for {url}\n{r.text[:500]}")
                try:
                    return r.json()
                except Exception:
                    raise CommandError(f"Yahoo returned non-JSON (HTTP {r.status_code}) for {url}.\nRaw: {r.text[:500]}")
            raise CommandError(f"Yahoo rate-limited after 3 attempts for {url}. Token may have expired.")

        base = "https://fantasysports.yahooapis.com/fantasy/v2"

        if options.get("debug_team_week"):
            import json
            parts = options["debug_team_week"].split(":")
            if len(parts) != 2:
                raise CommandError("--debug-team-week must be 'team_key:week', e.g. '449.l.8026.t.1:1'")
            team_key, week_str = parts
            payload = get(f"{base}/team/{team_key}/roster;week={week_str}/players/points;type=week;week={week_str}")
            team_list = payload.get("fantasy_content", {}).get("team", [])
            self.stdout.write(f"team_list length: {len(team_list)}")
            resources = team_list[1] if len(team_list) > 1 else {}
            roster = resources.get("roster", {})
            self.stdout.write(f"roster keys: {list(roster.keys()) if isinstance(roster, dict) else type(roster).__name__}")
            inner = roster.get("0", roster)
            players_data = inner.get("players", {}) if isinstance(inner, dict) else {}
            first_key = next((k for k in players_data if k != "count"), None)
            if first_key:
                self.stdout.write(f"\nFirst player entry:")
                self.stdout.write(json.dumps(players_data[first_key], indent=2)[:3000])
            else:
                self.stdout.write(json.dumps(resources, indent=2)[:3000])
            return

        # Determine weeks
        if options.get("weeks"):
            weeks = [int(w.strip()) for w in options["weeks"].split(",")]
        else:
            league_payload = get(f"{base}/league/{full_league_key}")
            league_meta = league_payload.get("fantasy_content", {}).get("league", [{}])[0]
            end_week = int(league_meta.get("end_week", 16))
            weeks = list(range(1, end_week + 1))

        teams = Team.objects.filter(season=season).exclude(yahoo_team_key="")
        total = 0
        for week in weeks:
            week_total = 0
            for team in teams:
                url = f"{base}/team/{team.yahoo_team_key}/roster;week={week}/players/points;type=week;week={week}"
                payload = get(url)
                n = sync_player_scores_from_yahoo(season, team, week, payload)
                week_total += n
            self.stdout.write(f"  Week {week}: {week_total} player score(s) stored")
            total += week_total

        self.stdout.write(self.style.SUCCESS(f"\nDone. {total} player week score(s) stored for {season.year}."))
