from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0003_game_delete_gameexclusion_delete_gamelikecount_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="ban_reason",
            field=models.TextField(blank=True, null=True, verbose_name="제외 사유"),
        ),
    ]
