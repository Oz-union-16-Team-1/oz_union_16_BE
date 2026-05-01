from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0004_game_ban_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="summary_ko",
            field=models.TextField(
                blank=True,
                null=True,
                verbose_name="게임 개요 한글 번역",
            ),
        ),
        migrations.AddField(
            model_name="game",
            name="storyline_ko",
            field=models.TextField(
                blank=True,
                null=True,
                verbose_name="게임 스토리라인 한글 번역",
            ),
        ),
    ]
