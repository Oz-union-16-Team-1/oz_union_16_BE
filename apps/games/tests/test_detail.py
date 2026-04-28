from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from apps.games.models import Game
from apps.games.serializer.game_list_detail_serializers import GameListDetailSerializer
from apps.games.service.game_list_detail_services import (
    GameDetailNotFoundError,
    GameListDetailService,
)
from apps.users.models import UserLikeBookmark

if TYPE_CHECKING:
    UserType = Any
else:
    UserType = get_user_model()


class GameListDetailSerializerTest(TestCase):
    def test_serializer_returns_full_detail_response(self):
        game = Game.objects.create(
            game_id=501,
            name="Elden Ring",
            slug="elden-ring",
            summary="Summary text.",
            storyline="Storyline text.",
            first_release_date=datetime(2024, 6, 21, tzinfo=timezone.utc),
            genres=[12, {"name": "커스텀 장르"}, {"id": 31}, "invalid", None, 999],
            videos=["trailer123"],
            cover="co1234",
            websites=[
                "invalid",
                {"category": 1},
                {"category": 1, "url": " https://official.example.com "},
                {"category": 13, "url": "https://store.steampowered.com/app/501"},
                {"category": 16, "url": "https://store.epicgames.com/game/501"},
            ],
            involved_companies=[
                "invalid",
                {"developer": True},
                {"company_name": "FromSoftware", "developer": True},
                {"company_name": "Bandai Namco", "publisher": True},
            ],
            like_count=1250,
        )

        data = GameListDetailSerializer(
            game,
            context={"liked_game_ids": {game.game_id}},
        ).data

        self.assertEqual(data["game_id"], 501)
        self.assertEqual(data["title"], "Elden Ring")
        self.assertEqual(data["genres"], ["역할수행(RPG)", "커스텀 장르", "어드벤처"])
        self.assertEqual(data["release_date"], "2024-06-21")
        self.assertEqual(data["developer"], "FromSoftware")
        self.assertEqual(data["publisher"], "Bandai Namco")
        self.assertEqual(
            data["media"],
            {
                "promo_video_url": "https://www.youtube.com/watch?v=trailer123",
                "promo_embed_url": "https://www.youtube.com/embed/trailer123",
                "cover_image_url": (
                    "https://images.igdb.com/igdb/image/upload/t_1080p/co1234.jpg"
                ),
            },
        )
        self.assertEqual(data["description"], "Summary text.\n\nStoryline text.")
        self.assertEqual(
            data["external_links"],
            {
                "official_site": "https://official.example.com",
                "steam": "https://store.steampowered.com/app/501",
                "epic_store": "https://store.epicgames.com/game/501",
            },
        )
        self.assertTrue(data["is_liked"])
        self.assertEqual(data["like_count"], 1250)

    def test_serializer_returns_nulls_for_missing_optional_data(self):
        game = Game.objects.create(
            game_id=502,
            name="Missing Data Game",
            slug="missing-data-game",
            summary=" ",
            storyline="",
            first_release_date=None,
            genres=None,
            videos=[],
            cover=None,
            websites=["invalid", {"category": 1}, {"url": " "}],
            involved_companies="invalid",
        )

        data = GameListDetailSerializer(game).data

        self.assertEqual(data["genres"], [])
        self.assertIsNone(data["release_date"])
        self.assertIsNone(data["developer"])
        self.assertIsNone(data["publisher"])
        self.assertEqual(
            data["media"],
            {
                "promo_video_url": None,
                "promo_embed_url": None,
                "cover_image_url": None,
            },
        )
        self.assertIsNone(data["description"])
        self.assertEqual(
            data["external_links"],
            {
                "official_site": None,
                "steam": None,
                "epic_store": None,
            },
        )
        self.assertFalse(data["is_liked"])

    def test_serializer_supports_dict_video_and_absolute_cover_url(self):
        game = Game.objects.create(
            game_id=503,
            name="Absolute Cover Game",
            slug="absolute-cover-game",
            videos=[{"video_id": "dict_video"}],
            cover="https://cdn.example.com/cover.jpg",
        )

        data = GameListDetailSerializer(game).data

        self.assertEqual(
            data["media"],
            {
                "promo_video_url": "https://www.youtube.com/watch?v=dict_video",
                "promo_embed_url": "https://www.youtube.com/embed/dict_video",
                "cover_image_url": "https://cdn.example.com/cover.jpg",
            },
        )

    def test_serializer_uses_store_url_fallbacks(self):
        game = Game.objects.create(
            game_id=504,
            name="Fallback Link Game",
            slug="fallback-link-game",
            websites=[
                {
                    "category": None,
                    "url": "https://store.steampowered.com/app/fallback",
                },
                {
                    "category": None,
                    "url": "https://store.epicgames.com/p/fallback",
                },
            ],
        )

        data = GameListDetailSerializer(game).data

        self.assertEqual(
            data["external_links"],
            {
                "official_site": None,
                "steam": "https://store.steampowered.com/app/fallback",
                "epic_store": "https://store.epicgames.com/p/fallback",
            },
        )

    def test_serializer_ignores_blank_company_and_video_values(self):
        game = Game.objects.create(
            game_id=505,
            name="Blank Metadata Game",
            slug="blank-metadata-game",
            videos=[{"video_id": " "}],
            involved_companies=[
                {"company_name": " ", "developer": True},
                {"company_name": "Publisher Only", "developer": False},
            ],
        )

        data = GameListDetailSerializer(game).data

        self.assertIsNone(data["developer"])
        self.assertIsNone(data["media"]["promo_video_url"])
        self.assertIsNone(data["media"]["promo_embed_url"])


class GameListDetailServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.game = Game.objects.create(
            game_id=601,
            name="Service Game",
            slug="service-game",
            genres=[12],
        )
        cls.banned_game = Game.objects.create(
            game_id=602,
            name="Banned Game",
            slug="banned-game",
            is_ban=True,
        )
        cls.user = UserType.objects.create_user(
            login_id="detailuser",
            password="testpassword123",
            name="상세유저",
            nickname="detailnick",
            gender="M",
        )
        cls.other_user = UserType.objects.create_user(
            login_id="detailother",
            password="testpassword123",
            name="다른유저",
            nickname="detailothernick",
            gender="W",
        )
        UserLikeBookmark.objects.create(user=cls.user, game=cls.game)

    def test_service_returns_detail_for_anonymous_user(self):
        data = GameListDetailService.get_game_detail(
            game_id=self.game.game_id,
            user=AnonymousUser(),
        )

        self.assertEqual(data["game_id"], self.game.game_id)
        self.assertEqual(data["title"], self.game.name)
        self.assertFalse(data["is_liked"])

    def test_service_returns_liked_detail_for_authenticated_user(self):
        data = GameListDetailService.get_game_detail(
            game_id=self.game.game_id,
            user=self.user,
        )

        self.assertTrue(data["is_liked"])

    def test_service_returns_not_liked_for_authenticated_user_without_bookmark(self):
        data = GameListDetailService.get_game_detail(
            game_id=self.game.game_id,
            user=self.other_user,
        )

        self.assertFalse(data["is_liked"])

    def test_service_raises_not_found_for_missing_game(self):
        with self.assertRaisesMessage(
            GameDetailNotFoundError,
            "해당 게임을 찾을 수 없습니다.",
        ):
            GameListDetailService.get_game_detail(game_id=999999, user=self.user)

    def test_service_raises_not_found_for_banned_game(self):
        with self.assertRaisesMessage(
            GameDetailNotFoundError,
            "해당 게임을 찾을 수 없습니다.",
        ):
            GameListDetailService.get_game_detail(
                game_id=self.banned_game.game_id,
                user=self.user,
            )
