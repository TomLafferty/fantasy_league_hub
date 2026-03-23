from decimal import Decimal
from .models import Champion, Player, RosterSnapshot, Season, Standing, Team


def sync_standings_from_yahoo(season: Season, payload: dict):
    fantasy_content = payload.get("fantasy_content", {})
    league = fantasy_content.get("league", {})
    standings_data = league.get("standings", {})
    teams_data = standings_data.get("teams", {})

    team_entries = []
    if isinstance(teams_data, dict):
        for value in teams_data.values():
            if isinstance(value, dict) and "team_key" in value:
                team_entries.append(value)

    for entry in team_entries:
        team_name = entry.get("name", "Unknown Team")
        team_key = entry.get("team_key", "")
        team_standings = entry.get("team_standings", {})
        outcomes = team_standings.get("outcome_totals", {})

        team, _ = Team.objects.get_or_create(
            season=season,
            name=team_name,
            defaults={"yahoo_team_key": team_key},
        )

        if not team.yahoo_team_key and team_key:
            team.yahoo_team_key = team_key
            team.save(update_fields=["yahoo_team_key"])

        Standing.objects.update_or_create(
            season=season,
            team=team,
            defaults={
                "rank": int(team_standings.get("rank", 999)),
                "wins": int(outcomes.get("wins", 0)),
                "losses": int(outcomes.get("losses", 0)),
                "ties": int(outcomes.get("ties", 0)),
                "points_for": Decimal(str(entry.get("team_points", {}).get("total", "0"))),
                "points_against": Decimal("0.00"),
                "final_place": int(team_standings.get("rank", 999)),
            },
        )

    top = Standing.objects.filter(season=season).order_by("rank").first()
    if top:
        Champion.objects.update_or_create(
            season=season,
            defaults={"team": top.team},
        )


def sync_final_roster_from_yahoo(season: Season, team: Team, payload: dict):
    fantasy_content = payload.get("fantasy_content", {})
    team_data = fantasy_content.get("team", {})
    roster = team_data.get("roster", {})
    players = roster.get("players", {})

    player_entries = []
    if isinstance(players, dict):
        for value in players.values():
            if isinstance(value, dict) and "player_key" in value:
                player_entries.append(value)

    for entry in player_entries:
        name_info = entry.get("name", {})
        full_name = (
            name_info.get("full")
            or f"{name_info.get('first', '')} {name_info.get('last', '')}".strip()
            or "Unknown Player"
        )

        player, _ = Player.objects.get_or_create(
            yahoo_player_key=entry.get("player_key"),
            defaults={
                "yahoo_player_id": str(entry.get("player_id", "")),
                "full_name": full_name,
                "nfl_team": entry.get("editorial_team_abbr", ""),
                "primary_position": entry.get("display_position", ""),
            },
        )

        RosterSnapshot.objects.update_or_create(
            season=season,
            team=team,
            player=player,
            week=0,
            defaults={"is_final_roster": True},
        )