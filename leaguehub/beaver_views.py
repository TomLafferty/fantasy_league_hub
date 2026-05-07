from collections import defaultdict

from django.shortcuts import get_object_or_404, render

from .models import (
    SleeperChampion,
    SleeperDraftPick,
    SleeperLeague,
    SleeperMatchup,
    SleeperPlayer,
    SleeperRoster,
    SleeperTransaction,
    SleeperTradedPick,
)
from .streak_utils import compute_active_streaks, compute_all_time_records


def _current_league():
    return SleeperLeague.objects.filter(is_current=True).first()


def _player_map(ids):
    return {p.sleeper_id: p for p in SleeperPlayer.objects.filter(sleeper_id__in=ids)}


def _roster_map(league):
    if not league:
        return {}
    return {r.roster_id: r for r in SleeperRoster.objects.filter(league=league).select_related("manager")}


# ── HOME ──────────────────────────────────────────────────────────────────────

def beaver_home(request):
    league = _current_league()

    leader = None
    last_place = None
    recent_txns = []
    player_map = {}
    roster_map = {}

    if league:
        rosters = list(SleeperRoster.objects.filter(league=league).select_related("manager").order_by("rank", "roster_id"))
        if rosters:
            leader = rosters[0]
            last_place = rosters[-1]

        recent_txns = list(
            SleeperTransaction.objects.filter(league=league).order_by("-created_at")[:15]
        )
        all_ids = set()
        for txn in recent_txns:
            all_ids.update((txn.adds or {}).keys())
            all_ids.update((txn.drops or {}).keys())
        player_map = _player_map(all_ids)
        roster_map = _roster_map(league)

    return render(request, "leaguehub/beaver/home.html", {
        "league": league,
        "leader": leader,
        "last_place": last_place,
        "recent_txns": recent_txns,
        "player_map": player_map,
        "roster_map": roster_map,
    })


# ── STANDINGS ─────────────────────────────────────────────────────────────────

def beaver_standings(request):
    all_leagues = SleeperLeague.objects.order_by("-season_year")
    selected_id = request.GET.get("league")
    if selected_id:
        league = get_object_or_404(SleeperLeague, id=selected_id)
    else:
        league = all_leagues.filter(is_current=True).first() or all_leagues.first()

    rosters = (
        SleeperRoster.objects.filter(league=league)
        .select_related("manager")
        .order_by("rank", "roster_id")
        if league else SleeperRoster.objects.none()
    )
    return render(request, "leaguehub/beaver/standings.html", {
        "all_leagues": all_leagues,
        "league": league,
        "rosters": rosters,
    })


# ── ROSTERS ───────────────────────────────────────────────────────────────────

_POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "LB", "DL", "DB", "DEF", "FLEX", "IDP_FLEX"]


def beaver_rosters(request):
    league = _current_league()
    roster_data = []

    if league:
        rosters = list(
            SleeperRoster.objects.filter(league=league)
            .select_related("manager")
            .order_by("rank", "roster_id")
        )
        all_ids = set()
        for r in rosters:
            all_ids.update(r.players or [])
            all_ids.update(r.taxi_players or [])
            all_ids.update(r.reserve_players or [])
        player_map = _player_map(all_ids)

        for r in rosters:
            taxi_set = set(r.taxi_players or [])
            reserve_set = set(r.reserve_players or [])
            main = sorted(
                [{"player": player_map.get(pid), "pid": pid}
                 for pid in (r.players or []) if pid not in taxi_set and pid not in reserve_set],
                key=lambda x: _POSITION_ORDER.index(x["player"].position) if x["player"] and x["player"].position in _POSITION_ORDER else 99,
            )
            taxi = [{"player": player_map.get(pid), "pid": pid} for pid in (r.taxi_players or [])]
            reserve = [{"player": player_map.get(pid), "pid": pid} for pid in (r.reserve_players or [])]
            roster_data.append({"roster": r, "main": main, "taxi": taxi, "reserve": reserve})

    return render(request, "leaguehub/beaver/rosters.html", {
        "league": league,
        "roster_data": roster_data,
    })


# ── TRANSACTIONS ──────────────────────────────────────────────────────────────

def beaver_transactions(request):
    all_leagues = SleeperLeague.objects.order_by("-season_year")
    selected_id = request.GET.get("league")
    if selected_id:
        league = get_object_or_404(SleeperLeague, id=selected_id)
    else:
        league = all_leagues.filter(is_current=True).first() or all_leagues.first()

    txns = list(
        SleeperTransaction.objects.filter(league=league).order_by("-created_at")[:200]
        if league else []
    )
    all_ids = set()
    for txn in txns:
        all_ids.update((txn.adds or {}).keys())
        all_ids.update((txn.drops or {}).keys())
    player_map = _player_map(all_ids)
    roster_map = _roster_map(league)

    return render(request, "leaguehub/beaver/transactions.html", {
        "all_leagues": all_leagues,
        "league": league,
        "txns": txns,
        "player_map": player_map,
        "roster_map": roster_map,
    })


