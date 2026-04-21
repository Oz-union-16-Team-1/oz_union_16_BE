import logging
import re
import time

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# 팀 협업을 위한 장르 상수
GENRE_ACTION = 1
GENRE_ADVENTURE = 2
GENRE_RPG = 3
GENRE_SHOOTER = 4
GENRE_STRATEGY = 5
GENRE_SIMULATION = 6
GENRE_SPORTS = 7
GENRE_RACING = 8
GENRE_PUZZLE = 9
GENRE_PLATFORM = 10
GENRE_FIGHTING = 11
GENRE_CARD_BOARD = 12
GENRE_MUSIC = 13
GENRE_VISUAL_NOVEL = 14


class IGDB:
    def __init__(self):
        self.url = settings.IGDB_BASE_URL
        self.timeout = settings.IGDB_TIMEOUT_SEC
        self.headers = {
            "Client-ID": settings.IGDB_ID,
            "Authorization": f"Bearer {settings.IGDB_ACCESS_TOKEN}",
        }
        # 중복 에디션 제거를 위한 정규식
        self.clean_pattern = re.compile(
            r"[:\-].*|\b(Remastered|Remake|Edition|Director\'s Cut|GOTY|Complete|Bundle|Ultimate|Legendary|Shadow of the Erdtree|Definitive)\b",
            re.IGNORECASE,
        )
        # 서비스용 장르 ID와 IGDB 내부 ID 매핑
        self.genre_mapping = {
            GENRE_ACTION: [25, 4],
            GENRE_ADVENTURE: [31, 2],
            GENRE_RPG: [12],
            GENRE_SHOOTER: [5],
            GENRE_STRATEGY: [15, 11, 36],
            GENRE_SIMULATION: [13],
            GENRE_SPORTS: [14],
            GENRE_RACING: [10],
            GENRE_PUZZLE: [9, 26, 30],
            GENRE_PLATFORM: [8],
            GENRE_FIGHTING: [4],
            GENRE_CARD_BOARD: [35, 16],
            GENRE_MUSIC: [7],
            GENRE_VISUAL_NOVEL: [32],
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

    def query_games(self, *, fields, where, sort=None, limit=500, offset=0):
        query = f"fields {fields}; where {where}; "
        if sort:
            query += f"sort {sort}; "
        query += f"limit {limit}; offset {offset};"
        return self.query_games_raw(query)

    def _apply_freshness_weight(self, games):
        now = int(time.time())
        three_years_sec = 3 * 365 * 24 * 60 * 60

        for game in games:
            release_date = game.get("first_release_date", now)
            age = now - release_date

            # 오늘 출시=1.2, 3년 전 출시=1.0 가중치 산출
            weight = 1.0 + (max(0, three_years_sec - age) / three_years_sec) * 0.2
            game["weighted_rating"] = game.get("total_rating", 0) * weight

        return sorted(games, key=lambda x: x["weighted_rating"], reverse=True)

    def _fetch_and_clean(self, query, limit=100):
        try:
            response = requests.post(self.url, headers=self.headers, data=query)
            response.raise_for_status()
            raw_data = response.json()

            unique_games = {}
            for g in raw_data:
                # 제목 정제 및 중복 제거
                clean_name = self.clean_pattern.split(g["name"])[0].strip()
                rating = g.get("total_rating", 0)

                if "cover" in g and "url" in g["cover"]:
                    g["cover"]["url"] = f"https:{g['cover']['url']}"

                # 동일 제목 중 평점이 가장 높은 버전만 선택
                if clean_name not in unique_games or rating > unique_games[
                    clean_name
                ].get("total_rating", 0):
                    unique_games[clean_name] = g

            # 가중치 적용 및 최종 정렬
            weighted_list = self._apply_freshness_weight(list(unique_games.values()))
            return weighted_list[:limit]

        except Exception as e:
            logger.error(f"IGDB API 통신 에러: {e}")
            return None

    def get_games(self, genre_id=None, limit=100):
        # 1. 캐시 키 생성
        cache_key = f"igdb_recent_top_{genre_id if genre_id else 'all'}_{limit}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data

        # 2. 3년 내 타임스탬프 계산
        start_date = int(time.time()) - (3 * 365 * 24 * 60 * 60)

        # 3. 쿼리 빌드
        # 최신작 발굴을 위해 투표수(count) 기준을 30으로 소폭 낮춤
        where_clause = f"platforms = (6) & first_release_date >= {start_date} & total_rating != null & total_rating_count > 30"

        if genre_id:
            target_ids = self.genre_mapping.get(int(genre_id))
            if not target_ids:
                return "BAD_REQUEST"
            ids_str = ",".join(map(str, target_ids))
            where_clause += f" & genres = ({ids_str})"

        # 중복 제거
        query = (
            f"fields name, total_rating, total_rating_count, first_release_date, cover.url; "
            f"where {where_clause}; "
            f"sort total_rating desc; "
            f"limit 500;"
        )

        result = self._fetch_and_clean(query, limit)

        if result and result != "BAD_REQUEST":
            cache.set(cache_key, result, 3600)  # 1시간 캐싱

        return result


igdb_client = IGDB()
