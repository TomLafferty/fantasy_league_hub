from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("leaguehub", "0007_add_matchup"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlayerWeeklyScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week", models.PositiveIntegerField()),
                ("points", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ("is_starter", models.BooleanField(default=True)),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="weekly_scores", to="leaguehub.player")),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="player_weekly_scores", to="leaguehub.season")),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="player_weekly_scores", to="leaguehub.team")),
            ],
            options={
                "ordering": ["season__year", "week", "-points"],
                "unique_together": {("season", "team", "player", "week")},
            },
        ),
    ]
