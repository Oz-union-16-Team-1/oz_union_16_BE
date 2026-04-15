from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class MatchResult(TimeStampedModel):  # 매칭 결과는 이력 저장 없이 최신 1건만 유지
    match_results_id = models.BigAutoField(primary_key=True)
    game_id = models.IntegerField(db_index=True)
    rating = models.PositiveSmallIntegerField()  # 매칭 점수 1 ~ 5
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
                condition=Q(rating__gte=1)
                & Q(rating__lte=5),  # 별점 스케일은 1 ~ 5로 고정
                name="ck_match_results_rating_1_5",
            ),
            models.CheckConstraint(
                condition=Q(game_id__gt=0),
                name="ck_match_results_game_id_positive",
            ),
        ]
        indexes = [
            # latest_desc + cursor(match_results_id) 용
            models.Index(
                fields=["user", "-updated_at", "-match_results_id"],
                name="ix_match_user_latest_cursor",
            ),
            # popular_desc(rating desc) + cursor(match_results_id) 용
            models.Index(
                fields=["user", "-rating", "-match_results_id"],
                name="ix_match_user_popular_cursor",
            ),
        ]
