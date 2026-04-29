from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.games.models import Game
from apps.games.service.game_like_services import (
    GameLikeBookmarkNotFoundError,
    GameLikeGameNotFoundError,
    GameLikeService,
)
from apps.users.models import UserLikeBookmark

if TYPE_CHECKING:
    UserType = Any
else:
    UserType = get_user_model()


class GameLikeServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserType.objects.create_user(
            login_id="likeuser",
            password="testpassword123",
            name="좋아요유저",
            nickname="likeusernick",
            gender="M",
        )
        cls.game = Game.objects.create(
            game_id=801,
            name="Like Service Game",
            slug="like-service-game",
            like_count=3,
        )
        cls.banned_game = Game.objects.create(
            game_id=802,
            name="Banned Like Game",
            slug="banned-like-game",
            is_ban=True,
        )

    def test_like_game_creates_bookmark_and_increases_like_count(self):
        data = GameLikeService.like_game(user=self.user, game_id=self.game.game_id)

        self.game.refresh_from_db()
        self.assertEqual(data, {"game_id": self.game.game_id, "like_count": 4})
        self.assertEqual(self.game.like_count, 4)
        self.assertTrue(
            UserLikeBookmark.objects.filter(
                user=self.user,
                game=self.game,
            ).exists()
        )

    def test_like_game_does_not_increase_like_count_twice(self):
        UserLikeBookmark.objects.create(user=self.user, game=self.game)

        data = GameLikeService.like_game(user=self.user, game_id=self.game.game_id)

        self.game.refresh_from_db()
        self.assertEqual(data, {"game_id": self.game.game_id, "like_count": 3})
        self.assertEqual(self.game.like_count, 3)
        self.assertEqual(
            UserLikeBookmark.objects.filter(user=self.user, game=self.game).count(),
            1,
        )

    def test_like_game_raises_not_found_for_missing_game(self):
        with self.assertRaisesMessage(
            GameLikeGameNotFoundError,
            "해당 게임을 찾을 수 없습니다.",
        ):
            GameLikeService.like_game(user=self.user, game_id=999999)

    def test_like_game_raises_not_found_for_banned_game(self):
        with self.assertRaisesMessage(
            GameLikeGameNotFoundError,
            "해당 게임을 찾을 수 없습니다.",
        ):
            GameLikeService.like_game(user=self.user, game_id=self.banned_game.game_id)

    def test_unlike_game_deletes_bookmark_and_decreases_like_count(self):
        UserLikeBookmark.objects.create(user=self.user, game=self.game)

        data = GameLikeService.unlike_game(user=self.user, game_id=self.game.game_id)

        self.game.refresh_from_db()
        self.assertEqual(data, {"game_id": self.game.game_id, "like_count": 2})
        self.assertEqual(self.game.like_count, 2)
        self.assertFalse(
            UserLikeBookmark.objects.filter(
                user=self.user,
                game=self.game,
            ).exists()
        )

    def test_unlike_game_does_not_decrease_like_count_below_zero(self):
        zero_count_game = Game.objects.create(
            game_id=803,
            name="Zero Count Game",
            slug="zero-count-game",
            like_count=0,
        )
        UserLikeBookmark.objects.create(user=self.user, game=zero_count_game)

        data = GameLikeService.unlike_game(
            user=self.user,
            game_id=zero_count_game.game_id,
        )

        zero_count_game.refresh_from_db()
        self.assertEqual(data, {"game_id": zero_count_game.game_id, "like_count": 0})
        self.assertEqual(zero_count_game.like_count, 0)

    def test_unlike_game_raises_not_found_for_missing_game(self):
        with self.assertRaisesMessage(
            GameLikeGameNotFoundError,
            "해당 게임을 찾을 수 없습니다.",
        ):
            GameLikeService.unlike_game(user=self.user, game_id=999999)

    def test_unlike_game_raises_not_found_for_missing_bookmark(self):
        with self.assertRaisesMessage(
            GameLikeBookmarkNotFoundError,
            "좋아요 기록을 찾을 수 없습니다.",
        ):
            GameLikeService.unlike_game(user=self.user, game_id=self.game.game_id)


class GameLikeViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserType.objects.create_user(
            login_id="likeviewuser",
            password="testpassword123",
            name="좋아요뷰유저",
            nickname="likeviewnick",
            gender="M",
        )
        cls.game = Game.objects.create(
            game_id=901,
            name="Like View Game",
            slug="like-view-game",
            like_count=10,
        )
        cls.banned_game = Game.objects.create(
            game_id=902,
            name="Banned Like View Game",
            slug="banned-like-view-game",
            is_ban=True,
        )

    def setUp(self):
        self.client = APIClient()

    def test_like_view_success(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("game_like", kwargs={"game_id": self.game.game_id})

        response = self.client.post(url)

        self.game.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data,
            {"game_id": self.game.game_id, "like_count": 11},
        )
        self.assertEqual(self.game.like_count, 11)

    def test_like_view_requires_authentication(self):
        url = reverse("game_like", kwargs={"game_id": self.game.game_id})

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data,
            {"error_detail": "자격 인증 데이터가 제공되지 않았습니다."},
        )

    def test_like_view_returns_404_for_missing_game(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("game_like", kwargs={"game_id": 999999})

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data,
            {"error_detail": "해당 게임을 찾을 수 없습니다."},
        )

    def test_like_view_returns_404_for_banned_game(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("game_like", kwargs={"game_id": self.banned_game.game_id})

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data,
            {"error_detail": "해당 게임을 찾을 수 없습니다."},
        )

    def test_unlike_view_success(self):
        self.client.force_authenticate(user=self.user)
        UserLikeBookmark.objects.create(user=self.user, game=self.game)
        url = reverse("game_like", kwargs={"game_id": self.game.game_id})

        response = self.client.delete(url)

        self.game.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"game_id": self.game.game_id, "like_count": 9},
        )
        self.assertEqual(self.game.like_count, 9)

    def test_unlike_view_requires_authentication(self):
        url = reverse("game_like", kwargs={"game_id": self.game.game_id})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data,
            {"error_detail": "자격 인증 데이터가 제공되지 않았습니다."},
        )

    def test_unlike_view_returns_404_for_missing_bookmark(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("game_like", kwargs={"game_id": self.game.game_id})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data,
            {"error_detail": "좋아요 기록을 찾을 수 없습니다."},
        )

    def test_unlike_view_returns_404_for_missing_game(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("game_like", kwargs={"game_id": 999999})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data,
            {"error_detail": "해당 게임을 찾을 수 없습니다."},
        )
