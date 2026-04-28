from django.db.models import Q
from django.utils import timezone

from apps.games.models import Game


class GameTop100Service:
    # 1. 누락된 상수 정의
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

    @staticmethod
    def get_top_100_games(
        genre_id: int, search: str = "", fuzzy: bool = False
    ) -> list[Game]:
        now = timezone.now()

        # 1. 기본 필터링
        queryset = Game.objects.filter(
            total_rating__isnull=False,
            total_rating_count__gte=50,
            first_release_date__lte=now,
            parent_game__isnull=True,
            is_ban=False,
        ).order_by("-total_rating", "-total_rating_count")

        # 2. 검색어 필터링
        if search:
            if fuzzy:
                words = search.split()
                q = Q()
                for word in words:
                    q |= Q(name__icontains=word)
                queryset = queryset.filter(q)
            else:
                queryset = queryset.filter(name__icontains=search)

        # 3. 장르 필터링 (0은 전체)
        if genre_id != 0:
            target_igdb_ids = GameTop100Service.GENRE_MAPPING.get(genre_id, [])
            if not target_igdb_ids:
                return []

            genre_filter = Q()
            for igdb_id in target_igdb_ids:
                genre_filter |= Q(genres__contains=[igdb_id])
            queryset = queryset.filter(genre_filter).distinct()

        # 4. 후보군 추출
        candidates = queryset[: GameTop100Service.CANDIDATE_LIMIT]

        # 5. 중복 에디션 제거 로직 (기존 로직 유지)
        unique_games: list[Game] = []
        seen_collections: set[int] = set()
        seen_base_names: set[str] = set()

        for game in candidates:
            if game.collection is not None:
                if game.collection in seen_collections:
                    continue
                seen_collections.add(game.collection)
            else:
                base_name = game.name.split(":")[0].split("-")[0].strip().lower()
                if base_name in seen_base_names:
                    continue
                seen_base_names.add(base_name)
            unique_games.append(game)

        return unique_games[:100]
