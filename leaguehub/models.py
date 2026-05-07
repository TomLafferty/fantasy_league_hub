from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Season(models.Model):
    year = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=100, blank=True)
    logo_url = models.URLField(max_length=500, blank=True)
    yahoo_game_key = models.CharField(max_length=50, blank=True)
    yahoo_league_key = models.CharField(max_length=100, blank=True)
    is_current = models.BooleanField(default=False)
    keeper_deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-year"]

    def __str__(self):
        return self.name or str(self.year)

    def save(self, *args, **kwargs):
        if self.is_current:
            Season.objects.exclude(pk=self.pk).filter(is_current=True).update(is_current=False)
        super().save(*args, **kwargs)


class ManagerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    display_name = models.CharField(max_length=100)
    yahoo_guid = models.CharField(max_length=100, blank=True)
    sleeper_user_id = models.CharField(max_length=100, blank=True, db_index=True)
    is_commissioner = models.BooleanField(default=False)
    is_officer = models.BooleanField(default=False)

    def __str__(self):
        return self.display_name


class Team(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=150)
    yahoo_team_key = models.CharField(max_length=100, blank=True)
    manager = models.ForeignKey(
        ManagerProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teams",
    )

    class Meta:
        unique_together = ("season", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.season.year} - {self.name}"


class Standing(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="standings")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="standings")
    rank = models.PositiveIntegerField()
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    ties = models.PositiveIntegerField(default=0)
    points_for = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    points_against = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    final_place = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("season", "team")
        ordering = ["rank"]

    def __str__(self):
        return f"{self.season.year} - {self.team.name} ({self.rank})"


class Champion(models.Model):
    season = models.OneToOneField(Season, on_delete=models.CASCADE, related_name="champion_record")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="championships")
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.season.year} Champion - {self.team.name}"


class Player(models.Model):
    yahoo_player_key = models.CharField(max_length=100, blank=True, null=True, unique=True)
    yahoo_player_id = models.CharField(max_length=50, blank=True, db_index=True)
    full_name = models.CharField(max_length=150)
    nfl_team = models.CharField(max_length=20, blank=True)
    primary_position = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class RosterSnapshot(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="roster_snapshots")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="roster_snapshots")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="roster_snapshots")
    week = models.PositiveIntegerField(default=0)
    is_final_roster = models.BooleanField(default=False)

    class Meta:
        unique_together = ("season", "team", "player", "week")

    def __str__(self):
        return f"{self.season.year} - {self.team.name} - {self.player.full_name}"


class DraftPick(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="draft_picks")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name="draft_picks")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True, blank=True, related_name="draft_picks")
    round = models.PositiveIntegerField()
    pick = models.PositiveIntegerField()

    class Meta:
        unique_together = ("season", "round", "pick")
        ordering = ["round", "pick"]

    def __str__(self):
        return f"{self.season.year} R{self.round}P{self.pick} — {self.player or 'unknown'}"


class KeeperRecord(models.Model):
    SOURCE_CHOICES = [
        ("manual", "Manual"),
        ("app", "App"),
        ("yahoo", "Yahoo"),
    ]

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="keeper_records")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="keeper_records")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="keeper_records")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("season", "team", "player")
        ordering = ["-season__year", "team__name", "player__full_name"]

    def __str__(self):
        return f"{self.season.year} - {self.team.name} kept {self.player.full_name}"


class TeamAccess(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    is_commissioner = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "season", "team")

    def __str__(self):
        return f"{self.user.username} -> {self.team.name} ({self.season.year})"


class RuleProposal(models.Model):
    description = models.TextField()
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rule_proposals",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.submitted_by.username}: {self.description[:60]}"


class RuleVote(models.Model):
    VOTE_CHOICES = [("up", "up"), ("down", "down")]
    proposal = models.ForeignKey(RuleProposal, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rule_votes")
    vote = models.CharField(max_length=4, choices=VOTE_CHOICES)

    class Meta:
        unique_together = ("proposal", "user")


class Matchup(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="matchups")
    week = models.PositiveIntegerField()
    team_a = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="matchups_as_a")
    team_b = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="matchups_as_b")
    score_a = models.DecimalField(max_digits=8, decimal_places=2)
    score_b = models.DecimalField(max_digits=8, decimal_places=2)
    is_playoff = models.BooleanField(default=False)
    is_consolation = models.BooleanField(default=False)

    class Meta:
        unique_together = ("season", "week", "team_a", "team_b")
        ordering = ["season__year", "week"]

    def __str__(self):
        return f"{self.season.year} W{self.week}: {self.team_a.name} {self.score_a} vs {self.team_b.name} {self.score_b}"


