from datetime import datetime
from datetime import timezone as dt_timezone

from django.db.models import Q
from django.utils import timezone

from apps.games.models import Game


class GameTop100Service:
    GENRE_MAPPING = {
        1: [25, 33],
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
    REVIEW_COUNT_THRESHOLDS = (50, 30, 10)
    MIN_RELEASE_YEAR = 1980
    MIN_RELEASE_DATE = datetime(MIN_RELEASE_YEAR, 1, 1, tzinfo=dt_timezone.utc)

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
        )

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

        ordering = ("-first_release_date", "-game_id")

        selected: list[Game] = []
        selected_ids: set[int] = set()

        for review_count in GameTop100Service.REVIEW_COUNT_THRESHOLDS:
            for year in GameTop100Service._target_release_years(now.year):
                if len(selected) >= GameTop100Service.RESULT_LIMIT:
                    break

                candidates = (
                    GameTop100Service._filter_by_release_year(
                        queryset=base_queryset,
                        year=year,
                    )
                    .filter(total_rating_count__gte=review_count)
                    .exclude(game_id__in=selected_ids)
                    .order_by(*ordering)[: GameTop100Service.CANDIDATE_LIMIT]
                )
                selected = GameTop100Service._append_unique_games(
                    selected=selected,
                    candidates=candidates,
                    selected_ids=selected_ids,
                )

        if len(selected) < GameTop100Service.RESULT_LIMIT:
            for review_count in GameTop100Service.REVIEW_COUNT_THRESHOLDS:
                for year in GameTop100Service._target_release_years(now.year):
                    if len(selected) >= GameTop100Service.RESULT_LIMIT:
                        break

                    candidates = (
                        GameTop100Service._filter_by_release_year(
                            queryset=base_queryset,
                            year=year,
                        )
                        .filter(total_rating_count__gte=review_count)
                        .exclude(game_id__in=selected_ids)
                        .order_by(*ordering)[: GameTop100Service.CANDIDATE_LIMIT]
                    )
                    selected = GameTop100Service._append_games(
                        selected=selected,
                        candidates=candidates,
                        selected_ids=selected_ids,
                    )

        return selected[: GameTop100Service.RESULT_LIMIT]

    @staticmethod
    def _target_release_years(current_year: int) -> list[int]:
        return list(range(current_year, GameTop100Service.MIN_RELEASE_YEAR - 1, -1))

    @staticmethod
    def _filter_by_release_year(queryset, year: int):
        start = datetime(year, 1, 1, tzinfo=dt_timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=dt_timezone.utc)
        return queryset.filter(
            first_release_date__gte=start, first_release_date__lt=end
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
                q |= Q(name__icontains=word) | Q(name_ko__icontains=word)
            return queryset.filter(q)

        return queryset.filter(
            Q(name__icontains=normalized_search)
            | Q(name_ko__icontains=normalized_search)
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
