from django.test import TestCase

from .models import KeeperRecord, Player, Season, Team
from .services import sync_keepers_from_draft, sync_keepers_from_yahoo


def make_season(year=2025):
    return Season.objects.create(year=year, name=f"{year} F.F.U.P.A.")


def make_team(season, name="Do Knox Cum", yahoo_team_key="461.t.1"):
    return Team.objects.create(season=season, name=name, yahoo_team_key=yahoo_team_key)


def make_player(key="461.p.30977", name="Tee Higgins"):
    return Player.objects.create(yahoo_player_key=key, full_name=name)


def _yahoo_draft_results_payload(picks):
    """Build a fake Yahoo /draftresults response with the given list of pick dicts."""
    draft_results = {str(i): {"draft_result": pick} for i, pick in enumerate(picks)}
    draft_results["count"] = len(picks)
    return {"fantasy_content": {"league": [{}, {"draft_results": draft_results}]}}


def _yahoo_keepers_payload(players):
    """
    Build a fake Yahoo /players;status=K/ownership response.
    Each entry in players: {"player_key": ..., "player_id": ..., "name": ..., "owner_team_key": ...}
    """
    players_data = {}
    for i, p in enumerate(players):
        players_data[str(i)] = {
            "player": [
                [
                    {"player_key": p["player_key"]},
                    {"player_id": p.get("player_id", "")},
                    {"name": {"full": p["name"]}},
                    {"display_position": p.get("position", "WR")},
                    {"editorial_team_abbr": p.get("nfl_team", "")},
                ],
                {"ownership": {"owner_team_key": p["owner_team_key"]}},
            ]
        }
    players_data["count"] = len(players)
    return {"fantasy_content": {"league": [{}, {"players": players_data}]}}


# ---------------------------------------------------------------------------
# sync_keepers_from_draft
# ---------------------------------------------------------------------------

class SyncKeepersFromDraftTests(TestCase):

    def setUp(self):
        self.season = make_season(2025)
        self.team = make_team(self.season)
        self.player = make_player("461.p.9001", "Tee Higgins")

    def test_offline_draft_returns_zero(self):
        """Offline drafts have no draft results at all — should return 0 keepers."""
        payload = {"fantasy_content": {"league": [{}, {"draft_results": {"count": 0}}]}}
        count = sync_keepers_from_draft(self.season, payload)
        self.assertEqual(count, 0)
        self.assertEqual(KeeperRecord.objects.count(), 0)

    def test_online_draft_no_keeper_picks(self):
        """Online draft with only regular picks (no type=keeper) — should return 0."""
        picks = [
            {"round": "1", "pick": "1", "team_key": self.team.yahoo_team_key,
             "player_key": self.player.yahoo_player_key, "type": "regular"},
        ]
        payload = _yahoo_draft_results_payload(picks)
        count = sync_keepers_from_draft(self.season, payload)
        self.assertEqual(count, 0)

    def test_online_draft_with_keeper_picks(self):
        """Online draft with type=keeper picks — creates KeeperRecord entries."""
        picks = [
            {"round": "1", "pick": "1", "team_key": self.team.yahoo_team_key,
             "player_key": self.player.yahoo_player_key, "type": "keeper"},
        ]
        payload = _yahoo_draft_results_payload(picks)
        count = sync_keepers_from_draft(self.season, payload)
        self.assertEqual(count, 1)
        self.assertTrue(
            KeeperRecord.objects.filter(season=self.season, team=self.team, player=self.player).exists()
        )

    def test_idempotent(self):
        """Running twice does not duplicate records."""
        picks = [
            {"round": "1", "pick": "1", "team_key": self.team.yahoo_team_key,
             "player_key": self.player.yahoo_player_key, "type": "keeper"},
        ]
        payload = _yahoo_draft_results_payload(picks)
        sync_keepers_from_draft(self.season, payload)
        count = sync_keepers_from_draft(self.season, payload)
        self.assertEqual(count, 0)  # second run: already exists, not created again
        self.assertEqual(KeeperRecord.objects.count(), 1)


# ---------------------------------------------------------------------------
# sync_keepers_from_yahoo (players;status=K/ownership)
# ---------------------------------------------------------------------------

class SyncKeepersFromYahooTests(TestCase):

    def setUp(self):
        self.season = make_season(2025)
        self.team = make_team(self.season, yahoo_team_key="461.t.1")
        self.higgins = make_player("461.p.9001", "Tee Higgins")
        self.njoku = make_player("461.p.9002", "David Njoku")

    def test_creates_records_when_player_still_on_team(self):
        """Player marked K and still owned by the same team — record is created."""
        payload = _yahoo_keepers_payload([
            {"player_key": "461.p.9001", "name": "Tee Higgins", "owner_team_key": "461.t.1"},
        ])
        count = sync_keepers_from_yahoo(self.season, payload)
        self.assertEqual(count, 1)
        self.assertTrue(KeeperRecord.objects.filter(player=self.higgins).exists())

    def test_missing_when_player_traded_or_dropped(self):
        """
        This is the offline-draft bug: player was kept by team 461.t.1 at the start
        of the season but was traded mid-season. Yahoo now reports owner_team_key=""
        or a different team. sync_keepers_from_yahoo silently creates NO record.
        """
        payload = _yahoo_keepers_payload([
            # owner_team_key is empty — player was dropped after being kept
            {"player_key": "461.p.9001", "name": "Tee Higgins", "owner_team_key": ""},
            # owner_team_key points to a different team — player was traded
            {"player_key": "461.p.9002", "name": "David Njoku", "owner_team_key": "461.t.99"},
        ])
        count = sync_keepers_from_yahoo(self.season, payload)
        self.assertEqual(count, 0, (
            "sync_keepers_from_yahoo creates 0 records when keeper players are no longer "
            "owned by their original team — this is the known limitation for offline "
            "draft leagues where players may be dropped or traded after keeper declaration."
        ))
        self.assertFalse(KeeperRecord.objects.filter(player=self.higgins).exists())
        self.assertFalse(KeeperRecord.objects.filter(player=self.njoku).exists())

    def test_empty_payload(self):
        payload = {"fantasy_content": {"league": [{}, {"players": {"count": 0}}]}}
        count = sync_keepers_from_yahoo(self.season, payload)
        self.assertEqual(count, 0)