class PlayerWeeklyScore(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="player_weekly_scores")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="player_weekly_scores")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="weekly_scores")
    week = models.PositiveIntegerField()
    points = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_starter = models.BooleanField(default=True)

    class Meta:
        unique_together = ("season", "team", "player", "week")
        ordering = ["season__year", "week", "-points"]

    def __str__(self):
        role = "starter" if self.is_starter else "bench"
        return f"{self.season.year} W{self.week}: {self.player.full_name} ({self.team.name}) {self.points}pts [{role}]"


class Draft(models.Model):
    season = models.OneToOneField(Season, on_delete=models.CASCADE, related_name="draft_info")
    date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    location_url = models.URLField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    fetched_images = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.season.year} Draft"


class DraftMedia(models.Model):
    draft = models.ForeignKey(Draft, on_delete=models.CASCADE, related_name="media")
    file = models.FileField(upload_to="draft_media/%Y/")
    caption = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    _VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.webm', '.mkv', '.m4v')

    @property
    def is_video(self):
        return (self.file.name or '').lower().endswith(self._VIDEO_EXTS)

    @property
    def safe_url(self):
        try:
            return self.file.url if self.file.name else None
        except Exception:
            return None

    def __str__(self):
        return f"{self.draft} — {self.file.name}"


class MediaReaction(models.Model):
    LOVE = "love"
    LIKE = "like"
    HATE = "hate"
    REACTION_CHOICES = [(LOVE, "❤️"), (LIKE, "👍"), (HATE, "👎")]

    media = models.ForeignKey(DraftMedia, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="media_reactions")
    reaction = models.CharField(max_length=10, choices=REACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("media", "user")

    def __str__(self):
        return f"{self.user} {self.reaction} on {self.media_id}"


class MediaComment(models.Model):
    media = models.ForeignKey(DraftMedia, on_delete=models.CASCADE, related_name="media_comments")
    text = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author} on {self.media_id}: {self.text[:40]}"


class DraftComment(models.Model):
    draft = models.ForeignKey(Draft, on_delete=models.CASCADE, related_name="comments")
    text = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.draft} — {self.author.username}"


class Transaction(models.Model):
    TYPE_ADD = "add"
    TYPE_DROP = "drop"
    TYPE_TRADE = "trade"
    TYPE_CHOICES = [
        (TYPE_ADD, "Add"),
        (TYPE_DROP, "Drop"),
        (TYPE_TRADE, "Trade"),
    ]

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    team_name = models.CharField(max_length=150, blank=True)
    player_name = models.CharField(max_length=150, blank=True)
    detail = models.CharField(max_length=400, blank=True)
    occurred_at = models.DateTimeField()
    yahoo_transaction_id = models.CharField(max_length=100, blank=True, db_index=True)

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.occurred_at.date()} {self.type}: {self.player_name} ({self.team_name})"


class KeeperSubmission(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="keeper_submissions")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="keeper_submissions")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="keeper_submissions")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("season", "team", "player")
        ordering = ["team__name", "player__full_name"]

    def clean(self):
        previous_season = Season.objects.filter(year=self.season.year - 1).first()

        if previous_season and KeeperRecord.objects.filter(
            season=previous_season,
            player=self.player
        ).exists():
            raise ValidationError(f"{self.player.full_name} was a keeper last year and is not eligible.")

        # Check current season roster first; fall back to previous season's
        # final roster (which is the source of truth when keepers are submitted
        # before the new season's rosters have been synced).
        on_final_roster = RosterSnapshot.objects.filter(
            season=self.season,
            team=self.team,
            player=self.player,
            is_final_roster=True,
        ).exists()

        if not on_final_roster and previous_season:
            prev_team = Team.objects.filter(season=previous_season, name=self.team.name).first()
            if prev_team:
                on_final_roster = RosterSnapshot.objects.filter(
                    season=previous_season,
                    team=prev_team,
                    player=self.player,
                    is_final_roster=True,
                ).exists()

        if not on_final_roster:
            raise ValidationError(f"{self.player.full_name} was not on the final roster for this team.")

        if self.season.keeper_deadline and timezone.now() > self.season.keeper_deadline:
            raise ValidationError("Keeper deadline has passed.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


# ── SLEEPER / BEAVER MODELS ───────────────────────────────────────────────────

class SleeperLeague(models.Model):
    league_id = models.CharField(max_length=64, unique=True)
    season_year = models.PositiveIntegerField(db_index=True)
    name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=30, blank=True)
    previous_league_id = models.CharField(max_length=64, blank=True)
    total_rosters = models.PositiveIntegerField(default=10)
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-season_year"]

    def save(self, *args, **kwargs):
        if self.is_current:
            SleeperLeague.objects.exclude(pk=self.pk).filter(is_current=True).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.season_year} BEAVER ({self.league_id})"


