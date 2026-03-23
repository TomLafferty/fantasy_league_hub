from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leaguehub", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="season",
            name="yahoo_league_key",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
