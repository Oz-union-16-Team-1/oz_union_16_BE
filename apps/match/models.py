from django.conf import settings
from django.db import models
from django.db.models import Q
from pgvector.django import HnswIndex, VectorField

from apps.core.models import TimeStampedModel

# Vector 차원 상수 정의
MATCH_VECTOR_DIM = 14


class MatchGameRating(TimeStampedModel):
    star_rating = models.SmallIntegerField(verbose_name="평점")  # 1 ~ 5
    effective_rating = models.DecimalField(
        max_digits=4, decimal_places=2, verbose_name="유효 평점"
    )
    rating_count = models.IntegerField(default=0, verbose_name="평가 횟수")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="match_ratings",
    )
    game = models.ForeignKey(
        "games.Game",
        on_delete=models.CASCADE,
        db_column="game_id",
        related_name="match_ratings",
        verbose_name="게임 ID",
    )

    class Meta:
        db_table = "match_game_ratings"
        constraints = [
            models.UniqueConstraint(  # 유저-게임당 1건의 평점만 허용
                fields=["user", "game"],
                name="uq_mgr_user_game",
            ),
            models.CheckConstraint(  # 별점 1~5 제한
                condition=Q(star_rating__gte=1) & Q(star_rating__lte=5),
                name="ck_mgr_star_rating_range",
            ),
        ]
        indexes = [
            models.Index(fields=["game"], name="idx_mgr_game"),
        ]


class MatchGamePreference(TimeStampedModel):

    game = models.OneToOneField(  # 게임당 1개의 벡터가 존재하므로 OneToOneField
        "games.Game",
        on_delete=models.CASCADE,
        db_column="game_id",
        related_name="match_preference",
        primary_key=True,
        verbose_name="게임 ID",
    )
    game_preference_vector = VectorField(
        dimensions=MATCH_VECTOR_DIM, verbose_name="게임 취향 벡터"
    )

    class Meta:
        db_table = "match_game_preference"
        indexes = [
            HnswIndex(  # 명세서의 벡터 코사인 유사도 인덱스 구현
                name="idx_mgp_vector_cosine_hnsw",
                fields=["game_preference_vector"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]


class MatchGameGenreMap(models.Model):
    game = models.ForeignKey(
        "games.Game",
        on_delete=models.CASCADE,
        db_column="game_id",
        related_name="genre_maps",
    )

    pgti_genre_id = models.IntegerField(
        verbose_name="PGTI 장르 ID"
    )  # 명세서 기준 필드명 pgti_genre_id
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "match_game_genre_map"
        constraints = [
            models.UniqueConstraint(  # 게임-장르 중복 매핑 방지
                fields=["game", "pgti_genre_id"],
                name="uq_mggm_game_genre",
            ),
            models.CheckConstraint(  # 장르 코드 범위 1~14 제한
                condition=Q(pgti_genre_id__gte=1) & Q(pgti_genre_id__lte=14),
                name="ck_mggm_genre_id_range",
            ),
        ]
        indexes = [
            models.Index(fields=["pgti_genre_id", "game"], name="idx_mggm_genre_game"),
        ]
