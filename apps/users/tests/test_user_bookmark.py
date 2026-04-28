from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.games.models import Game
from apps.users.models import UserLikeBookmark

if TYPE_CHECKING:
    UserType = Any
else:
    UserType = get_user_model()


class UserLikeBookmarkListTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 유저 생성
        cls.user = UserType.objects.create_user(
            login_id="testuser",
            password="testpassword123",
            name="테스트",
            nickname="테스터",
            gender="M",
        )
        cls.other_user = UserType.objects.create_user(
            login_id="otheruser",
            password="testpassword123",
            name="다른유저",
            nickname="다른테스터",
            gender="W",
        )

        # 게임 생성
        cls.game1 = Game.objects.create(
            game_id=1001,
            name="엘든 링",
            slug="elden-ring",
            cover="t_thumb/elden-ring.jpg",
            genres=[12, 31, 32],
        )
        cls.game2 = Game.objects.create(
            game_id=1002,
            name="로스트아크",
            slug="lost-ark",
            cover="t_thumb/lost-ark.jpg",
            genres=[4, 32],
        )
        cls.game3 = Game.objects.create(
            game_id=1003,
            name="발로란트",
            slug="valorant",
            cover=None,
            genres=[5],
        )

        # 북마크 생성
        cls.bookmark1 = UserLikeBookmark.objects.create(user=cls.user, game=cls.game1)
        cls.bookmark2 = UserLikeBookmark.objects.create(user=cls.user, game=cls.game2)
        cls.bookmark3 = UserLikeBookmark.objects.create(user=cls.user, game=cls.game3)

        cls.url = reverse("user-bookmark-list")

    def setUp(self):
        self.client = APIClient()

    # --- 성공 케이스 ---

    def test_get_bookmark_list_success(self):
        """인증된 유저가 북마크 목록 조회 시 200 OK와 올바른 데이터를 반환하는지 확인"""
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 3)

    def test_get_bookmark_list_response_fields(self):
        """응답 데이터에 필요한 필드가 모두 포함되어 있는지 확인"""
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        result = response.data["results"][0]
        self.assertIn("game_id", result)
        self.assertIn("game_title", result)
        self.assertIn("thumbnail_url", result)
        self.assertIn("genres", result)
        self.assertIn("liked_at", result)

    def test_get_bookmark_list_thumbnail_null(self):
        """cover가 없는 게임의 thumbnail_url이 null로 반환되는지 확인"""
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        game_ids = [r["game_id"] for r in response.data["results"]]
        self.assertIn(1003, game_ids)

        valorant = next(r for r in response.data["results"] if r["game_id"] == 1003)
        self.assertIsNone(valorant["thumbnail_url"])

    def test_get_bookmark_list_genres_is_list(self):
        """genres 필드가 리스트로 반환되는지 확인"""
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for result in response.data["results"]:
            self.assertIsInstance(result["genres"], list)

    def test_get_bookmark_list_genres_name(self):
        """genres 필드가 장르 ID가 아닌 장르 이름으로 반환되는지 확인"""
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 엘든링: genres=[12, 31, 32] -> ["역할수행(RPG)", "어드벤처", "인디"]
        elden_ring = next(r for r in response.data["results"] if r["game_id"] == 1001)
        self.assertEqual(elden_ring["genres"], ["역할수행(RPG)", "어드벤처", "인디"])

        # 로스트아크: genres=[4, 32] -> ["격투", "인디"]
        lost_ark = next(r for r in response.data["results"] if r["game_id"] == 1002)
        self.assertEqual(lost_ark["genres"], ["격투", "인디"])

        # 발로란트: genres=[5] -> ["슈팅"]
        valorant = next(r for r in response.data["results"] if r["game_id"] == 1003)
        self.assertEqual(valorant["genres"], ["슈팅"])

    def test_get_bookmark_list_only_my_bookmarks(self):
        """다른 유저의 북마크는 조회되지 않는지 확인"""
        UserLikeBookmark.objects.create(user=self.other_user, game=self.game1)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)  # 본인 북마크 3개만

    def test_get_bookmark_list_pagination(self):
        """page_size 파라미터로 페이지네이션이 올바르게 동작하는지 확인"""
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url, {"page": 1, "page_size": 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 2)

    def test_get_bookmark_list_empty(self):
        """북마크가 없는 유저 조회 시 빈 리스트 반환 확인"""
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    def test_get_bookmark_list_genres_empty(self):
        """genres가 없는 게임의 genres 필드가 빈 리스트로 반환되는지 확인"""
        game_no_genre = Game.objects.create(
            game_id=1004,
            name="장르없는게임",
            slug="no-genre-game",
            cover=None,
            genres=[],
        )
        UserLikeBookmark.objects.create(user=self.user, game=game_no_genre)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        no_genre_result = next(
            r for r in response.data["results"] if r["game_id"] == 1004
        )
        self.assertEqual(no_genre_result["genres"], [])

    def test_get_bookmark_list_genres_unknown_id(self):
        """GENRE_NAME_MAP에 없는 장르 ID는 결과에서 제외되는지 확인"""
        game_unknown_genre = Game.objects.create(
            game_id=1005,
            name="알수없는장르게임",
            slug="unknown-genre-game",
            cover=None,
            genres=[999],  # 존재하지 않는 장르 ID
        )
        UserLikeBookmark.objects.create(user=self.user, game=game_unknown_genre)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        unknown_result = next(
            r for r in response.data["results"] if r["game_id"] == 1005
        )
        self.assertEqual(unknown_result["genres"], [])

    # --- 실패 케이스 ---

    def test_get_bookmark_list_unauthenticated_fail(self):
        """비인증 유저가 접근 시 401 반환 확인"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_post_method_not_allowed_fail(self):
        """POST 요청 시 405 반환 확인"""
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url, data={})

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
