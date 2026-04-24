from django.conf import settings
from django.db import models
from django.db.models import Q
from pgvector.django import HnswIndex, VectorField

from apps.core.models import TimeStampedModel

# Vector 차원 상수 정의
MATCH_VECTOR_DIM = 14


class MatchGameRating(TimeStampedModel):
    match_game_rating_id = models.BigAutoField(primary_key=True)  # 기존 PK 유지
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
        to_field="game_id",
        related_name="match_ratings",
    )

    class Meta:
        db_table = "match_game_ratings"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game"],
                name="uq_mgr_user_game",
            ),
            models.CheckConstraint(
                condition=Q(star_rating__gte=1) & Q(star_rating__lte=5),
                name="ck_mgr_star_rating_range",
            ),
        ]
        indexes = [
            models.Index(fields=["game"], name="idx_mgr_game"),
        ]


# 1. 게임 취향 벡터 저장
class MatchGamePreference(TimeStampedModel):
    match_game_preference_id = models.BigAutoField(primary_key=True)  # 기존 PK 유지
    game_id = models.ForeignKey(
        "games.Game",
        on_delete=models.CASCADE,
        db_column="game_id",
        related_name="match_preferences",
        verbose_name="게임 ID",
    )
    game_preference_vector = VectorField(
        dimensions=MATCH_VECTOR_DIM,
        verbose_name="게임 취향 벡터",
    )

    class Meta:
        db_table = "match_game_preference"
        constraints = [
            models.UniqueConstraint(
                fields=["game_id"],
                name="uq_mgp_game",
            ),
        ]
        indexes = [
            HnswIndex(
                name="idx_mgp_vector_cosine_hnsw",
                fields=["game_preference_vector"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]


# 2. 매칭 게임 장르 매핑
class MatchGameGenreMap(TimeStampedModel):
    match_game_genre_map_id = models.BigAutoField(primary_key=True)  # 기존 PK 유지
    game_id = models.ForeignKey(
        "games.Game",
        on_delete=models.CASCADE,
        db_column="game_id",
        to_field="game_id",
        related_name="genre_maps",
    )
    igdb_genre_id = models.PositiveSmallIntegerField(db_column="igdb_genre_id")

    class Meta:
        db_table = "match_game_genre_map"
        constraints = [
            models.UniqueConstraint(
                fields=["game_id", "igdb_genre_id"], name="uq_mggm_game_genre"
            ),
            models.CheckConstraint(
                condition=Q(igdb_genre_id__gte=1) & Q(igdb_genre_id__lte=14),
                name="ck_mggm_genre_id_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["igdb_genre_id", "game_id"], name="idx_mggm_genre_game"
            ),
        ]
