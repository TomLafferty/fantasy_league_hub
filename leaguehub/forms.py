from django import forms
from django.db import transaction
from .models import KeeperRecord, KeeperSubmission, Player, RosterSnapshot, Season, Team


class KeeperSubmissionForm(forms.Form):
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    def __init__(self, *args, season: Season, team: Team, max_keepers: int = 3, **kwargs):
        super().__init__(*args, **kwargs)
        self.season = season
        self.team = team
        self.max_keepers = max_keepers

        previous_season = Season.objects.filter(year=season.year - 1).first()
        prior_keeper_ids = []
        if previous_season:
            prior_keeper_ids = list(
                KeeperRecord.objects.filter(season=previous_season).values_list("player_id", flat=True)
            )

        eligible_ids = RosterSnapshot.objects.filter(
            season=season,
            team=team,
            is_final_roster=True,
        ).exclude(player_id__in=prior_keeper_ids).values_list("player_id", flat=True)

        self.fields["players"].queryset = Player.objects.filter(id__in=eligible_ids).order_by("full_name")

    def clean_players(self):
        players = self.cleaned_data["players"]
        if len(players) > self.max_keepers:
            raise forms.ValidationError(f"You may choose up to {self.max_keepers} keepers.")
        return players

    def save(self, user):
        with transaction.atomic():
            KeeperSubmission.objects.filter(season=self.season, team=self.team).delete()
            for player in self.cleaned_data["players"]:
                KeeperSubmission.objects.create(
                    season=self.season,
                    team=self.team,
                    player=player,
                    submitted_by=user,
                )