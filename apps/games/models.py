from django.db import models
from django.db.models import Q


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


class GameExclusion(models.Model):
    game_exclusion_id = models.BigAutoField(primary_key=True)
    game_id = models.IntegerField(
        unique=True
    )  # 블랙리스트는 게임당 1건만 허용 (사유는 reason 문자열로 통합 관리)
    title = models.CharField(max_length=30)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "game_exclusions"
