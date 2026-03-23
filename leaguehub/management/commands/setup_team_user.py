import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from leaguehub.models import ManagerProfile, Season, Team, TeamAccess

User = get_user_model()


class Command(BaseCommand):
    help = "Create or update a user and link them to a team for a season via TeamAccess"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument("--password", default=None, help="If omitted, you will be prompted")
        parser.add_argument("--team", required=True, help="Team name (must exist for the season)")
        parser.add_argument("--season", type=int, required=True, help="Season year")
        parser.add_argument("--commissioner", action="store_true", default=False)

    def handle(self, *args, **options):
        season = Season.objects.filter(year=options["season"]).first()
        if not season:
            raise CommandError(f"No season found for year {options['season']}.")

        team = Team.objects.filter(season=season, name=options["team"]).first()
        if not team:
            available = ", ".join(Team.objects.filter(season=season).values_list("name", flat=True))
            raise CommandError(
                f"No team named '{options['team']}' in {season.year}. "
                f"Available: {available or 'none — run sync_yahoo_season first'}"
            )

        user, created = User.objects.get_or_create(
            username=options["username"],
            defaults={"email": options["email"]},
        )

        if created:
            password = options["password"] or self._prompt_password(options["username"])
            user.set_password(password)
            user.save()
            self.stdout.write(f"Created user '{user.username}'.")
        else:
            if options["password"]:
                user.set_password(options["password"])
                user.save()
                self.stdout.write(f"Updated password for '{user.username}'.")
            else:
                self.stdout.write(f"User '{user.username}' already exists — password unchanged.")

        # Link ManagerProfile.user if a profile exists for this team and user is not yet linked
        if team.manager and not team.manager.user:
            team.manager.user = user
            team.manager.save(update_fields=["user"])
            self.stdout.write(f"Linked user to ManagerProfile '{team.manager.display_name}'.")

        access, access_created = TeamAccess.objects.update_or_create(
            user=user,
            season=season,
            team=team,
            defaults={"is_commissioner": options["commissioner"]},
        )

        action = "Created" if access_created else "Updated"
        role = "commissioner" if access.is_commissioner else "manager"
        self.stdout.write(self.style.SUCCESS(
            f"{action} TeamAccess: '{user.username}' -> '{team.name}' ({season.year}) as {role}."
        ))

    def _prompt_password(self, username):
        while True:
            pw = getpass.getpass(f"Password for '{username}': ")
            confirm = getpass.getpass("Confirm password: ")
            if pw == confirm:
                return pw
            self.stderr.write("Passwords do not match. Try again.")
