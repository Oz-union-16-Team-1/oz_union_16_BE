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
        # 장르 매핑 (기존 로직 유지)
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

    def get_games(self, genre_id=None, limit=20, offset=0):
        """기본 게임 목록 조회 (평점순)"""
        where_clause = "total_rating != null & total_rating_count > 5"

        # 필드 리스트 정의 (category 추가 및 collection 확인)
        full_fields = [
            "name",
            "slug",
            "summary",
            "storyline",
            "first_release_date",
            "status",
            "category",  # 추가됨
            "franchises",
            "version_title",
            "remakes",
            "remasters",
            "expansions",
            "dlcs",
            "language_supports",
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

        # 3. 장르 필터
        if genre_id:
            gid = int(genre_id)
            target_genre_ids = self.genre_mapping.get(gid, [])
            if target_genre_ids:
                ids_str = ",".join(map(str, target_genre_ids))
                where_clause += f" & genres = ({ids_str})"

        # 4. 최종 쿼리
        query = (
            f"fields {fields_str}; "
            f"where {where_clause}; "
            f"sort total_rating desc; "
            f"limit {limit}; "
            f"offset {offset};"
        )

        return self.query_games_raw(query)

# 싱글톤 인스턴스 생성
igdb_client = IGDB()