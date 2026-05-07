"""Shared streak computation logic used by both FFUPA and BEAVER hottest/coldest views."""
from datetime import date, timedelta


def week_to_monday(year, week):
    """Return the Monday of NFL week `week` for the given `year`."""
    base = date(year, 9, 5)
    week1_monday = base - timedelta(days=base.weekday())
    return week1_monday + timedelta(weeks=week - 1)


def best_streak_games(results, target):
    """Return the games in the longest consecutive streak of `target` result ('W' or 'L')."""
    best_start, best_len = 0, 0
    cur_start, cur_len = 0, 0
    for i, g in enumerate(results):
        if g["result"] == target:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
        else:
            cur_len = 0
    return results[best_start: best_start + best_len]


def compute_all_time_records(manager_results):
    """
    Given a dict of manager_name -> [{"year", "week", "result", "score", "opponent_score"}],
    return (all_time_hot, all_time_cold) dicts describing the longest ever W and L streaks.
    """
    today = date.today()
    all_time_hot = None
    all_time_cold = None

    for mgr_name_str, results in manager_results.items():
        for target, current_record in [("W", all_time_hot), ("L", all_time_cold)]:
            games = best_streak_games(results, target)
            if not games:
                continue
            count = len(games)
            if current_record is None or count > current_record["streak_count"]:
                for g in games:
                    g.setdefault("margin", round(abs(g["score"] - g["opponent_score"]), 2))
                avg = round(sum(g["margin"] for g in games) / count, 2)
                is_active = (
                    games[-1]["year"] == results[-1]["year"]
                    and games[-1]["week"] == results[-1]["week"]
                )
                first_monday = week_to_monday(games[0]["year"], games[0]["week"])
                end_date = today if is_active else week_to_monday(games[-1]["year"], games[-1]["week"])
                record = {
                    "manager": mgr_name_str,
                    "streak_count": count,
                    "avg_margin": avg,
                    "first_year": games[0]["year"],
                    "first_week": games[0]["week"],
                    "last_year": games[-1]["year"],
                    "last_week": games[-1]["week"],
                    "streak_days": (end_date - first_monday).days,
                    "is_active": is_active,
                }
                if target == "W":
                    all_time_hot = record
                else:
                    all_time_cold = record

    return all_time_hot, all_time_cold


def compute_active_streaks(manager_results):
    """
    Given a dict of manager_name -> [{"year", "week", "result", "score", "opponent_score"}],
    return a list of active-streak dicts (the current ongoing streak for each manager).
    """
    today = date.today()
    streaks = []

    for mgr_name_str, results in manager_results.items():
        if not results:
            continue
        latest_result = results[-1]
        current_result_type = latest_result["result"]

        streak_games = [latest_result]
        for i in range(len(results) - 2, -1, -1):
            if results[i]["result"] == current_result_type:
                streak_games.insert(0, results[i])
            else:
                break

        for g in streak_games:
            g["margin"] = round(abs(g["score"] - g["opponent_score"]), 2)
        avg_margin = round(sum(g["margin"] for g in streak_games) / len(streak_games), 2)

        first_game = streak_games[0]
        streak_start_date = week_to_monday(first_game["year"], first_game["week"])
        streak_days = (today - streak_start_date).days

        streaks.append({
            "manager": mgr_name_str,
            "streak_type": current_result_type,
            "streak_count": len(streak_games),
            "streak_games": streak_games,
            "avg_margin": avg_margin,
            "streak_days": streak_days,
        })

    return streaks
