from django.conf import settings
from django.db import models
from django.db.models import Q


class MatchResult(models.Model):  # 매칭 결과는 이력 저장 없이 최신 1건만 유지
    match_results_id = models.BigAutoField(primary_key=True)
    game_id = models.IntegerField(db_index=True)
    rating = models.FloatField()  # 매칭 점수 0.0 ~ 5.0
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # settings.AUTH_USER_MODEL FK로 인증 중심형 유저와 안전하게 연결
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="match_results",
    )

    class Meta:
        db_table = "match_results"  # 한 유저-한 게임 점수 1개
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game_id"],
                name="uq_match_results_user_game",
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=0.0)
                & Q(rating__lte=5.0),  # 별점 스케일은 0.0~5.0으로 고정
                name="ck_match_results_rating_0_5",
            ),
        ]
