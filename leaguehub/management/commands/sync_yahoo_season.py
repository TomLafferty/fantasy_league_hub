import requests
from django.core.management.base import BaseCommand, CommandError

from leaguehub.models import Season, Team
from leaguehub.services import (
    sync_champion_from_standings,
    sync_final_roster_from_yahoo,
    sync_keepers_from_draft,
    sync_keepers_from_yahoo,
    sync_league_metadata_from_yahoo,
    sync_standings_from_yahoo,
)


class Command(BaseCommand):
    help = "Sync a season's standings, rosters, metadata, and optionally keepers/champion from Yahoo"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--access-token", type=str, required=True)
        parser.add_argument(
            "--full-league-key",
            type=str,
            help="Override the league key (e.g. 449.l.46828). Skips game/league key lookup from the Season record.",
        )
        parser.add_argument(
            "--sync-keepers",
            action="store_true",
            default=False,
            help="Also import keeper transactions as KeeperRecord entries.",
        )
        parser.add_argument(
            "--mark-champion",
            action="store_true",
            default=False,
            help="Mark the rank-1 team as champion. Only use after the season is complete.",
        )
        parser.add_argument(
            "--debug-standings",
            action="store_true",
            default=False,
            help="Print the raw Yahoo standings structure for the first team and exit.",
        )
        parser.add_argument(
            "--debug-roster",
            action="store_true",
            default=False,
            help="Print the raw Yahoo roster structure for the first team and exit.",
        )
        parser.add_argument(
            "--roster-week",
            type=int,
            default=None,
            help="Week to fetch rosters for. Defaults to end_week from Yahoo league settings (the championship week).",
        )
        parser.add_argument(
            "--debug-keepers",
            action="store_true",
            default=False,
            help="Print raw responses from candidate keeper endpoints and exit.",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        access_token = options["access_token"]

        season = Season.objects.filter(year=season_year).first()
        if not season:
            raise CommandError("Season not found.")

        if options["full_league_key"]:
            full_league_key = options["full_league_key"]
        else:
            if not season.yahoo_game_key:
                raise CommandError("Season.yahoo_game_key is blank. Set it or pass --full-league-key.")
            if not season.yahoo_league_key:
                raise CommandError("Season.yahoo_league_key is blank. Set it or pass --full-league-key.")
            full_league_key = f"{season.yahoo_game_key}.l.{season.yahoo_league_key}"

        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        def get(url, **params):
            r = requests.get(url, headers=headers, params={"format": "json", **params}, timeout=30)
            if not r.ok:
                raise CommandError(f"Yahoo API error {r.status_code} for {url}\n{r.text}")
            return r.json()

        base = "https://fantasysports.yahooapis.com/fantasy/v2"

        # League metadata (name + end_week)
        league_payload = get(f"{base}/league/{full_league_key}")
        sync_league_metadata_from_yahoo(season, league_payload)
        league_meta = league_payload.get("fantasy_content", {}).get("league", [{}])[0]
        roster_week = options["roster_week"] or int(league_meta.get("end_week", 16))
        self.stdout.write(f"League metadata synced for {season.year} (roster week: {roster_week})")

        # Standings + manager profiles
        standings_payload = get(f"{base}/league/{full_league_key}/standings")

        if options["debug_standings"]:
            import json
            league_list = standings_payload.get("fantasy_content", {}).get("league", [])
            resources = league_list[1] if len(league_list) > 1 else {}
            standings_list = resources.get("standings", [{}])
            teams_data = standings_list[0].get("teams", {}) if standings_list else {}
            first_key = next((k for k in teams_data if k != "count"), None)
            if first_key:
                self.stdout.write(json.dumps(teams_data[first_key], indent=2))
            else:
                self.stdout.write(json.dumps(standings_payload, indent=2))
            return

        sync_standings_from_yahoo(season, standings_payload)
        self.stdout.write(self.style.SUCCESS(f"Standings synced for {season.year}"))

        if options["debug_keepers"]:
            import json
            candidates = [
                f"{base}/league/{full_league_key}/players;status=K",
                f"{base}/league/{full_league_key}/players;status=kept",
                f"{base}/league/{full_league_key}/draftpicks",
                f"{base}/league/{full_league_key}/transactions;types=keeper",
            ]
            for url in candidates:
                self.stdout.write(f"\n--- {url} ---")
                try:
                    r = requests.get(url, headers=headers, params={"format": "json"}, timeout=30)
                    if r.ok:
                        league_l = r.json().get("fantasy_content", {}).get("league", [])
                        resources = league_l[1] if len(league_l) > 1 else {}
                        self.stdout.write(f"keys: {list(resources.keys())}")
                        self.stdout.write(json.dumps(resources, indent=2)[:1000])
                    else:
                        self.stdout.write(f"HTTP {r.status_code}: {r.text[:200]}")
                except Exception as e:
                    self.stdout.write(f"Error: {e}")
            return

        # Final rosters
        for team in Team.objects.filter(season=season).exclude(yahoo_team_key=""):
            roster_payload = get(f"{base}/team/{team.yahoo_team_key}/roster;week={roster_week}")

            if options["debug_roster"]:
                import json
                team_list = roster_payload.get("fantasy_content", {}).get("team", [])
                self.stdout.write(f"team list length: {len(team_list)}")
                for i, item in enumerate(team_list):
                    self.stdout.write(f"team_list[{i}] type: {type(item).__name__}, keys: {list(item.keys()) if isinstance(item, dict) else 'n/a'}")
                    if isinstance(item, dict) and "roster" in item:
                        roster = item["roster"]
                        self.stdout.write(f"roster keys: {list(roster.keys()) if isinstance(roster, dict) else type(roster).__name__}")
                        self.stdout.write(json.dumps(roster, indent=2)[:3000])
                return

            count = sync_final_roster_from_yahoo(season, team, roster_payload)
            self.stdout.write(self.style.SUCCESS(f"Roster synced for {team.name} — {count} player(s)"))

        # Keepers — try both sources; get_or_create prevents duplicates
        if options["sync_keepers"]:
            count = sync_keepers_from_draft(season, get(f"{base}/league/{full_league_key}/draftresults"))
            count += sync_keepers_from_yahoo(season, get(f"{base}/league/{full_league_key}/players;status=K/ownership"))
            self.stdout.write(self.style.SUCCESS(f"Keepers synced for {season.year} — {count} keeper(s) found"))

        # Champion
        if options["mark_champion"]:
            sync_champion_from_standings(season)
            self.stdout.write(self.style.SUCCESS(f"Champion marked for {season.year}"))
