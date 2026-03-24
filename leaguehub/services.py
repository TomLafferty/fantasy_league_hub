from decimal import Decimal
from .models import Champion, DraftPick, KeeperRecord, Matchup, ManagerProfile, Player, RosterSnapshot, Season, Standing, Team


def _extract_team_meta(team_meta_list: list) -> dict:
    """Flatten Yahoo's team metadata list-of-dicts into a single dict."""
    result = {}
    for item in team_meta_list:
        if isinstance(item, dict):
            result.update(item)
        elif isinstance(item, list):
            for sub in item:
                if isinstance(sub, dict):
                    result.update(sub)
    return result


def _sync_manager_profile(team: Team, meta: dict):
    """Create or update a ManagerProfile from Yahoo team metadata and link it to the team."""
    managers = meta.get("managers", [])
    manager_data = None
    # Yahoo returns managers as a list: [{"manager": {...}}]
    if isinstance(managers, list):
        for item in managers:
            if isinstance(item, dict) and "manager" in item:
                manager_data = item["manager"]
                break
    # Older API versions returned a dict: {"0": {"manager": {...}}}
    elif isinstance(managers, dict):
        for v in managers.values():
            if isinstance(v, dict) and "manager" in v:
                manager_data = v["manager"]
                break

    if not manager_data:
        return

    guid = manager_data.get("guid", "")
    nickname = manager_data.get("nickname", "")
    if not guid and not nickname:
        return

    if guid:
        profile, _ = ManagerProfile.objects.update_or_create(
            yahoo_guid=guid,
            defaults={"display_name": nickname or guid},
        )
    else:
        profile, _ = ManagerProfile.objects.get_or_create(
            display_name=nickname,
            defaults={"yahoo_guid": ""},
        )

    if team.manager_id != profile.pk:
        team.manager = profile
        team.save(update_fields=["manager"])


def sync_standings_from_yahoo(season: Season, payload: dict):
    # Yahoo returns: fantasy_content.league = [metadata_dict, resources_dict]
    league_list = payload.get("fantasy_content", {}).get("league", [])
    if len(league_list) < 2:
        return

    resources = league_list[1]
    standings_list = resources.get("standings", [{}])
    teams_data = standings_list[0].get("teams", {}) if standings_list else {}

    for key, value in teams_data.items():
        if key == "count" or not isinstance(value, dict):
            continue

        # Each entry: {"team": [meta_list, {"team_standings": {...}}]}
        team_wrapper = value.get("team", [])
        if len(team_wrapper) < 2:
            continue

        meta = _extract_team_meta(team_wrapper[0] if isinstance(team_wrapper[0], list) else [team_wrapper[0]])

        # team_wrapper has 3 elements: [meta_list, {team_points}, {team_standings}]
        # Search rather than assume fixed indices
        team_standings = {}
        team_points = {}
        for item in team_wrapper[1:]:
            if isinstance(item, dict):
                if "team_standings" in item:
                    team_standings = item["team_standings"]
                if "team_points" in item:
                    team_points = item["team_points"]

        outcomes = team_standings.get("outcome_totals", {})

        team_name = meta.get("name", "Unknown Team")
        team_key = meta.get("team_key", "")

        team, _ = Team.objects.get_or_create(
            season=season,
            name=team_name,
            defaults={"yahoo_team_key": team_key},
        )

        if not team.yahoo_team_key and team_key:
            team.yahoo_team_key = team_key
            team.save(update_fields=["yahoo_team_key"])

        _sync_manager_profile(team, meta)

        Standing.objects.update_or_create(
            season=season,
            team=team,
            defaults={
                "rank": int(team_standings.get("rank", 999)),
                "wins": int(outcomes.get("wins", 0)),
                "losses": int(outcomes.get("losses", 0)),
                "ties": int(outcomes.get("ties", 0)),
                "points_for": Decimal(str(team_points.get("total", "0") or "0")),
                "points_against": Decimal(str(team_standings.get("points_against", "0") or "0")),
            },
        )


