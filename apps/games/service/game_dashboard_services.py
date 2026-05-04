from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.db.models import Avg, Count, QuerySet
from django.utils import timezone

from apps.games.models import Game
from apps.match.constants import IGDB_GENRE_NAME_MAP
from apps.match.models import MatchGameRating
from apps.users.models import UserLikeBookmark


@dataclass(frozen=True)
class RecommendationHistoryAdapter:
    model: Any | None

    @classmethod
    def load(cls) -> "RecommendationHistoryAdapter":
        try:
            model = apps.get_model("match", "RecommendationHistory")
        except LookupError:
            model = None
        return cls(model=model)

    def queryset(self, game: Game) -> QuerySet[Any] | None:
        if self.model is None:
            return None

        field_names = {field.name for field in self.model._meta.fields}
        if "game" in field_names:
            return self.model.objects.filter(game=game)
        if "game_id" in field_names:
            return self.model.objects.filter(game_id=game.game_id)
        return None


class GameDashboardService:
    @classmethod
    def get_dashboard(cls, game_id: int) -> dict[str, Any]:
        game = Game.objects.get(game_id=game_id)
        ratings = MatchGameRating.objects.filter(game=game)
        likes_count = cls._get_likes_count(game)
        recommendation_history = RecommendationHistoryAdapter.load().queryset(game)

        return {
            "basic_info": cls._get_basic_info(game, ratings, likes_count),
            "performance_metrics": cls._get_performance_metrics(
                ratings=ratings,
                recommendation_history=recommendation_history,
            ),
            "user_reaction_analysis": cls._get_user_reaction_analysis(
                ratings=ratings,
                likes_count=likes_count,
            ),
            "blacklist_impact": cls._get_blacklist_impact(game, recommendation_history),
        }

    @staticmethod
    def _get_likes_count(game: Game) -> int:
        bookmark_count = UserLikeBookmark.objects.filter(game=game).count()
        return max(game.like_count or 0, bookmark_count)

    @classmethod
    def _get_basic_info(
        cls,
        game: Game,
        ratings: QuerySet[MatchGameRating],
        likes_count: int,
    ) -> dict[str, Any]:
        rating_summary = ratings.aggregate(
            total_rating_count=Count("match_game_rating_id"),
            average_star_rating=Avg("star_rating"),
        )

        return {
            "game_name": game.name,
            "game_id": game.game_id,
            "genres": cls._get_genre_names(game),
            "total_like_count": likes_count,
            "total_rating_count": rating_summary["total_rating_count"] or 0,
            "average_star_rating": cls._round_or_none(
                rating_summary["average_star_rating"]
            ),
            "is_ban": game.is_ban,
        }

    @classmethod
    def _get_performance_metrics(
        cls,
        ratings: QuerySet[MatchGameRating],
        recommendation_history: QuerySet[Any] | None,
    ) -> dict[str, Any]:
        now = timezone.now()
        recent_7d = now - timezone.timedelta(days=7)
        recent_30d = now - timezone.timedelta(days=30)

        return {
            "recommendation_impressions": cls._count_history(
                recommendation_history, ("impression", "shown", "exposed")
            ),
            "recommendation_clicks": cls._count_history(
                recommendation_history, ("click", "selected", "choice")
            ),
            "user_average_score": cls._round_or_none(
                ratings.aggregate(avg=Avg("effective_rating"))["avg"]
            ),
            "trend_7d": cls._build_rating_trend(
                ratings.filter(created_at__gte=recent_7d)
            ),
            "trend_30d": cls._build_rating_trend(
                ratings.filter(created_at__gte=recent_30d)
            ),
        }

    @staticmethod
    def _get_user_reaction_analysis(
        ratings: QuerySet[MatchGameRating],
        likes_count: int,
    ) -> dict[str, Any]:
        rating_count = ratings.count()
        star_counts = {
            row["star_rating"]: row["count"]
            for row in ratings.values("star_rating").annotate(
                count=Count("star_rating")
            )
        }
        distribution = {str(star): star_counts.get(star, 0) for star in range(1, 6)}
        excluded_count = distribution["1"]
        reaction_total = likes_count + excluded_count

        return {
            "star_distribution": distribution,
            "star_distribution_chart": GameDashboardService._build_star_chart(
                distribution
            ),
            "like_ratio": GameDashboardService._ratio(likes_count, reaction_total),
            "dislike_or_excluded_count": excluded_count,
        }

    @staticmethod
    def _get_blacklist_impact(
        game: Game,
        recommendation_history: QuerySet[Any] | None,
    ) -> dict[str, Any]:
        return {
            "is_ban": game.is_ban,
            "is_ban_mark": "O" if game.is_ban else "X",
            "ban_reason": game.ban_reason or "",
        }

    @staticmethod
    def _get_genre_names(game: Game) -> list[str]:
        raw_genres = game.genres or []
        names: list[str] = []
        for genre in raw_genres:
            genre_id = genre.get("id") if isinstance(genre, dict) else genre
            if isinstance(genre_id, str) and genre_id.isdigit():
                genre_id = int(genre_id)
            if isinstance(genre_id, int) and genre_id in IGDB_GENRE_NAME_MAP:
                names.append(IGDB_GENRE_NAME_MAP[genre_id])
        return names

    @staticmethod
    def _build_rating_trend(ratings: QuerySet[MatchGameRating]) -> dict[str, Any]:
        summary = ratings.aggregate(
            count=Count("match_game_rating_id"), avg=Avg("star_rating")
        )
        return {
            "rating_count": summary["count"] or 0,
            "average_star_rating": GameDashboardService._round_or_none(summary["avg"]),
        }

    @staticmethod
    def _count_history(
        recommendation_history: QuerySet[Any] | None,
        event_names: tuple[str, ...],
    ) -> int:
        if recommendation_history is None:
            return 0

        field_names = {
            field.name for field in recommendation_history.model._meta.fields
        }
        if "event_type" in field_names:
            return recommendation_history.filter(event_type__in=event_names).count()
        if "is_clicked" in field_names and "click" in event_names:
            return recommendation_history.filter(is_clicked=True).count()
        if "selected_at" in field_names and "selected" in event_names:
            return recommendation_history.filter(selected_at__isnull=False).count()
        return recommendation_history.count() if "impression" in event_names else 0

    @staticmethod
    def _build_star_chart(distribution: dict[str, int]) -> dict[str, Any]:
        colors = {
            5: "rgb(111, 93, 246)",
            4: "rgb(67, 189, 127)",
            3: "rgb(255, 200, 87)",
            2: "rgb(255, 143, 63)",
            1: "rgb(255, 91, 102)",
        }
        total = sum(distribution.values())
        items = []
        gradient_parts = []
        cursor = 0.0

        for star in range(5, 0, -1):
            count = distribution[str(star)]
            ratio = GameDashboardService._ratio(count, total)
            percent = round(ratio * 100, 1)
            next_cursor = cursor + percent
            color = colors[star]

            items.append(
                {
                    "star": star,
                    "count": count,
                    "ratio": ratio,
                    "percent": percent,
                    "color": color,
                }
            )

            if count > 0:
                gradient_parts.append(f"{color} {cursor}% {next_cursor}%")
            cursor = next_cursor

        return {
            "total": total,
            "items": items,
            "gradient": (
                ", ".join(gradient_parts)
                if gradient_parts
                else "rgb(208, 208, 208) 0% 100%"
            ),
        }

    @staticmethod
    def _ratio(part: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round(part / total, 4)

    @staticmethod
    def _round_or_none(value: Any) -> float | None:
        if value is None:
            return None
        return round(float(value), 2)
