from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("leaguehub", "0006_rule_proposal_vote"),
    ]

    operations = [
        migrations.CreateModel(
            name="Matchup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week", models.PositiveIntegerField()),
                ("score_a", models.DecimalField(max_digits=8, decimal_places=2)),
                ("score_b", models.DecimalField(max_digits=8, decimal_places=2)),
                ("is_playoff", models.BooleanField(default=False)),
                ("is_consolation", models.BooleanField(default=False)),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matchups", to="leaguehub.season")),
                ("team_a", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matchups_as_a", to="leaguehub.team")),
                ("team_b", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matchups_as_b", to="leaguehub.team")),
            ],
            options={
                "ordering": ["season__year", "week"],
                "unique_together": {("season", "week", "team_a", "team_b")},
            },
        ),
    ]
