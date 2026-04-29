import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class IGDB:

    GENRE_NAME_MAP = {
        1: "액션",
        2: "포인트 앤 클릭",
        4: "격투",
        5: "슈팅",
        7: "음악",
        8: "플랫폼",
        9: "퍼즐",
        10: "레이싱",
        11: "실시간 전략",
        12: "RPG",
        13: "시뮬레이션",
        14: "스포츠",
        15: "전략",
        16: "턴제 전략",
        24: "전술",
        25: "핵 앤 슬래시",
        26: "퀴즈/상식",
        30: "핀볼",
        31: "어드벤처",
        32: "인디",
        33: "아케이드",
        34: "비주얼 노벨",
        35: "카드 및 보드 게임",
        36: "모바(MOBA)",
    }

    def __init__(self):
        self.url = settings.IGDB_BASE_URL
        self.timeout = settings.IGDB_TIMEOUT_SEC
        self.headers = {
            "Client-ID": settings.IGDB_ID,
            "Authorization": f"Bearer {settings.IGDB_ACCESS_TOKEN}",
        }
        self.genre_mapping = {
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

    def query_games_raw(self, query):
        try:
            response = requests.post(
                self.url,
                headers=self.headers,
                data=query,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"IGDB API 통신 에러: {e}")
            return None

    def query_games(self, query=None, **kwargs):
        """
        mypy 에러 해결 및 가변 인자 처리를 위한 메서드.
        키워드 인자(fields, where 등)가 들어오면 IGDB 쿼리 문자열로 변환합니다.
        """
        if query:
            return self.query_games_raw(query)

        # 키워드 인자가 들어온 경우 (fields, where, sort, limit, offset 등)
        query_parts = []
        for key, value in kwargs.items():
            query_parts.append(f"{key} {value};")

        final_query = " ".join(query_parts)
        return self.query_games_raw(final_query)

    def get_games(self, genre_id=None, limit=500, offset=0, pc_only=False):
        """기본 게임 목록 조회 (평점순)"""
        where_conditions = []

        full_fields = [
            "name",
            "slug",
            "summary",
            "storyline",
            "first_release_date",
            "status",
            "category",
            "franchises",
            "version_title",
            "rating",
            "rating_count",
            "aggregated_rating",
            "aggregated_rating_count",
            "total_rating",
            "total_rating_count",
            "follows",
            "hypes",
            "game_modes",
            "player_perspectives",
            "themes",
            "genres",
            "keywords",
            "multiplayer_modes",
            "screenshots.image_id",
            "videos.video_id",
            "websites.category",
            "websites.url",
            "involved_companies.developer",
            "involved_companies.publisher",
            "involved_companies.company.name",
            "collection",
            "parent_game",
            "cover.image_id",
            "game_type",
        ]
        fields_str = ", ".join(full_fields)

        if genre_id:
            gid = int(genre_id)
            target_genre_ids = self.genre_mapping.get(gid, [])
            if target_genre_ids:
                ids_str = ",".join(map(str, target_genre_ids))
                where_conditions.append(f"genres = ({ids_str})")

        if pc_only:
            where_conditions.append("platforms = (6)")

        where_part = ""
        if where_conditions:
            where_part = f"where {' & '.join(where_conditions)}; "

        query = (
            f"fields {fields_str}; "
            f"{where_part}"
            f"sort total_rating desc; "
            f"limit {limit}; "
            f"offset {offset};"
        )

        return self.query_games_raw(query)

    def get_ban_games(self, limit=500, offset=0):
        """
        성인용 조건(등급 OR 테마 OR 키워드 OR 카테고리) 중 하나라도 만족하는
        PC 플랫폼 게임의 ID 목록을 조회합니다.
        """
        # 조건 구성:
        # 1. age_ratings.rating = 26 (한국 청불)
        # 2. themes = 42 (에로틱)
        # 3. keywords.slug = ("eroge", "sexual-content", "hentai")
        # 4. category = 7 (Restricted)
        # 위 조건 중 하나라도 만족(OR)하고, 반드시 platforms = 6 (PC)일 것(AND)

        where_query = (
            "where ("
            "age_ratings.rating = 26 | "
            "themes = 42 | "
            'keywords.slug = ("eroge", "sexual-content", "hentai") | '
            "category = 7"
            ") & platforms = 6;"
        )

        query = f"fields id; " f"{where_query} " f"limit {limit}; " f"offset {offset};"

        results = self.query_games_raw(query)
        return results if results else []


igdb_client = IGDB()
