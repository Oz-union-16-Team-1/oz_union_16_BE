from datetime import datetime
from datetime import timezone as dt_timezone

from django.db.models import Q
from django.utils import timezone

from apps.games.models import Game


class GameTop100Service:
    GENRE_MAPPING = {
        1: [5, 25, 33],
        2: [31, 2],
        3: [12],
        4: [5],
        5: [15, 11, 16, 24, 36],
        6: [13],
        7: [14],
        8: [10],
        9: [9, 26, 30],
        10: [8],
        11: [4],
        12: [35],
        13: [7],
        14: [34],
    }
    CANDIDATE_LIMIT = 500
    RESULT_LIMIT = 100
    REVIEW_COUNT_THRESHOLDS = (50, 30, 10, 5)
    GLOBAL_REVIEW_COUNT_THRESHOLD = 50
    GLOBAL_INITIAL_YEAR_SPAN = 3
    GLOBAL_MIN_RELEASE_YEAR = 2020
    MIN_RELEASE_YEAR = 1980
    MIN_RELEASE_DATE = datetime(MIN_RELEASE_YEAR, 1, 1, tzinfo=dt_timezone.utc)
    EXCLUDED_SERVICE_STATUSES = (
        5,  # offline
        6,  # cancelled
        8,  # delisted
    )

    @staticmethod
    def get_top_100_games(
        genre_id: int, search: str = "", fuzzy: bool = False
    ) -> list[Game]:
        now = timezone.now()
        base_queryset = Game.objects.filter(
            first_release_date__lte=now,
            first_release_date__gte=GameTop100Service.MIN_RELEASE_DATE,
            total_rating__isnull=False,
            parent_game__isnull=True,
            is_ban=False,
        ).exclude(status__in=GameTop100Service.EXCLUDED_SERVICE_STATUSES)

        base_queryset = GameTop100Service._apply_search_filter(
            queryset=base_queryset,
            search=search,
            fuzzy=fuzzy,
        )

        base_queryset = GameTop100Service._apply_genre_filter(
            queryset=base_queryset,
            genre_id=genre_id,
        )
        if base_queryset is None:
            return []

        if genre_id == 0:
            return GameTop100Service._collect_global_top100(
                base_queryset=base_queryset,
                start_year=now.year,
            )

        return GameTop100Service._collect_genre_top100(
            base_queryset=base_queryset,
            start_year=now.year,
        )

    @staticmethod
    def _collect_global_top100(*, base_queryset, start_year: int) -> list[Game]:
        initial_end_year = max(
            start_year - GameTop100Service.GLOBAL_INITIAL_YEAR_SPAN + 1,
            GameTop100Service.GLOBAL_MIN_RELEASE_YEAR,
        )
        year_ranges = [(start_year, initial_end_year)]
        year_ranges.extend(
            (year, year)
            for year in range(
                initial_end_year - 1,
                GameTop100Service.GLOBAL_MIN_RELEASE_YEAR - 1,
                -1,
            )
        )

        querysets = [
            GameTop100Service._filter_year_range(
                base_queryset,
                start_year=range_start,
                end_year=range_end,
            ).filter(
                total_rating_count__gte=GameTop100Service.GLOBAL_REVIEW_COUNT_THRESHOLD
            )
            for range_start, range_end in year_ranges
        ]
        return GameTop100Service._collect_from_rank_buckets(querysets)

    @staticmethod
    def _collect_genre_top100(*, base_queryset, start_year: int) -> list[Game]:
        querysets = []
        for year in range(start_year, GameTop100Service.MIN_RELEASE_YEAR - 1, -1):
            year_queryset = GameTop100Service._filter_year(base_queryset, year)
            for review_count in GameTop100Service.REVIEW_COUNT_THRESHOLDS:
                querysets.append(
                    year_queryset.filter(total_rating_count__gte=review_count)
                )

        return GameTop100Service._collect_from_rank_buckets(querysets)

    @staticmethod
    def _collect_from_rank_buckets(querysets: list) -> list[Game]:
        selected: list[Game] = []
        selected_ids: set[int] = set()
        ordering = GameTop100Service._ranking_ordering()

        for queryset in querysets:
            if len(selected) >= GameTop100Service.RESULT_LIMIT:
                break

            candidates = queryset.exclude(game_id__in=selected_ids).order_by(*ordering)[
                : GameTop100Service.CANDIDATE_LIMIT
            ]
            selected = GameTop100Service._append_unique_games(
                selected=selected,
                candidates=candidates,
                selected_ids=selected_ids,
            )

        if len(selected) < GameTop100Service.RESULT_LIMIT:
            for queryset in querysets:
                if len(selected) >= GameTop100Service.RESULT_LIMIT:
                    break

                candidates = queryset.exclude(game_id__in=selected_ids).order_by(
                    *ordering
                )[: GameTop100Service.CANDIDATE_LIMIT]
                selected = GameTop100Service._append_games(
                    selected=selected,
                    candidates=candidates,
                    selected_ids=selected_ids,
                )

        return GameTop100Service._sort_ranked_games(selected)[
            : GameTop100Service.RESULT_LIMIT
        ]

    @staticmethod
    def _filter_year(queryset, year: int):
        return GameTop100Service._filter_year_range(
            queryset,
            start_year=year,
            end_year=year,
        )

    @staticmethod
    def _filter_year_range(queryset, *, start_year: int, end_year: int):
        start_date = datetime(end_year, 1, 1, tzinfo=dt_timezone.utc)
        end_date = datetime(start_year + 1, 1, 1, tzinfo=dt_timezone.utc)
        return queryset.filter(
            first_release_date__gte=start_date,
            first_release_date__lt=end_date,
        )

    @staticmethod
    def _ranking_ordering() -> tuple[str, str, str, str]:
        return (
            "-total_rating",
            "-total_rating_count",
            "-first_release_date",
            "-game_id",
        )

    @staticmethod
    def _sort_ranked_games(games: list[Game]) -> list[Game]:
        return sorted(
            games,
            key=lambda game: (
                game.total_rating or 0,
                game.total_rating_count or 0,
                game.first_release_date or GameTop100Service.MIN_RELEASE_DATE,
                game.game_id,
            ),
            reverse=True,
        )

    @staticmethod
    def _apply_search_filter(queryset, search: str, fuzzy: bool):
        if not search:
            return queryset

        normalized_search = search.strip()
        if not normalized_search:
            return queryset

        if fuzzy:
            words = normalized_search.split()
            q = Q()
            for word in words:
                q |= Q(name__istartswith=word) | Q(name_ko__istartswith=word)
            return queryset.filter(q)

        return queryset.filter(
            Q(name__istartswith=normalized_search)
            | Q(name_ko__istartswith=normalized_search)
        )

    @staticmethod
    def _apply_genre_filter(queryset, genre_id: int):
        if genre_id == 0:
            return queryset

        target_igdb_ids = GameTop100Service.GENRE_MAPPING.get(genre_id, [])
        if not target_igdb_ids:
            return None

        genre_filter = Q()
        for igdb_id in target_igdb_ids:
            genre_filter |= Q(genres__contains=[igdb_id])

        return queryset.filter(genre_filter).distinct()

    @staticmethod
    def _append_unique_games(
        *,
        selected: list[Game],
        candidates,
        selected_ids: set[int],
    ) -> list[Game]:
        seen_collections: set[int] = {
            game.collection for game in selected if game.collection is not None
        }
        seen_base_names: set[str] = {
            GameTop100Service._base_name(game.name)
            for game in selected
            if game.collection is None
        }

        for game in candidates:
            if len(selected) >= GameTop100Service.RESULT_LIMIT:
                break
            if game.game_id in selected_ids:
                continue

            if game.collection is not None:
                if game.collection in seen_collections:
                    continue
                seen_collections.add(game.collection)
            else:
                base_name = GameTop100Service._base_name(game.name)
                if base_name in seen_base_names:
                    continue
                seen_base_names.add(base_name)

            selected.append(game)
            selected_ids.add(game.game_id)

        return selected

    @staticmethod
    def _append_games(
        *,
        selected: list[Game],
        candidates,
        selected_ids: set[int],
    ) -> list[Game]:
        for game in candidates:
            if len(selected) >= GameTop100Service.RESULT_LIMIT:
                break
            if game.game_id in selected_ids:
                continue

            selected.append(game)
            selected_ids.add(game.game_id)

        return selected

    @staticmethod
    def _base_name(name: str) -> str:
        return name.split(":")[0].split("-")[0].strip().lower()
