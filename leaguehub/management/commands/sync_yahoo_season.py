import requests
from django.core.management.base import BaseCommand, CommandError

from leaguehub.models import Season, Team
from leaguehub.services import sync_final_roster_from_yahoo, sync_standings_from_yahoo


class Command(BaseCommand):
    help = "Sync season standings and final rosters from Yahoo"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--access-token", type=str, required=True)
        parser.add_argument(
            "--full-league-key",
            type=str,
            help="Override the league key (e.g. 449.l.46828). Skips game/league key lookup from the Season record.",
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

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        standings_url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{full_league_key}/standings"
        standings_response = requests.get(standings_url, headers=headers, params={"format": "json"}, timeout=30)
        if not standings_response.ok:
            raise CommandError(
                f"Yahoo API error {standings_response.status_code} for {standings_url}\n{standings_response.text}"
            )
        sync_standings_from_yahoo(season, standings_response.json())
        self.stdout.write(self.style.SUCCESS(f"Standings synced for {season.year}"))

        for team in Team.objects.filter(season=season).exclude(yahoo_team_key=""):
            roster_url = f"https://fantasysports.yahooapis.com/fantasy/v2/team/{team.yahoo_team_key}/roster"
            roster_response = requests.get(roster_url, headers=headers, params={"format": "json"}, timeout=30)
            roster_response.raise_for_status()
            sync_final_roster_from_yahoo(season, team, roster_response.json())
            self.stdout.write(self.style.SUCCESS(f"Final roster synced for {team.name}"))