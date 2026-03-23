from decimal import Decimal
from .models import ManagerProfile, Player, RosterSnapshot, Season, Standing, Team


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
    managers = meta.get("managers", {})
    # Yahoo returns managers as {"0": {"manager": {...}}, ...}
    manager_data = None
    if isinstance(managers, dict):
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
        team_standings = team_wrapper[1].get("team_standings", {})
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

        team_points = team_wrapper[1].get("team_points", {})

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


def sync_final_roster_from_yahoo(season: Season, team: Team, payload: dict):
    # Yahoo returns: fantasy_content.team = [meta_list, resources_dict]
    team_list = payload.get("fantasy_content", {}).get("team", [])
    if len(team_list) < 2:
        return

    players_data = team_list[1].get("roster", {}).get("players", {})

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