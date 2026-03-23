from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from leaguehub.models import Season, Team, TeamAccess


class Command(BaseCommand):
    help = "Copy teams from one season to another as placeholders (e.g. 2025 → 2026)"

    def add_arguments(self, parser):
        parser.add_argument("--from-season", type=int, required=True, help="Year to copy teams from")
        parser.add_argument("--to-season", type=int, required=True, help="Year to copy teams into")
        parser.add_argument(
            "--copy-access",
            action="store_true",
            default=False,
            help="Also copy TeamAccess records so existing users are linked to the new teams",
        )

    def handle(self, *args, **options):
        from_season = Season.objects.filter(year=options["from_season"]).first()
        if not from_season:
            raise CommandError(f"No season found for year {options['from_season']}.")

        to_season = Season.objects.filter(year=options["to_season"]).first()
        if not to_season:
            raise CommandError(
                f"No season found for year {options['to_season']}. "
                f"Create it in the admin first (yahoo_game_key and yahoo_league_key can be left blank)."
            )

        source_teams = Team.objects.filter(season=from_season).select_related("manager")
        if not source_teams.exists():
            raise CommandError(f"No teams found for {from_season.year}.")

        existing = Team.objects.filter(season=to_season).values_list("name", flat=True)

        created_count = 0
        skipped_count = 0

        with transaction.atomic():
            for team in source_teams:
                if team.name in existing:
                    self.stdout.write(f"  [skip] {team.name} — already exists in {to_season.year}")
                    skipped_count += 1
                    continue

                new_team = Team.objects.create(
                    season=to_season,
                    name=team.name,
                    yahoo_team_key="",  # blank until Yahoo sync fills it in
                    manager=team.manager,
                )
                self.stdout.write(f"  [ok] created {new_team.name}")
                created_count += 1

                if options["copy_access"]:
                    accesses = TeamAccess.objects.filter(season=from_season, team=team)
                    for access in accesses:
                        TeamAccess.objects.get_or_create(
                            user=access.user,
                            season=to_season,
                            team=new_team,
                            defaults={"is_commissioner": access.is_commissioner},
                        )
                        self.stdout.write(f"    [ok] linked {access.user.username} → {new_team.name}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {created_count} team(s) created in {to_season.year}, {skipped_count} skipped."
        ))
        if not options["copy_access"]:
            self.stdout.write(
                "Run with --copy-access to also carry over user→team links, "
                "or use setup_team_user to link users manually."
            )