def sync_keepers_from_yahoo(season: Season, payload: dict) -> int:
    """Import keepers from /league/{key}/players;status=K/ownership. Returns count created."""
    league_list = payload.get("fantasy_content", {}).get("league", [])
    if len(league_list) < 2:
        return 0

    players_data = league_list[1].get("players", {})
    if isinstance(players_data, list):
        players_data = players_data[0] if players_data else {}

    count = 0
    for key, value in players_data.items():
        if key == "count" or not isinstance(value, dict):
            continue

        player_wrapper = value.get("player", [])
        if not player_wrapper:
            continue

        player_meta = _extract_team_meta(
            player_wrapper[0] if isinstance(player_wrapper[0], list) else [player_wrapper[0]]
        )

        # Ownership is in subsequent elements of player_wrapper
        owner_team_key = ""
        for item in player_wrapper[1:]:
            if isinstance(item, dict) and "ownership" in item:
                ownership = item["ownership"]
                if isinstance(ownership, list):
                    ownership = ownership[0] if ownership else {}
                owner_team_key = ownership.get("owner_team_key", "")
                break

        if not owner_team_key:
            continue

        team = Team.objects.filter(season=season, yahoo_team_key=owner_team_key).first()
        if not team:
            continue

        yahoo_player_key = player_meta.get("player_key")
        player = Player.objects.filter(yahoo_player_key=yahoo_player_key).first()
        if not player:
            name_info = player_meta.get("name", {})
            full_name = (
                name_info.get("full") if isinstance(name_info, dict) else str(name_info)
            ) or "Unknown Player"
            player, _ = Player.objects.get_or_create(
                yahoo_player_key=yahoo_player_key,
                defaults={
                    "yahoo_player_id": str(player_meta.get("player_id", "")),
                    "full_name": full_name,
                    "nfl_team": player_meta.get("editorial_team_abbr", ""),
                    "primary_position": player_meta.get("display_position", ""),
                },
            )

        _, created = KeeperRecord.objects.get_or_create(
            season=season,
            team=team,
            player=player,
            defaults={"source": "yahoo"},
        )
        if created:
            count += 1

    return count


def sync_draft_picks_from_yahoo(season: Season, payload: dict) -> int:
    """Store all draft picks for a season. Returns count created."""
    league_list = payload.get("fantasy_content", {}).get("league", [])
    if len(league_list) < 2:
        return 0

    draft_results = league_list[1].get("draft_results", {})
    if isinstance(draft_results, list):
        draft_results = draft_results[0] if draft_results else {}

    count = 0
    for key, value in draft_results.items():
        if key == "count" or not isinstance(value, dict):
            continue

        pick_data = value.get("draft_result", {})
        if isinstance(pick_data, list):
            pick_data = pick_data[0] if pick_data else {}

        round_num = int(pick_data.get("round", 0))
        pick_num = int(pick_data.get("pick", 0))
        if not round_num or not pick_num:
            continue

        team = Team.objects.filter(season=season, yahoo_team_key=pick_data.get("team_key", "")).first()
        player = Player.objects.filter(yahoo_player_key=pick_data.get("player_key", "")).first()

        _, created = DraftPick.objects.get_or_create(
            season=season,
            round=round_num,
            pick=pick_num,
            defaults={"team": team, "player": player},
        )
        if created:
            count += 1

    return count


def sync_keepers_from_draft(season: Season, payload: dict) -> int:
    """Import keeper picks from draft results. Returns count of keepers created."""
    league_list = payload.get("fantasy_content", {}).get("league", [])
    if len(league_list) < 2:
        return 0

    draft_results = league_list[1].get("draft_results", {})
    if isinstance(draft_results, list):
        draft_results = draft_results[0] if draft_results else {}

    count = 0
    for key, value in draft_results.items():
        if key == "count" or not isinstance(value, dict):
            continue

        pick = value.get("draft_result", {})
        if isinstance(pick, list):
            pick = pick[0] if pick else {}

        if pick.get("type") != "keeper":
            continue

        team_key = pick.get("team_key", "")
        player_key = pick.get("player_key", "")
        if not team_key or not player_key:
            continue

        team = Team.objects.filter(season=season, yahoo_team_key=team_key).first()
        player = Player.objects.filter(yahoo_player_key=player_key).first()
        if not team or not player:
            continue

        _, created = KeeperRecord.objects.get_or_create(
            season=season,
            team=team,
            player=player,
            defaults={"source": "yahoo"},
        )
        if created:
            count += 1

    return count


def sync_champion_from_standings(season: Season):
    """Mark the rank-1 team as champion. Only call this after the season is complete."""
    top = Standing.objects.filter(season=season, rank=1).select_related("team").first()
    if top:
        Champion.objects.update_or_create(season=season, defaults={"team": top.team})


def sync_league_metadata_from_yahoo(season: Season, payload: dict):
    """Update season name and logo from the league info endpoint."""
    league_list = payload.get("fantasy_content", {}).get("league", [])
    if not league_list:
        return
    meta = league_list[0] if isinstance(league_list[0], dict) else {}
    update_fields = []
    yahoo_name = meta.get("name", "")
    if yahoo_name:
        formatted_name = f"{season.year} {yahoo_name}"
        if season.name != formatted_name:
            season.name = formatted_name
            update_fields.append("name")
    logo_url = meta.get("logo_url", "")
    if logo_url and season.logo_url != logo_url:
        season.logo_url = logo_url
        update_fields.append("logo_url")
    if update_fields:
        season.save(update_fields=update_fields)




