from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


# 1. 유저별 좋아요 기록
class UserGamelike(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_likes",
    )
    game_id = models.IntegerField()  # IGDB 게임_ID

    class Meta:
        db_table = "user_game_likes"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game_id"], name="user_game_likes_unique"
            ),
        ]


# 2. 게임당 총 좋아요 수
class GameLikeCount(TimeStampedModel):
    game_like_id = models.BigAutoField(primary_key=True)
    game_id = models.IntegerField(unique=True)  # 집계 테이블: 게임당 1행만 유지
    like_count = models.IntegerField(default=0)

    class Meta:
        db_table = (
            "game_like_counts"  # like_count는 음수 방지 CheckConstraint를 넣어 안전하게
        )


# 3. 블랙리스트 관리
class GameExclusion(TimeStampedModel):
    game_exclusion_id = models.BigAutoField(primary_key=True)
    game_id = models.IntegerField(unique=True)
    title = models.CharField(max_length=255)
    reason = models.CharField(max_length=255)
    is_excluded = models.BooleanField(default=True)

    class Meta:
        db_table = "game_exclusions"
