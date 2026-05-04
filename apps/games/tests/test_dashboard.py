from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Game
from apps.match.models import MatchGameGenreMap, MatchGamePreference, MatchGameRating
from apps.users.models import User, UserLikeBookmark


class GameDashboardAPITest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            login_id="admin",
            password="password",
            name="Admin",
            nickname="admin",
            gender="M",
            is_staff=True,
        )
        cls.user = User.objects.create_user(
            login_id="user",
            password="password",
            name="User",
            nickname="user",
            gender="M",
        )
        cls.other_user = User.objects.create_user(
            login_id="other",
            password="password",
            name="Other",
            nickname="other",
            gender="W",
        )
        cls.game = Game.objects.create(
            game_id=901,
            name="Dashboard Game",
            slug="dashboard-game",
            genres=[12, {"id": 5}, 999],
            cover="cover-id",
            summary="summary",
            like_count=3,
            rating=80,
            total_rating=82,
            total_rating_count=120,
            is_ban=True,
            ban_reason="테스트 차단",
        )
        cls.rating_5 = MatchGameRating.objects.create(
            user=cls.user,
            game=cls.game,
            star_rating=5,
            effective_rating=Decimal("4.80"),
            rating_count=1,
        )
        cls.rating_1 = MatchGameRating.objects.create(
            user=cls.other_user,
            game=cls.game,
            star_rating=1,
            effective_rating=Decimal("1.30"),
            rating_count=1,
        )
        old_date = timezone.now() - timezone.timedelta(days=10)
        MatchGameRating.objects.filter(pk=cls.rating_1.pk).update(created_at=old_date)

        UserLikeBookmark.objects.create(user=cls.user, game=cls.game)
        MatchGamePreference.objects.create(
            game_id=cls.game,
            game_preference_vector=[
                1.0,
                0.0,
                0.8,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.2,
                -0.1,
                0.4,
                0.6,
                -0.2,
                0.8,
            ],
        )
        MatchGameGenreMap.objects.create(game_id=cls.game, igdb_genre_id=3)
        cls.url = reverse("game_dashboard", kwargs={"game_id": cls.game.game_id})

    def test_admin_can_get_game_dashboard(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["basic_info"]["game_id"], 901)
        self.assertEqual(response.data["basic_info"]["game_name"], "Dashboard Game")
        self.assertEqual(response.data["basic_info"]["genres"], ["RPG", "전략"])
        self.assertEqual(response.data["basic_info"]["total_like_count"], 3)
        self.assertEqual(response.data["basic_info"]["total_rating_count"], 2)
        self.assertEqual(response.data["basic_info"]["average_star_rating"], 3.0)

        self.assertEqual(
            response.data["user_reaction_analysis"]["star_distribution"]["1"],
            1,
        )
        self.assertEqual(
            response.data["user_reaction_analysis"]["star_distribution"]["5"],
            1,
        )
        self.assertTrue(response.data["preference_vector"]["exists"])
        self.assertEqual(len(response.data["preference_vector"]["axes"]), 14)
        self.assertEqual(response.data["blacklist_impact"]["ban_reason"], "테스트 차단")
        self.assertEqual(
            response.data["data_health"],
            {
                "has_preference_vector": True,
                "has_genre_mapping": True,
                "has_image": True,
                "has_metadata": True,
            },
        )

    def test_non_admin_cannot_get_game_dashboard(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_returns_404_for_missing_game(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(
            reverse("game_dashboard", kwargs={"game_id": 999999})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