def sync_final_roster_from_yahoo(season: Season, team: Team, payload: dict) -> int:
    # Yahoo returns: fantasy_content.team = [meta_list, resources_dict]
    team_list = payload.get("fantasy_content", {}).get("team", [])
    if len(team_list) < 2:
        return 0

    roster = team_list[1].get("roster", {})
    # Yahoo nests players under roster["players"] or roster["0"]["players"]
    players_data = roster.get("players") or roster.get("0", {}).get("players", {})
    if isinstance(players_data, list):
        players_data = players_data[0] if players_data else {}

    count = 0
    for key, value in players_data.items():
        if key == "count" or not isinstance(value, dict):
            continue

        # Each entry: {"player": [meta_list, extra_dict]}
        player_wrapper = value.get("player", [])
        if not player_wrapper:
            continue

        meta = _extract_team_meta(player_wrapper[0] if isinstance(player_wrapper[0], list) else [player_wrapper[0]])

        name_info = meta.get("name", {})
        if isinstance(name_info, dict):
            full_name = (
                name_info.get("full")
                or f"{name_info.get('first', '')} {name_info.get('last', '')}".strip()
                or "Unknown Player"
            )
        else:
            full_name = str(name_info) or "Unknown Player"

        player, _ = Player.objects.get_or_create(
            yahoo_player_key=meta.get("player_key"),
            defaults={
                "yahoo_player_id": str(meta.get("player_id", "")),
                "full_name": full_name,
                "nfl_team": meta.get("editorial_team_abbr", ""),
                "primary_position": meta.get("display_position", ""),
            },
        )

        RosterSnapshot.objects.update_or_create(
            season=season,
            team=team,
            player=player,
            week=0,
            defaults={"is_final_roster": True},
        )
        count += 1

    return count


def sync_matchups_from_yahoo(season: Season, week: int, payload: dict) -> int:
    """Store matchups from a weekly scoreboard response. Returns count stored."""
    league_list = payload.get("fantasy_content", {}).get("league", [])
    if len(league_list) < 2:
        return 0

    scoreboard_wrapper = league_list[1].get("scoreboard", {})
    if isinstance(scoreboard_wrapper, list):
        scoreboard_wrapper = scoreboard_wrapper[0] if scoreboard_wrapper else {}

    # Yahoo nests matchups under scoreboard["0"]["matchups"], not scoreboard["matchups"]
    inner = scoreboard_wrapper.get("0", scoreboard_wrapper)
    matchups_data = inner.get("matchups", {})
    if isinstance(matchups_data, list):
        matchups_data = matchups_data[0] if matchups_data else {}

    count = 0
    for key, value in matchups_data.items():
        if key == "count" or not isinstance(value, dict):
            continue

        # Yahoo returns matchup as a dict, not a list
        matchup_data = value.get("matchup", {})
        if isinstance(matchup_data, list):
            matchup_data = matchup_data[0] if matchup_data else {}
        if not matchup_data:
            continue

        is_playoff = str(matchup_data.get("is_playoffs", "0")) == "1"
        is_consolation = str(matchup_data.get("is_consolation", "0")) == "1"
        # Teams are nested under matchup["0"]["teams"], not matchup["teams"]
        matchup_inner = matchup_data.get("0", matchup_data)
        teams_data = matchup_inner.get("teams", {})

        if not teams_data:
            continue

        team_entries = []
        for tkey, tvalue in teams_data.items():
            if tkey == "count" or not isinstance(tvalue, dict):
                continue
            team_wrapper = tvalue.get("team", [])
            if not team_wrapper:
                continue

            meta = _extract_team_meta(
                team_wrapper[0] if isinstance(team_wrapper[0], list) else [team_wrapper[0]]
            )
            score = Decimal("0")
            for item in team_wrapper[1:]:
                if isinstance(item, dict) and "team_points" in item:
                    tp = item["team_points"]
                    if isinstance(tp, list):
                        tp = tp[0] if tp else {}
                    score = Decimal(str(tp.get("total", "0") or "0"))
                    break

            team_key = meta.get("team_key", "")
            team = Team.objects.filter(season=season, yahoo_team_key=team_key).first()
            if team:
                team_entries.append((team, score))

        if len(team_entries) == 2:
            team_a, score_a = team_entries[0]
            team_b, score_b = team_entries[1]
            # Normalize order so unique_together works regardless of API ordering
            if team_a.pk > team_b.pk:
                team_a, team_b = team_b, team_a
                score_a, score_b = score_b, score_a

            Matchup.objects.update_or_create(
                season=season,
                week=week,
                team_a=team_a,
                team_b=team_b,
                defaults={
                    "score_a": score_a,
                    "score_b": score_b,
                    "is_playoff": is_playoff,
                    "is_consolation": is_consolation,
                },
            )
            count += 1

    return count