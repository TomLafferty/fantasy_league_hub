from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import KeeperSubmissionForm
from .models import Champion, KeeperRecord, KeeperSubmission, Season, Standing, TeamAccess


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
    records = KeeperRecord.objects.select_related("season", "team", "player").all()
    return render(request, "leaguehub/keeper_history.html", {"records": records})


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
        form = KeeperSubmissionForm(request.POST, season=season, team=team, max_keepers=3)
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
            max_keepers=3,
            initial={"players": existing_ids},
        )

    current_submissions = KeeperSubmission.objects.filter(
        season=season,
        team=team,
    ).select_related("player").order_by("player__full_name")

    return render(request, "leaguehub/submit_keepers.html", {
        "season": season,
        "team": team,
        "form": form,
        "current_submissions": current_submissions,
    })