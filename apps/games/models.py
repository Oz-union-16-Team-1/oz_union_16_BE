from django.conf import settings
from django.db import models
from django.db.models import Q


# 1. 유저별 좋아요 기록
class UserGamelike(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_likes",
    )
    game_id = models.IntegerField()  # IGDB 게임_ID
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_game_likes"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game_id"], name="user_game_likes_unique"
            ),
        ]


# 2. 게임당 총 좋아요 수
class GameLikeCount(models.Model):
    game_like_id = models.BigAutoField(primary_key=True)
    game_id = models.IntegerField(unique=True)  # 집계 테이블: 게임당 1행만 유지
    like_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = (
            "game_like_counts"  # like_count는 음수 방지 CheckConstraint를 넣어 안전하게
        )
        constraints = [
            models.CheckConstraint(
                condition=Q(like_count__gte=0),
                name="ck_game_like_counts_non_negative",
            ),
        ]


# 3. 블랙리스트 관리
class GameExclusion(models.Model):
    game_exclusion_id = models.BigAutoField(primary_key=True)
    game_id = models.IntegerField(unique=True)
    title = models.CharField(max_length=255)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "game_exclusions"