# ── TRADED PICKS ──────────────────────────────────────────────────────────────

def beaver_picks(request):
    league = _current_league()
    picks = (
        SleeperTradedPick.objects.filter(league=league).order_by("season_year", "round", "roster_id")
        if league else SleeperTradedPick.objects.none()
    )
    roster_map = _roster_map(league)

    # Group picks by season_year
    grouped = defaultdict(list)
    for p in picks:
        grouped[p.season_year].append(p)
    grouped_picks = sorted(grouped.items())

    return render(request, "leaguehub/beaver/picks.html", {
        "league": league,
        "grouped_picks": grouped_picks,
        "roster_map": roster_map,
    })


# ── DRAFT HISTORY ─────────────────────────────────────────────────────────────

def beaver_drafts(request):
    all_leagues = SleeperLeague.objects.order_by("-season_year")
    selected_id = request.GET.get("league")
    if selected_id:
        league = get_object_or_404(SleeperLeague, id=selected_id)
    else:
        league = all_leagues.filter(is_current=True).first() or all_leagues.first()

    draft_picks = (
        SleeperDraftPick.objects.filter(league=league)
        .select_related("player")
        .order_by("round", "pick_no")
        if league else SleeperDraftPick.objects.none()
    )
    roster_map = _roster_map(league)

    # Group by round
    by_round = defaultdict(list)
    for p in draft_picks:
        by_round[p.round].append(p)
    rounds = sorted(by_round.items())

    return render(request, "leaguehub/beaver/drafts.html", {
        "all_leagues": all_leagues,
        "league": league,
        "rounds": rounds,
        "roster_map": roster_map,
    })


# ── HALL OF FAME ──────────────────────────────────────────────────────────────

def beaver_hall(request):
    champions = (
        SleeperChampion.objects
        .select_related("league", "roster__manager")
        .order_by("-league__season_year")
    )
    return render(request, "leaguehub/beaver/hall.html", {"champions": champions})


# ── HOTTEST & COLDEST ─────────────────────────────────────────────────────────

def beaver_hottest(request):
    league = _current_league()

    if not league:
        return render(request, "leaguehub/beaver/hottest.html", {
            "hottest": None, "coldest": None, "all_time_hot": None, "all_time_cold": None, "league": None,
        })

    all_matchups = list(
        SleeperMatchup.objects.filter(league=league)
        .select_related("roster__manager")
        .order_by("week", "matchup_id")
    )

    if not all_matchups:
        return render(request, "leaguehub/beaver/hottest.html", {
            "hottest": None, "coldest": None, "all_time_hot": None, "all_time_cold": None, "league": league,
        })

    # Pair matchup rows by (week, matchup_id) to derive W/L
    pairs = defaultdict(list)
    for m in all_matchups:
        pairs[(m.week, m.matchup_id)].append(m)

    manager_results = defaultdict(list)
    for (week, _mid), entries in sorted(pairs.items()):
        if len(entries) != 2:
            continue
        a, b = entries
        name_a = a.roster.manager.display_name if a.roster.manager else str(a.roster.roster_id)
        name_b = b.roster.manager.display_name if b.roster.manager else str(b.roster.roster_id)
        year = league.season_year
        if a.points > b.points:
            manager_results[name_a].append({"year": year, "week": week, "result": "W", "score": float(a.points), "opponent_score": float(b.points)})
            manager_results[name_b].append({"year": year, "week": week, "result": "L", "score": float(b.points), "opponent_score": float(a.points)})
        elif b.points > a.points:
            manager_results[name_a].append({"year": year, "week": week, "result": "L", "score": float(a.points), "opponent_score": float(b.points)})
            manager_results[name_b].append({"year": year, "week": week, "result": "W", "score": float(b.points), "opponent_score": float(a.points)})

    all_time_hot, all_time_cold = compute_all_time_records(manager_results)
    streaks = compute_active_streaks(manager_results)

    hot_streaks = [s for s in streaks if s["streak_type"] == "W"]
    cold_streaks = [s for s in streaks if s["streak_type"] == "L"]

    return render(request, "leaguehub/beaver/hottest.html", {
        "league": league,
        "hottest": max(hot_streaks, key=lambda x: x["streak_count"]) if hot_streaks else None,
        "coldest": max(cold_streaks, key=lambda x: x["streak_count"]) if cold_streaks else None,
        "all_time_hot": all_time_hot,
        "all_time_cold": all_time_cold,
    })
