from django.db.models import Q
from django.utils import timezone

from apps.games.models import Game


class GameTop100Service:
    # 기획서 및 명세서에 따른 장르 매핑
    GENRE_MAPPING = {
        1: [25, 33],  # 액션 (핵 앤 슬래시, 아케이드)
        2: [31, 2],  # 어드벤처 (어드벤처, 포인트 앤 클릭)
        3: [12],  # RPG (역할수행)
        4: [5],  # 슈팅 (FPS/TPS)
        5: [15, 11, 16, 24, 36],  # 전략 (전략, RTS, TBS, 전술, MOBA)
        6: [13],  # 시뮬레이션
        7: [14],  # 스포츠
        8: [10],  # 레이싱
        9: [9, 26, 30],  # 퍼즐 (퍼즐, 퀴즈, 핀볼)
        10: [8],  # 플랫폼
        11: [4],  # 격투
        12: [35],  # 보드/카드 게임
        13: [7],  # 음악
        14: [34],  # 비주얼 노벨
    }

    @staticmethod
    def get_top_100_games(genre_id: int):
        """
        중복된 에디션을 제거하고 순수한 TOP 100 리스트를 반환합니다.
        """
        now = timezone.now()

        # 1. 기본 필터링 (중복 제거를 위해 넉넉하게 300개 정도 가져옵니다)
        queryset = Game.objects.filter(
            platforms__contains=6,
            total_rating__isnull=False,
            total_rating_count__gte=50,
            first_release_date__lte=now,
        ).order_by("-total_rating", "-total_rating_count")

        # 2. 장르 필터링 (0이 아닐 경우)
        if genre_id != 0:
            target_igdb_ids = GameTop100Service.GENRE_MAPPING.get(genre_id, [])
            if target_igdb_ids:
                genre_filter = Q()
                for igdb_id in target_igdb_ids:
                    genre_filter |= Q(genres__contains=igdb_id)
                queryset = queryset.filter(genre_filter).distinct()
            else:
                return []

        # 3. [핵심] 동일 게임(에디션 중복) 제거 로직
        unique_games = []
        seen_base_names = set()

        for game in queryset:
            # 이름에서 ':', '-' 등을 기준으로 앞부분(핵심 제목)만 추출
            # 예: "The Witcher 3: Wild Hunt - GOTY" -> "The Witcher 3"
            raw_name = game.name
            base_name = raw_name.split(":")[0].split("-")[0].strip().lower()

            # 특수 케이스: "God of War"와 "God of War Ragnarök"은 다른 게임이므로 구분 필요
            # 하지만 "The Witcher 3" 시리즈는 하나로 묶는 것이 깔끔합니다.
            if base_name not in seen_base_names:
                unique_games.append(game)
                seen_base_names.add(base_name)

            # 100개가 모두 채워지면 중단
            if len(unique_games) >= 100:
                break

        return unique_games
