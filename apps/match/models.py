from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel
from pgvector.django import VectorField

class MatchGameRating(TimeStampedModel):
    match_game_rating_id = models.BigAutoField(primary_key=True)
    star_rating = models.PositiveSmallIntegerField()  # 매칭 점수 1 ~ 5
    effective_rating = models.DecimalField(max_digits=4, decimal_places=2)
    rating_count = models.PositiveIntegerField(default=0)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # settings.AUTH_USER_MODEL FK로 인증 중심형 유저와 안전하게 연결
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="match_game_ratings",
    )
    match_game_preference = models.ForeignKey(
        "match.MatchGamePreference",
        on_delete=models.CASCADE,
        db_column="match_game_preference_id",
        related_name="ratings",
    )

    class Meta:
        db_table = "match_game_ratings"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "match_game_preference"],
                name="uq_match_game_ratings_user_preference",
            ),
            models.CheckConstraint(
                condition=Q(star_rating__gte=1)
                & Q(star_rating__lte=5),  # 별점 스케일은 1 ~ 5로 고정
                name="ck_match_game_ratings_star_rating_1_5",
            ),
        ]

class MatchGamePreference(TimeStampedModel):
    match_game_preference_id = models.BigAutoField(primary_key=True)
    game_id = models.IntegerField(db_index=True)
    genre_id = models.IntegerField(db_index=True)
    game_preference_vector = VectorField(dimensions=14)

    class Meta:
        db_table = "match_game_preference"
        constraints = [
            models.UniqueConstraint(
                fields=["game_id"],
                name="uq_match_game_preference_game_id",
            ),
        ]
        indexes = [
            models.Index(
                fields=["genre_id"],
                name="idx_match_game_preference_genre_id",
            ),
        ]

class MatchGameGenreMap(models.Model):
    match_game_genre_map_id = models.BigAutoField(primary_key=True)
    game_id = models.IntegerField(db_index=True)
    igdb_genre_id = models.IntegerField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "match_game_genre_map"
        constraints = [
            models.UniqueConstraint(
                fields=["game_id", "igdb_genre_id"],
                name="uq_match_game_genre_map_game_genre",
            ),
        ]
