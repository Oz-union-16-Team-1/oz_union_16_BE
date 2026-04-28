from rest_framework import serializers

from apps.core.igdb import IGDB
from apps.games.models import Game

GENRE_NAME_MAP: dict[int, str] = IGDB.GENRE_NAME_MAP


class GameDetailMediaSerializer(serializers.Serializer):
    promo_video_url = serializers.CharField(allow_null=True)
    promo_embed_url = serializers.CharField(allow_null=True)
    cover_image_url = serializers.CharField(allow_null=True)


class GameDetailExternalLinksSerializer(serializers.Serializer):
    official_site = serializers.CharField(allow_null=True)
    steam = serializers.CharField(allow_null=True)
    epic_store = serializers.CharField(allow_null=True)


class GameListDetailSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="name", allow_null=True, read_only=True)
    genres = serializers.SerializerMethodField()
    release_date = serializers.SerializerMethodField()
    developer = serializers.SerializerMethodField()
    publisher = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    external_links = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "game_id",
            "title",
            "genres",
            "release_date",
            "developer",
            "publisher",
            "media",
            "description",
            "external_links",
            "is_liked",
            "like_count",
        ]

    def get_genres(self, obj: Game) -> list[str]:
        genre_ids = obj.genres or []
        genres = []

        for genre in genre_ids:
            if isinstance(genre, dict):
                name = genre.get("name")
                if isinstance(name, str) and name.strip():
                    genres.append(name.strip())
                    continue
                genre = genre.get("id")

            try:
                genre_id = int(genre)
            except TypeError, ValueError:
                continue

            genre_name = GENRE_NAME_MAP.get(genre_id)
            if genre_name:
                genres.append(genre_name)

        return genres

    def get_release_date(self, obj: Game) -> str | None:
        if obj.first_release_date is None:
            return None
        return obj.first_release_date.date().isoformat()

    def get_developer(self, obj: Game) -> str | None:
        return self._get_company_name(obj.involved_companies, "developer")

    def get_publisher(self, obj: Game) -> str | None:
        return self._get_company_name(obj.involved_companies, "publisher")

    def get_media(self, obj: Game) -> dict[str, str | None]:
        video_id = self._get_first_video_id(obj.videos)

        return {
            "promo_video_url": (
                f"https://www.youtube.com/watch?v={video_id}" if video_id else None
            ),
            "promo_embed_url": (
                f"https://www.youtube.com/embed/{video_id}" if video_id else None
            ),
            "cover_image_url": self._to_igdb_image_url(obj.cover, "t_1080p"),
        }

    def get_description(self, obj: Game) -> str | None:
        descriptions = []
        for value in [obj.summary, obj.storyline]:
            if isinstance(value, str) and value.strip():
                descriptions.append(value.strip())

        if not descriptions:
            return None

        return "\n\n".join(dict.fromkeys(descriptions))

    def get_external_links(self, obj: Game) -> dict[str, str | None]:
        links: dict[str, str | None] = {
            "official_site": None,
            "steam": None,
            "epic_store": None,
        }

        for website in obj.websites or []:
            if not isinstance(website, dict):
                continue

            url = website.get("url")
            if not isinstance(url, str) or not url.strip():
                continue

            url = url.strip()
            category = website.get("category")

            if category == 1 and links["official_site"] is None:
                links["official_site"] = url
            elif category == 13 and links["steam"] is None:
                links["steam"] = url
            elif category == 16 and links["epic_store"] is None:
                links["epic_store"] = url
            elif "store.steampowered.com" in url and links["steam"] is None:
                links["steam"] = url
            elif "store.epicgames.com" in url and links["epic_store"] is None:
                links["epic_store"] = url

        return links

    def get_is_liked(self, obj: Game) -> bool:
        liked_game_ids: set[int] = self.context.get("liked_game_ids", set())
        return obj.game_id in liked_game_ids

    @staticmethod
    def _get_company_name(companies: object, role: str) -> str | None:
        if not isinstance(companies, list):
            return None

        for company in companies:
            if not isinstance(company, dict) or not company.get(role):
                continue

            company_name = company.get("company_name")
            if isinstance(company_name, str) and company_name.strip():
                return company_name.strip()

        return None

    @staticmethod
    def _get_first_video_id(videos: object) -> str | None:
        if not isinstance(videos, list) or not videos:
            return None

        first_video = videos[0]
        if isinstance(first_video, str) and first_video.strip():
            return first_video.strip()

        if isinstance(first_video, dict):
            video_id = first_video.get("video_id")
            if isinstance(video_id, str) and video_id.strip():
                return video_id.strip()

        return None

    @staticmethod
    def _to_igdb_image_url(image_id: str | None, size: str) -> str | None:
        if not image_id:
            return None

        if image_id.startswith("http://") or image_id.startswith("https://"):
            return image_id

        return f"https://images.igdb.com/igdb/image/upload/{size}/{image_id}.jpg"


class GameListDetailResponseSerializer(GameListDetailSerializer):
    media = GameDetailMediaSerializer(read_only=True)
    external_links = GameDetailExternalLinksSerializer(read_only=True)
