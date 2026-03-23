from django import forms
from django.contrib import admin

from .models import (
    Champion,
    DraftPick,
    KeeperRecord,
    KeeperSubmission,
    ManagerProfile,
    Player,
    RosterSnapshot,
    Season,
    Standing,
    Team,
    TeamAccess,
)


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ["year", "name", "is_current", "keeper_deadline"]
    ordering = ["-year"]


@admin.register(ManagerProfile)
class ManagerProfileAdmin(admin.ModelAdmin):
    list_display = ["display_name", "yahoo_guid", "user"]
    search_fields = ["display_name", "yahoo_guid"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "season", "manager"]
    list_filter = ["season__year"]
    search_fields = ["name"]
    ordering = ["-season__year", "name"]


@admin.register(Standing)
class StandingAdmin(admin.ModelAdmin):
    list_display = ["team", "season", "rank", "wins", "losses", "ties"]
    list_filter = ["season__year"]
    ordering = ["-season__year", "rank"]


@admin.register(Champion)
class ChampionAdmin(admin.ModelAdmin):
    list_display = ["season", "team", "notes"]
    ordering = ["-season__year"]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["full_name", "primary_position", "nfl_team", "yahoo_player_key"]
    search_fields = ["full_name", "yahoo_player_key"]


@admin.register(RosterSnapshot)
class RosterSnapshotAdmin(admin.ModelAdmin):
    list_display = ["player", "team", "season", "week", "is_final_roster"]
    list_filter = ["season__year", "is_final_roster"]
    search_fields = ["player__full_name", "team__name"]


@admin.register(DraftPick)
class DraftPickAdmin(admin.ModelAdmin):
    list_display = ["season", "round", "pick", "team", "player"]
    list_filter = ["season__year"]
    search_fields = ["player__full_name", "team__name"]
    ordering = ["-season__year", "round", "pick"]


@admin.register(KeeperRecord)
class KeeperRecordAdmin(admin.ModelAdmin):
    list_display = ["season", "team", "player", "source"]
    list_filter = ["season__year"]
    search_fields = ["player__full_name", "team__name"]
    ordering = ["-season__year", "team__name"]


class TeamAccessForm(forms.ModelForm):
    class Meta:
        model = TeamAccess
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter out teams already assigned to any user (excluding current instance)
        assigned_team_ids = TeamAccess.objects.values_list("team_id", flat=True)
        if self.instance.pk:
            assigned_team_ids = assigned_team_ids.exclude(pk=self.instance.pk)
        self.fields["team"].queryset = (
            Team.objects.exclude(id__in=assigned_team_ids)
            .select_related("season")
            .order_by("-season__year", "name")
        )
        self.fields["team"].label_from_instance = lambda t: f"{t.season.year} — {t.name}"
        self.fields["season"].queryset = Season.objects.order_by("-year")


@admin.register(TeamAccess)
class TeamAccessAdmin(admin.ModelAdmin):
    form = TeamAccessForm
    list_display = ["user", "team", "season", "is_commissioner"]
    list_filter = ["season__year"]
    search_fields = ["user__username", "team__name"]
    ordering = ["-season__year", "team__name"]


@admin.register(KeeperSubmission)
class KeeperSubmissionAdmin(admin.ModelAdmin):
    list_display = ["season", "team", "player", "submitted_by"]
    list_filter = ["season__year"]
    search_fields = ["player__full_name", "team__name"]
    ordering = ["-season__year", "team__name"]