class SleeperRoster(models.Model):
    league = models.ForeignKey(SleeperLeague, on_delete=models.CASCADE, related_name="rosters")
    roster_id = models.PositiveIntegerField()
    owner_id = models.CharField(max_length=64, blank=True)
    manager = models.ForeignKey(
        ManagerProfile, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sleeper_rosters",
    )
    team_name = models.CharField(max_length=150, blank=True)
    avatar_id = models.CharField(max_length=100, blank=True)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    ties = models.PositiveIntegerField(default=0)
    points_for = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    points_against = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    players = models.JSONField(default=list)
    taxi_players = models.JSONField(default=list)
    reserve_players = models.JSONField(default=list)
    rank = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("league", "roster_id")
        ordering = ["rank", "roster_id"]

    def __str__(self):
        return f"{self.league.season_year} Roster {self.roster_id} ({self.team_name or self.owner_id})"


class SleeperPlayer(models.Model):
    sleeper_id = models.CharField(max_length=20, primary_key=True)
    full_name = models.CharField(max_length=150, blank=True)
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    position = models.CharField(max_length=10, blank=True)
    nfl_team = models.CharField(max_length=10, blank=True)
    status = models.CharField(max_length=50, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.position}, {self.nfl_team})"


class SleeperMatchup(models.Model):
    league = models.ForeignKey(SleeperLeague, on_delete=models.CASCADE, related_name="matchups")
    week = models.PositiveIntegerField()
    matchup_id = models.PositiveIntegerField()
    roster = models.ForeignKey(SleeperRoster, on_delete=models.CASCADE, related_name="matchups")
    points = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_playoff = models.BooleanField(default=False)

    class Meta:
        unique_together = ("league", "week", "roster")
        ordering = ["league__season_year", "week", "matchup_id"]

    def __str__(self):
        return f"{self.league.season_year} W{self.week} M{self.matchup_id}: {self.roster}"


class SleeperTransaction(models.Model):
    TYPE_FREE_AGENT = "free_agent"
    TYPE_WAIVER = "waiver"
    TYPE_TRADE = "trade"
    TYPE_CHOICES = [
        (TYPE_FREE_AGENT, "Free Agent"),
        (TYPE_WAIVER, "Waiver"),
        (TYPE_TRADE, "Trade"),
    ]

    league = models.ForeignKey(SleeperLeague, on_delete=models.CASCADE, related_name="sleeper_transactions")
    sleeper_txn_id = models.CharField(max_length=64, unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, blank=True)
    week = models.PositiveIntegerField(null=True, blank=True)
    adds = models.JSONField(default=dict)
    drops = models.JSONField(default=dict)
    roster_ids = models.JSONField(default=list)
    waiver_bid = models.PositiveIntegerField(null=True, blank=True)
    draft_picks = models.JSONField(default=list)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.league.season_year} {self.type} {self.sleeper_txn_id}"


class SleeperTradedPick(models.Model):
    league = models.ForeignKey(SleeperLeague, on_delete=models.CASCADE, related_name="traded_picks")
    season_year = models.PositiveIntegerField()
    round = models.PositiveIntegerField()
    roster_id = models.PositiveIntegerField()
    previous_owner_id = models.PositiveIntegerField()
    owner_id = models.PositiveIntegerField()

    class Meta:
        unique_together = ("league", "season_year", "round", "roster_id", "owner_id")
        ordering = ["season_year", "round", "roster_id"]

    def __str__(self):
        return f"{self.season_year} R{self.round} (orig {self.roster_id} → {self.owner_id})"


class SleeperDraftPick(models.Model):
    league = models.ForeignKey(SleeperLeague, on_delete=models.CASCADE, related_name="draft_results")
    draft_id = models.CharField(max_length=64, blank=True)
    round = models.PositiveIntegerField()
    pick_no = models.PositiveIntegerField()
    roster_id = models.PositiveIntegerField()
    player = models.ForeignKey(
        SleeperPlayer, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="draft_picks",
    )
    player_name = models.CharField(max_length=150, blank=True)

    class Meta:
        unique_together = ("league", "draft_id", "round", "pick_no")
        ordering = ["round", "pick_no"]

    def __str__(self):
        return f"{self.league.season_year} R{self.round}P{self.pick_no}: {self.player_name}"


class SleeperChampion(models.Model):
    league = models.OneToOneField(SleeperLeague, on_delete=models.CASCADE, related_name="champion")
    roster = models.ForeignKey(SleeperRoster, on_delete=models.CASCADE, related_name="championships")
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.league.season_year} BEAVER Champion — {self.roster.team_name}"