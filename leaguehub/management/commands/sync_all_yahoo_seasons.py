import requests
from django.core.management.base import BaseCommand, CommandError

from leaguehub.models import Season, Standing, Team
from leaguehub.services import (
    sync_champion_from_standings,
    sync_draft_picks_from_yahoo,
    sync_final_roster_from_yahoo,
    sync_keepers_from_draft,
    sync_keepers_from_yahoo,
    sync_league_metadata_from_yahoo,
    sync_standings_from_yahoo,
)


class Command(BaseCommand):
    help = "Sync all seasons that have yahoo_game_key and yahoo_league_key set"

    def add_arguments(self, parser):
        parser.add_argument("--access-token", type=str, required=True)
        parser.add_argument(
            "--sync-keepers",
            action="store_true",
            default=False,
            help="Import keeper picks from draft results for each season.",
        )
        parser.add_argument(
            "--mark-champions",
            action="store_true",
            default=False,
            help="Mark the rank-1 team as champion for each season. Only use after seasons are complete.",
        )
        parser.add_argument(
            "--skip-current",
            action="store_true",
            default=False,
            help="Skip the season marked as current.",
        )

    def handle(self, *args, **options):
        access_token = options["access_token"]
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        seasons = Season.objects.exclude(yahoo_game_key="").exclude(yahoo_league_key="").order_by("year")
        if options["skip_current"]:
            seasons = seasons.filter(is_current=False)

        if not seasons.exists():
            self.stdout.write("No seasons with yahoo_game_key and yahoo_league_key found.")
            return

        def get(url):
            r = requests.get(url, headers=headers, params={"format": "json"}, timeout=30)
            if not r.ok:
                raise CommandError(f"{r.status_code} for {url}\n{r.text}")
            return r.json()

        base = "https://fantasysports.yahooapis.com/fantasy/v2"

        for season in seasons:
            full_league_key = f"{season.yahoo_game_key}.l.{season.yahoo_league_key}"
            self.stdout.write(f"\n--- {season.year} ({full_league_key}) ---")

            # League metadata + resolve roster week from end_week
            roster_week = 16
            try:
                league_payload = get(f"{base}/league/{full_league_key}")
                sync_league_metadata_from_yahoo(season, league_payload)
                league_meta = league_payload.get("fantasy_content", {}).get("league", [{}])[0]
                roster_week = int(league_meta.get("end_week", 16))
                self.stdout.write(f"  [ok] metadata — name: {season.name}, roster week: {roster_week}")
            except CommandError as e:
                self.stderr.write(self.style.ERROR(f"  [fail] metadata: {e}"))

            # Standings
            try:
                sync_standings_from_yahoo(season, get(f"{base}/league/{full_league_key}/standings"))
                ranks = list(Standing.objects.filter(season=season).order_by("rank").values_list("rank", "team__name"))
                self.stdout.write(f"  [ok] standings — {len(ranks)} teams, ranks: {ranks[:3]}{'...' if len(ranks) > 3 else ''}")
            except CommandError as e:
                self.stderr.write(self.style.ERROR(f"  [fail] standings: {e}"))

            # Rosters (using championship week)
            teams = Team.objects.filter(season=season).exclude(yahoo_team_key="")
            for team in teams:
                try:
                    count = sync_final_roster_from_yahoo(season, team, get(f"{base}/team/{team.yahoo_team_key}/roster;week={roster_week}"))
                    self.stdout.write(f"  [ok] roster — {team.name} ({count} players)")
                except CommandError as e:
                    self.stderr.write(self.style.ERROR(f"  [fail] roster {team.name}: {e}"))

            # Draft picks (all rounds — used for keeper cost calculation)
            try:
                draft_payload = get(f"{base}/league/{full_league_key}/draftresults")
                pick_count = sync_draft_picks_from_yahoo(season, draft_payload)
                self.stdout.write(f"  [ok] draft picks — {pick_count} pick(s) stored")
            except CommandError as e:
                self.stderr.write(self.style.ERROR(f"  [fail] draft picks: {e}"))
                draft_payload = None

            # Keepers — try both sources; get_or_create prevents duplicates
            if options["sync_keepers"]:
                try:
                    count = sync_keepers_from_draft(season, draft_payload or get(f"{base}/league/{full_league_key}/draftresults"))
                    count += sync_keepers_from_yahoo(season, get(f"{base}/league/{full_league_key}/players;status=K/ownership"))
                    self.stdout.write(f"  [ok] keepers — {count} keeper(s) found")
                except CommandError as e:
                    self.stderr.write(self.style.ERROR(f"  [fail] keepers: {e}"))

            # Champion
            if options["mark_champions"]:
                top = Standing.objects.filter(season=season, rank=1).select_related("team").first()
                if top:
                    sync_champion_from_standings(season)
                    self.stdout.write(self.style.SUCCESS(f"  [ok] champion — {top.team.name}"))
                else:
                    self.stderr.write(self.style.WARNING(f"  [skip] champion — no rank=1 standing found for {season.year}"))

        self.stdout.write(self.style.SUCCESS("\nAll seasons processed."))
