from datetime import datetime, timezone

from apps.core.igdb import igdb_client
from apps.games.models import Game


class GameSyncService:
    @staticmethod
    def _extract_image_id(value):
        if isinstance(value, dict):
            image_id = value.get("image_id")
            if isinstance(image_id, str) and image_id.strip():
                return image_id.strip()
            return None

        if isinstance(value, str) and value.strip():
            return value.strip()

        return None

    @staticmethod
    def _normalize_websites(raw_websites):
        normalized = []

        for website in raw_websites or []:
            if isinstance(website, dict):
                url = website.get("url")
                if not isinstance(url, str) or not url.strip():
                    continue

                normalized.append(
                    {
                        "category": website.get("category"),
                        "url": url.strip(),
                    }
                )
                continue

            if isinstance(website, str) and website.strip():
                normalized.append(
                    {
                        "category": None,
                        "url": website.strip(),
                    }
                )

        return normalized

    @staticmethod
    def _normalize_involved_companies(raw_companies):
        normalized = []

        for company in raw_companies or []:
            if not isinstance(company, dict):
                continue

            company_info = company.get("company")
            company_name = None
            if isinstance(company_info, dict):
                raw_name = company_info.get("name")
                if isinstance(raw_name, str) and raw_name.strip():
                    company_name = raw_name.strip()

            if not company_name:
                continue

            normalized.append(
                {
                    "company_name": company_name,
                    "developer": bool(company.get("developer")),
                    "publisher": bool(company.get("publisher")),
                }
            )

        return normalized

    @staticmethod
    def prepare_game_data(raw_data):
        """IGDB 원본 데이터를 DB 모델 규격에 맞게 전처리합니다."""

        raw_ts = raw_data.get("first_release_date")
        converted_date = None
        if raw_ts:
            try:
                converted_date = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
            except TypeError:
                converted_date = None
            except ValueError:
                converted_date = None

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
                "involved_companies": GameSyncService._normalize_involved_companies(
                    raw_data.get("involved_companies", [])
                ),
            }
        )

        collection_obj = raw_data.get("collection")
        processed["collection"] = (
            collection_obj.get("id")
            if isinstance(collection_obj, dict)
            else collection_obj
        )

        processed["cover"] = GameSyncService._extract_image_id(raw_data.get("cover"))

        processed["screenshots"] = [
            image_id
            for s in raw_data.get("screenshots", [])
            if (image_id := GameSyncService._extract_image_id(s)) is not None
        ]

        processed["videos"] = [
            video_id
            for v in raw_data.get("videos", [])
            if isinstance(v, dict)
            and isinstance((video_id := v.get("video_id")), str)
            and video_id.strip()
        ]

        processed["websites"] = GameSyncService._normalize_websites(
            raw_data.get("websites", [])
        )

        return processed

    @classmethod
    def sync_all_games(cls, *, page_size=500, max_pages=0, pc_only=False):
        """
        max_pages=0 이면 응답이 빌 때까지 전체 수집
        """
        scanned = 0
        upserted = 0
        page = 0

        while True:
            if max_pages > 0 and page >= max_pages:
                break

            offset = page * page_size
            raw_games = igdb_client.get_games(
                limit=page_size,
                offset=offset,
                pc_only=pc_only,
            )

            if not raw_games:
                break

            scanned += len(raw_games)

            for raw_game in raw_games:
                clean_data = cls.prepare_game_data(raw_game)
                Game.objects.update_or_create(
                    game_id=raw_game["id"],
                    defaults=clean_data,
                )
                upserted += 1

            if len(raw_games) < page_size:
                break

            page += 1

        return {"scanned": scanned, "upserted": upserted}
