import requests
from django.core.management.base import BaseCommand, CommandError

from leaguehub.models import Season, Team
from leaguehub.services import sync_final_roster_from_yahoo, sync_standings_from_yahoo


class Command(BaseCommand):
    help = "Sync season standings and final rosters from Yahoo"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--access-token", type=str, required=True)

    def handle(self, *args, **options):
        season_year = options["season"]
        access_token = options["access_token"]

        season = Season.objects.filter(year=season_year).first()
        if not season:
            raise CommandError("Season not found.")
        if not season.yahoo_league_key:
            raise CommandError("Season.yahoo_league_key is blank.")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        standings_url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{season.yahoo_league_key}/standings"
        standings_response = requests.get(standings_url, headers=headers, params={"format": "json"}, timeout=30)
        standings_response.raise_for_status()
        sync_standings_from_yahoo(season, standings_response.json())
        self.stdout.write(self.style.SUCCESS(f"Standings synced for {season.year}"))

        for team in Team.objects.filter(season=season).exclude(yahoo_team_key=""):
            roster_url = f"https://fantasysports.yahooapis.com/fantasy/v2/team/{team.yahoo_team_key}/roster"
            roster_response = requests.get(roster_url, headers=headers, params={"format": "json"}, timeout=30)
            roster_response.raise_for_status()
            sync_final_roster_from_yahoo(season, team, roster_response.json())
            self.stdout.write(self.style.SUCCESS(f"Final roster synced for {team.name}"))