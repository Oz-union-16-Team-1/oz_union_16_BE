import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class IGDB:
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

    def get_games(self, genre_id=None, limit=500, offset=0):
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
            "websites.url",
            "involved_companies",
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


igdb_client = IGDB()
