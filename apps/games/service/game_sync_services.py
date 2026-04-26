from datetime import datetime,timezone

from apps.core.igdb import igdb_client
from apps.games.models import Game


class GameSyncService:
    @staticmethod
    def prepare_game_data(raw_data):
        """IGDB 원본 데이터를 DB 모델 규격에 맞게 전처리합니다."""

        # 날짜 데이터 처리 (Unix Timestamp -> aware datetime UTC)
        raw_ts = raw_data.get("first_release_date")
        converted_date = None
        if raw_ts:
            try:
                converted_date = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
            except TypeError:
                converted_date = None
            except ValueError:
                converted_date = None

        # 1. 단일 값 필드 가공
        processed = {
            "name": raw_data.get("name"),
            "slug": raw_data.get("slug"),
            "summary": raw_data.get("summary", ""),
            "storyline": raw_data.get("storyline", ""),
            "category": raw_data.get("category"),
            "status": raw_data.get("status"),
            "first_release_date": converted_date,
            "version_title": raw_data.get("version_title", ""),
            "rating": raw_data.get("rating"),
            "rating_count": raw_data.get("rating_count", 0),
            "aggregated_rating": raw_data.get("aggregated_rating"),
            "aggregated_rating_count": raw_data.get("aggregated_rating_count", 0),
            "total_rating": raw_data.get("total_rating"),
            "total_rating_count": raw_data.get("total_rating_count", 0),
            "follows": raw_data.get("follows", 0),
            "hypes": raw_data.get("hypes", 0),
            "game_type": raw_data.get("game_type"),
            "parent_game": raw_data.get("parent_game"),
        }

        # 2. 리스트/JSONField 가공 (기본값 [] 설정으로 null 방지)
        processed.update(
            {
                "genres": raw_data.get("genres", []),
                "themes": raw_data.get("themes", []),
                "keywords": raw_data.get("keywords", []),
                "game_modes": raw_data.get("game_modes", []),
                "player_perspectives": raw_data.get("player_perspectives", []),
                "language_supports": raw_data.get("language_supports", []),
                "franchises": raw_data.get("franchises", []),
                "remakes": raw_data.get("remakes", []),
                "remasters": raw_data.get("remasters", []),
                "expansions": raw_data.get("expansions", []),
                "dlcs": raw_data.get("dlcs", []),
                "multiplayer_modes": raw_data.get("multiplayer_modes", []),
                "involved_companies": raw_data.get("involved_companies", []),
            }
        )

        # 3. 중첩 객체(Nested Object) 가공 - ID나 특정 값만 추출

        # Collection 처리 (딕셔너리로 올 경우 ID만 추출)
        collection_obj = raw_data.get("collection")
        processed["collection"] = (
            collection_obj.get("id")
            if isinstance(collection_obj, dict)
            else collection_obj
        )

        # Cover 처리
        cover_obj = raw_data.get("cover")
        processed["cover"] = (
            cover_obj.get("image_id") if isinstance(cover_obj, dict) else None
        )

        # Screenshots (image_id 리스트로 변환)
        processed["screenshots"] = [
            s.get("image_id")
            for s in raw_data.get("screenshots", [])
            if isinstance(s, dict) and "image_id" in s
        ]

        # Videos (video_id 리스트로 변환)
        processed["videos"] = [
            v.get("video_id")
            for v in raw_data.get("videos", [])
            if isinstance(v, dict) and "video_id" in v
        ]

        # Websites (url 리스트로 변환)
        processed["websites"] = [
            w.get("url")
            for w in raw_data.get("websites", [])
            if isinstance(w, dict) and "url" in w
        ]

        return processed

    @classmethod
    def sync_top_games(cls):
        """대량의 게임 데이터를 가져와서 DB를 최신화합니다."""
        raw_games = igdb_client.get_games(limit=500)

        if not raw_games:
            return

        for raw_game in raw_games:
            clean_data = cls.prepare_game_data(raw_game)

            # DB 저장 및 업데이트
            Game.objects.update_or_create(game_id=raw_game["id"], defaults=clean_data)
