from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0005_game_korean_descriptions"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="name_ko",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name="게임 이름 한글 번역",
            ),
        ),
    ]
