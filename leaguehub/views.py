from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import KeeperSubmissionForm
from .models import Champion, DraftPick, KeeperRecord, KeeperSubmission, Matchup, PlayerWeeklyScore, RosterSnapshot, RuleProposal, RuleVote, Season, Standing, Team, TeamAccess


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


def constitution_view(request):
    return render(request, "leaguehub/constitution.html")


def rules_view(request):
    proposals = (
        RuleProposal.objects
        .annotate(
            up_count=Count("votes", filter=Q(votes__vote="up")),
            down_count=Count("votes", filter=Q(votes__vote="down")),
        )
        .order_by("-up_count", "-created_at")
    )
    user_votes = {}
    if request.user.is_authenticated:
        user_votes = {
            v.proposal_id: v.vote
            for v in RuleVote.objects.filter(user=request.user, proposal__in=proposals)
        }
    return render(request, "leaguehub/new_rules.html", {
        "proposals": proposals,
        "user_votes": user_votes,
    })


@login_required
def submit_rule_view(request):
    if request.method == "POST":
        description = request.POST.get("description", "").strip()
        if description:
            RuleProposal.objects.create(submitted_by=request.user, description=description)
            messages.success(request, "Rule proposal submitted.")
        else:
            messages.error(request, "Description cannot be empty.")
    return redirect("rules")


@login_required
@require_POST
def vote_rule_view(request, proposal_id):
    proposal = get_object_or_404(RuleProposal, id=proposal_id)
    vote_value = request.POST.get("vote")
    if vote_value not in ("up", "down"):
        return JsonResponse({"error": "invalid"}, status=400)

    existing = RuleVote.objects.filter(proposal=proposal, user=request.user).first()
    if existing:
        if existing.vote == vote_value:
            existing.delete()
        else:
            existing.vote = vote_value
            existing.save()
    else:
        RuleVote.objects.create(proposal=proposal, user=request.user, vote=vote_value)

    down_count = RuleVote.objects.filter(proposal=proposal, vote="down").count()
    if down_count >= 9:
        proposal.delete()
        return JsonResponse({"deleted": True})

    up_count = RuleVote.objects.filter(proposal=proposal, vote="up").count()
    down_count = RuleVote.objects.filter(proposal=proposal, vote="down").count()
    user_vote_obj = RuleVote.objects.filter(proposal=proposal, user=request.user).first()
    return JsonResponse({
        "deleted": False,
        "up_count": up_count,
        "down_count": down_count,
        "user_vote": user_vote_obj.vote if user_vote_obj else None,
    })


