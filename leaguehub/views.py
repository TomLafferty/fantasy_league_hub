from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import KeeperSubmissionForm
from .models import Champion, DraftPick, KeeperRecord, KeeperSubmission, RosterSnapshot, Season, Standing, Team, TeamAccess


def home(request):
    current_season = Season.objects.filter(is_current=True).first()
    recent_champions = Champion.objects.select_related("season", "team").order_by("-season__year")[:10]
    return render(request, "leaguehub/home.html", {
        "current_season": current_season,
        "recent_champions": recent_champions,
    })


def champions_view(request):
    champions = Champion.objects.select_related("season", "team").order_by("-season__year")
    return render(request, "leaguehub/champions.html", {"champions": champions})


def standings_view(request):
    seasons = Season.objects.all().order_by("-year")
    selected_id = request.GET.get("season")
    selected_season = seasons.first() if not selected_id else get_object_or_404(Season, id=selected_id)
    standings = Standing.objects.filter(season=selected_season).select_related("team").order_by("rank")
    return render(request, "leaguehub/standings.html", {
        "seasons": seasons,
        "selected_season": selected_season,
        "standings": standings,
    })


def keeper_history_view(request):
    seasons = Season.objects.all().order_by("-year")
    selected_id = request.GET.get("season")
    selected_season = seasons.first() if not selected_id else get_object_or_404(Season, id=selected_id)
    records = (
        KeeperRecord.objects.filter(season=selected_season)
        .select_related("season", "team", "player")
        .order_by("team__name", "player__full_name")
    )
    return render(request, "leaguehub/keeper_history.html", {
        "seasons": seasons,
        "selected_season": selected_season,
        "records": records,
    })


def team_detail_view(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    roster = (
        RosterSnapshot.objects.filter(team=team, is_final_roster=True)
        .select_related("player")
        .order_by("player__primary_position", "player__full_name")
    )
    return render(request, "leaguehub/team_detail.html", {
        "team": team,
        "roster": roster,
    })


@login_required
def submit_keepers_view(request):
    season = Season.objects.filter(is_current=True).first()
    if not season:
        raise Http404("No current season configured.")

    access = TeamAccess.objects.filter(user=request.user, season=season).select_related("team").first()
    if not access:
        raise Http404("You are not linked to a team for this season.")

    team = access.team

    if request.method == "POST":
        form = KeeperSubmissionForm(request.POST, season=season, team=team, max_keepers=2)
        if form.is_valid():
            form.save(request.user)
            messages.success(request, "Keepers submitted.")
            return redirect("submit_keepers")
    else:
        existing_ids = KeeperSubmission.objects.filter(
            season=season, team=team
        ).values_list("player_id", flat=True)

        form = KeeperSubmissionForm(
            season=season,
            team=team,
            max_keepers=2,
            initial={"players": existing_ids},
        )

    current_submissions = KeeperSubmission.objects.filter(
        season=season,
        team=team,
    ).select_related("player").order_by("player__full_name")

    previous_season = Season.objects.filter(year=season.year - 1).first()

    # Ineligible: players on this roster who were kept last year
    ineligible = []
    if previous_season:
        roster_player_ids = RosterSnapshot.objects.filter(
            season=season, team=team, is_final_roster=True
        ).values_list("player_id", flat=True)
        prior_records = (
            KeeperRecord.objects.filter(season=previous_season, player_id__in=roster_player_ids)
            .select_related("player", "team")
        )
        ineligible = [{"player": r.player, "kept_by": r.team.name} for r in prior_records]

    # Draft round each eligible player was picked in last season (for keeper cost display)
    # Undrafted players default to round 10
    player_rounds = {}
    if previous_season:
        picks = DraftPick.objects.filter(
            season=previous_season,
            player__isnull=False,
        ).values("player_id", "round")
        player_rounds = {p["player_id"]: p["round"] for p in picks}

    return render(request, "leaguehub/submit_keepers.html", {
        "season": season,
        "team": team,
        "form": form,
        "current_submissions": current_submissions,
        "ineligible": ineligible,
        "player_rounds": player_rounds,
    })