import requests
from django.core.management.base import BaseCommand, CommandError

from leaguehub.models import Season


class Command(BaseCommand):
    help = "Discover all NFL leagues from Yahoo and create/update Season records"

    def add_arguments(self, parser):
        parser.add_argument("--access-token", type=str, required=True)

    def handle(self, *args, **options):
        access_token = options["access_token"]
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        url = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_codes=nfl/leagues"
        response = requests.get(url, headers=headers, params={"format": "json"}, timeout=30)
        if not response.ok:
            raise CommandError(f"Yahoo API error {response.status_code}:\n{response.text}")

        payload = response.json()

        users_data = payload.get("fantasy_content", {}).get("users", {})
        user_entry = users_data.get("0", {}).get("user", [])
        if len(user_entry) < 2:
            raise CommandError("Unexpected response structure — no user data found.")

        games_data = user_entry[1].get("games", {})
        imported = 0

        for gkey, gvalue in games_data.items():
            if gkey == "count" or not isinstance(gvalue, dict):
                continue

            game_wrapper = gvalue.get("game", [])
            if len(game_wrapper) < 2:
                continue

            # game[0] is a list of game metadata dicts
            game_meta = {}
            raw = game_wrapper[0]
            for item in (raw if isinstance(raw, list) else [raw]):
                if isinstance(item, dict):
                    game_meta.update(item)

            game_key = str(game_meta.get("game_key", ""))
            season_year = game_meta.get("season")
            if not game_key or not season_year:
                continue

            try:
                season_year = int(season_year)
            except (TypeError, ValueError):
                continue

            leagues_data = game_wrapper[1].get("leagues", {})
            for lkey, lvalue in leagues_data.items():
                if lkey == "count" or not isinstance(lvalue, dict):
                    continue

                league_wrapper = lvalue.get("league", [])
                league_meta = {}
                for item in (league_wrapper if isinstance(league_wrapper, list) else [league_wrapper]):
                    if isinstance(item, dict):
                        league_meta.update(item)

                league_key = league_meta.get("league_key", "")
                league_id = league_meta.get("league_id", "")
                league_name = league_meta.get("name", "")

                if not league_id:
                    # Fall back to splitting the league_key
                    parts = league_key.split(".l.")
                    league_id = parts[1] if len(parts) == 2 else ""

                if not league_id:
                    continue

                if league_name != "F.F.U.P.A.":
                    self.stdout.write(f"  Skipping '{league_name}' ({season_year}) — not F.F.U.P.A.")
                    continue

                formatted_name = f"{season_year} F.F.U.P.A."

                season, created = Season.objects.update_or_create(
                    year=season_year,
                    defaults={
                        "yahoo_game_key": game_key,
                        "yahoo_league_key": league_id,
                        "name": formatted_name,
                    },
                )

                if not created:
                    season.yahoo_game_key = game_key
                    season.yahoo_league_key = league_id
                    season.name = formatted_name
                    season.save(update_fields=["yahoo_game_key", "yahoo_league_key", "name"])

                action = "Created" if created else "Updated"
                self.stdout.write(
                    f"{action}: {formatted_name} — game key {game_key}, league ID {league_id}"
                )
                imported += 1

        self.stdout.write(self.style.SUCCESS(f"\nDone. {imported} season(s) imported/updated."))