def hall_view(request):
    def mgr_name(team):
        return team.manager.display_name if team and team.manager else (team.name if team else "Unknown")

    # Load all standings (exclude seasons with zero games played = placeholder seasons)
    all_standings = list(
        Standing.objects
        .select_related("team__manager", "season")
        .exclude(wins=0, losses=0, ties=0)
        .order_by("season__year", "rank")
    )
    played_standings = [s for s in all_standings if s.wins + s.losses + s.ties > 0]

    all_champions = list(Champion.objects.select_related("team__manager", "season").all())

    # ── HOF SEASON ──
    top_points_for = sorted(played_standings, key=lambda s: s.points_for, reverse=True)[:10]
    top_wins = sorted(played_standings, key=lambda s: (s.wins, s.points_for), reverse=True)[:10]
    best_defense = sorted(played_standings, key=lambda s: s.points_against)[:10]  # lowest PA = best

    champ_counts = defaultdict(lambda: {"name": "", "years": []})
    for c in all_champions:
        name = mgr_name(c.team)
        champ_counts[name]["name"] = name
        champ_counts[name]["years"].append(c.season.year)
    most_championships = sorted(champ_counts.values(), key=lambda x: len(x["years"]), reverse=True)

    season_max_rank = defaultdict(int)
    for s in played_standings:
        if s.rank > season_max_rank[s.season_id]:
            season_max_rank[s.season_id] = s.rank

    last_place_mgr = defaultdict(lambda: {"name": "", "count": 0, "years": []})
    for s in played_standings:
        if season_max_rank.get(s.season_id) and s.rank == season_max_rank[s.season_id]:
            name = mgr_name(s.team)
            last_place_mgr[name]["name"] = name
            last_place_mgr[name]["count"] += 1
            last_place_mgr[name]["years"].append(s.season.year)
    most_last_place = sorted(last_place_mgr.values(), key=lambda x: x["count"], reverse=True)

    champion_season_team = {c.season_id: c.team_id for c in all_champions}
    no_title_standings = [s for s in played_standings if champion_season_team.get(s.season_id) != s.team_id]
    highest_pf_no_title = sorted(no_title_standings, key=lambda s: s.points_for, reverse=True)[:10]

    # ── HOS SEASON ──
    worst_points_for = sorted(played_standings, key=lambda s: s.points_for)[:10]
    most_losses = sorted(played_standings, key=lambda s: (s.losses, -float(s.points_for)), reverse=True)[:10]
    worst_defense = sorted(played_standings, key=lambda s: s.points_against, reverse=True)[:10]
    no_playoff_standings = [s for s in played_standings if s.final_place is None]
    highest_pf_no_playoffs = sorted(no_playoff_standings, key=lambda s: s.points_for, reverse=True)[:10]

    # ── MATCHUP RECORDS ──
    has_matchup_data = Matchup.objects.exists()
    highest_score = biggest_margin = highest_losing_score = longest_win_streak = best_playoff_score = None
    lowest_score = worst_margin = longest_loss_streak = lowest_playoff_score = None
    cumulative_all = cumulative_playoff = cumulative_regular = None
    bro_vs_bro = []

    if has_matchup_data:
        all_matchups = list(
            Matchup.objects.select_related("team_a__manager", "team_b__manager", "season")
            .order_by("season__year", "week")
        )

        # Build a flat list of score events
        score_events = []
        for m in all_matchups:
            if m.score_a >= m.score_b:
                w_team, w_score, l_team, l_score = m.team_a, m.score_a, m.team_b, m.score_b
            else:
                w_team, w_score, l_team, l_score = m.team_b, m.score_b, m.team_a, m.score_a
            margin = w_score - l_score
            score_events.append({
                "matchup": m,
                "winner": mgr_name(w_team),
                "loser": mgr_name(l_team),
                "winner_score": w_score,
                "loser_score": l_score,
                "margin": margin,
                "year": m.season.year,
                "week": m.week,
                "is_playoff": m.is_playoff,
                "is_consolation": m.is_consolation,
            })

        highest_score = sorted(score_events, key=lambda x: x["winner_score"], reverse=True)[:10]
        biggest_margin = sorted(score_events, key=lambda x: x["margin"], reverse=True)[:10]
        highest_losing_score = sorted(score_events, key=lambda x: x["loser_score"], reverse=True)[:10]
        lowest_score = sorted(score_events, key=lambda x: x["loser_score"])[:10]
        worst_margin = biggest_margin  # same data, loser's perspective

        # Playoffs only — exclude consolation bracket entirely
        playoff_events = [e for e in score_events if e["is_playoff"] and not e["is_consolation"]]
        if playoff_events:
            best_playoff_score = sorted(playoff_events, key=lambda x: x["winner_score"], reverse=True)[:10]
            lowest_playoff_score = sorted(playoff_events, key=lambda x: x["loser_score"])[:10]

        # Cumulative all-time points by manager (consolation excluded throughout)
        from decimal import Decimal as D
        cum = defaultdict(lambda: {"name": "", "all": D(0), "playoff": D(0), "regular": D(0)})
        for m in all_matchups:
            if m.is_consolation:
                continue
            for team, score in [(m.team_a, m.score_a), (m.team_b, m.score_b)]:
                name = mgr_name(team)
                cum[name]["name"] = name
                cum[name]["all"] += score
                if m.is_playoff:
                    cum[name]["playoff"] += score
                else:
                    cum[name]["regular"] += score
        cumulative_all = sorted(cum.values(), key=lambda x: x["all"], reverse=True)
        cumulative_playoff = sorted(cum.values(), key=lambda x: x["playoff"], reverse=True)
        cumulative_regular = sorted(cum.values(), key=lambda x: x["regular"], reverse=True)

        # Streaks — per (season, team), find max consecutive W or L
        season_team_results = defaultdict(list)
        team_obj_map = {}
        season_obj_map = {}
        for m in all_matchups:
            ka = (m.season_id, m.team_a_id)
            kb = (m.season_id, m.team_b_id)
            if m.score_a > m.score_b:
                season_team_results[ka].append("W")
                season_team_results[kb].append("L")
            elif m.score_b > m.score_a:
                season_team_results[ka].append("L")
                season_team_results[kb].append("W")
            else:
                season_team_results[ka].append("T")
                season_team_results[kb].append("T")
            team_obj_map[ka] = m.team_a
            team_obj_map[kb] = m.team_b
            season_obj_map[m.season_id] = m.season

        def max_streak(results, target):
            mx = cur = 0
            for r in results:
                cur = cur + 1 if r == target else 0
                mx = max(mx, cur)
            return mx

        win_streaks, loss_streaks = [], []
        for key, results in season_team_results.items():
            team = team_obj_map.get(key)
            season_obj = season_obj_map.get(key[0])
            if not team or not season_obj:
                continue
            ws = max_streak(results, "W")
            ls = max_streak(results, "L")
            entry = {"manager": mgr_name(team), "team": team.name, "year": season_obj.year}
            if ws:
                win_streaks.append({**entry, "streak": ws})
            if ls:
                loss_streaks.append({**entry, "streak": ls})

        longest_win_streak = sorted(win_streaks, key=lambda x: x["streak"], reverse=True)[:10]
        longest_loss_streak = sorted(loss_streaks, key=lambda x: x["streak"], reverse=True)[:10]

        # Bro vs Bro — head-to-head by manager
        h2h = defaultdict(lambda: {"a_wins": 0, "b_wins": 0, "ties": 0})
        for m in all_matchups:
            ma = mgr_name(m.team_a)
            mb = mgr_name(m.team_b)
            sa, sb = m.score_a, m.score_b
            if ma > mb:
                ma, mb = mb, ma
                sa, sb = sb, sa
            key = (ma, mb)
            if sa > sb:
                h2h[key]["a_wins"] += 1
            elif sb > sa:
                h2h[key]["b_wins"] += 1
            else:
                h2h[key]["ties"] += 1

        for (ma, mb), rec in h2h.items():
            total = rec["a_wins"] + rec["b_wins"] + rec["ties"]
            if rec["a_wins"] >= rec["b_wins"]:
                leader, trailer, lw, ll = ma, mb, rec["a_wins"], rec["b_wins"]
            else:
                leader, trailer, lw, ll = mb, ma, rec["b_wins"], rec["a_wins"]
            bro_vs_bro.append({
                "mgr_a": ma, "mgr_b": mb,
                "a_wins": rec["a_wins"], "b_wins": rec["b_wins"], "ties": rec["ties"],
                "total": total,
                "leader": leader, "trailer": trailer,
                "leader_wins": lw, "leader_losses": ll,
                "dominance": abs(rec["a_wins"] - rec["b_wins"]),
            })
        bro_vs_bro = sorted(bro_vs_bro, key=lambda x: (x["dominance"], x["total"]), reverse=True)

    # ── KEEPER LEGENDS ──
    all_keepers = list(KeeperRecord.objects.select_related("player", "team__manager").all())
    keeper_map = defaultdict(lambda: {"name": "", "count": 0, "teams": set()})
    for kr in all_keepers:
        pname = kr.player.full_name
        keeper_map[pname]["name"] = pname
        keeper_map[pname]["count"] += 1
        keeper_map[pname]["teams"].add(mgr_name(kr.team))
    keeper_legends_raw = sorted(keeper_map.values(), key=lambda x: x["count"], reverse=True)[:15]
    keeper_legends = []
    for kl in keeper_legends_raw:
        keeper_legends.append({
            "name": kl["name"],
            "count": kl["count"],
            "team_count": len(kl["teams"]),
            "teams": sorted(kl["teams"]),
        })
    team_spread = sorted(keeper_legends, key=lambda x: x["team_count"], reverse=True)[:10]

    # ── PLAYER STAT RECORDS ──
    has_player_data = PlayerWeeklyScore.objects.exists()
    bench_disasters = []
    best_player_game = []
    best_draft_picks = []
    worst_draft_picks = []
    draft_pick_seasons = []
    draft_pick_managers = []
    prized_keepers = []

    if has_player_data:
        from decimal import Decimal as D

        all_scores = list(
            PlayerWeeklyScore.objects
            .select_related("season", "team__manager", "player")
            .all()
        )

        # ── Most bench points in a week (Bill Kinney Award) ──
        bench_by_week = defaultdict(lambda: {"manager": "", "team": "", "year": 0, "week": 0, "bench_pts": D(0)})
        for s in all_scores:
            if not s.is_starter:
                key = (s.season_id, s.team_id, s.week)
                entry = bench_by_week[key]
                entry["manager"] = mgr_name(s.team)
                entry["team"] = s.team.name
                entry["year"] = s.season.year
                entry["week"] = s.week
                entry["bench_pts"] += s.points
        bench_disasters = sorted(bench_by_week.values(), key=lambda x: x["bench_pts"], reverse=True)[:15]

        # ── Highest single-player performance ──
        best_player_game = sorted(all_scores, key=lambda s: s.points, reverse=True)[:15]

        # ── Best/worst draft pick by round ──
        all_picks = list(
            DraftPick.objects
            .select_related("season", "team__manager", "player")
            .filter(player__isnull=False)
            .all()
        )
        # Build season totals per player per season
        player_season_pts = defaultdict(D)
        for s in all_scores:
            player_season_pts[(s.player_id, s.season_id)] += s.points

        pick_records = []
        for pick in all_picks:
            total = player_season_pts.get((pick.player_id, pick.season_id), D(0))
            pick_records.append({
                "player": pick.player.full_name,
                "manager": mgr_name(pick.team) if pick.team else "Unknown",
                "year": pick.season.year,
                "season_id": pick.season_id,
                "round": pick.round,
                "pick": pick.pick,
                "season_pts": total,
            })

        draft_pick_seasons = sorted({r["year"] for r in pick_records}, reverse=True)
        draft_pick_managers = sorted({r["manager"] for r in pick_records if r["manager"] != "Unknown"})

        # Best per round (across all seasons/managers)
        by_round = defaultdict(list)
        for r in pick_records:
            by_round[r["round"]].append(r)
        best_draft_picks = [
            max(picks, key=lambda x: x["season_pts"])
            for picks in sorted(by_round.values(), key=lambda p: p[0]["round"])
        ]
        worst_draft_picks = [
            min(picks, key=lambda x: x["season_pts"])
            for picks in sorted(by_round.values(), key=lambda p: p[0]["round"])
        ]

        # ── Most prized keepers — best player season after being kept ──
        all_keeper_records = list(
            KeeperRecord.objects.select_related("season", "team__manager", "player").all()
        )
        keeper_season_rows = []
        for kr in all_keeper_records:
            pts = player_season_pts.get((kr.player_id, kr.season_id), D(0))
            keeper_season_rows.append({
                "player": kr.player.full_name,
                "manager": mgr_name(kr.team),
                "year": kr.season.year,
                "season_pts": pts,
            })
        prized_keepers = sorted(keeper_season_rows, key=lambda x: x["season_pts"], reverse=True)[:15]

    return render(request, "leaguehub/hall.html", {
        # HOF Season
        "top_points_for": top_points_for,
        "top_wins": top_wins,
        "best_defense": best_defense,
        "most_championships": most_championships,
        "most_last_place": most_last_place,
        "highest_pf_no_title": highest_pf_no_title,
        # HOF Week
        "highest_score": highest_score,
        "biggest_margin": biggest_margin,
        "highest_losing_score": highest_losing_score,
        "longest_win_streak": longest_win_streak,
        "best_playoff_score": best_playoff_score,
        # HOS Season
        "worst_points_for": worst_points_for,
        "most_losses": most_losses,
        "worst_defense": worst_defense,
        "highest_pf_no_playoffs": highest_pf_no_playoffs,
        # HOS Week
        "lowest_score": lowest_score,
        "worst_margin": worst_margin,
        "longest_loss_streak": longest_loss_streak,
        "lowest_playoff_score": lowest_playoff_score,
        # Cumulative points
        "cumulative_all": cumulative_all,
        "cumulative_playoff": cumulative_playoff,
        "cumulative_regular": cumulative_regular,
        # Bro vs Bro
        "bro_vs_bro": bro_vs_bro,
        # Keeper Legends
        "keeper_legends": keeper_legends,
        "team_spread": team_spread,
        # Meta
        "has_matchup_data": has_matchup_data,
        "has_player_data": has_player_data,
        "bench_disasters": bench_disasters,
        "best_player_game": best_player_game,
        "best_draft_picks": best_draft_picks,
        "worst_draft_picks": worst_draft_picks,
        "draft_pick_seasons": draft_pick_seasons,
        "draft_pick_managers": draft_pick_managers,
        "prized_keepers": prized_keepers,
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