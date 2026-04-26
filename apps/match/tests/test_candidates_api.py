from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.match.services.candidates_query import MatchCandidatesDataUnavailable


class MatchCandidatesAPITest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("match-candidates")
        cls.user = get_user_model().objects.create_user(
            login_id="candidates_api_user",
            password="Pass1234!",
            name="테스터",
            nickname="candidates_tester",
            gender="M",
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("apps.match.views.candidates.MatchCandidatesQueryService.get_candidates")
    def test_get_candidates_success_returns_200(self, mock_get_candidates):
        mock_get_candidates.return_value = {
            "genre_id": 2,
            "count": 1,
            "results": [
                {
                    "game_id": 72,
                    "name": "Portal 2",
                    "trailer_url": "https://www.youtube.com/watch?v=mC_u9ZwlIUc",
                    "is_liked": False,
                    "description": "Puzzle action game.",
                    "genres": ["액션", "퍼즐"],
                    "rating": 91.3,
                }
            ],
        }

        response = self.client.get(self.url, {"genre_id": 2, "retry_no": 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["genre_id"], 2)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["game_id"], 72)
        mock_get_candidates.assert_called_once_with(
            user_id=self.user.id,
            genre_id=2,
            retry_no=1,
        )

    @patch("apps.match.views.candidates.MatchCandidatesQueryService.get_candidates")
    def test_get_candidates_default_retry_no_zero(self, mock_get_candidates):
        mock_get_candidates.return_value = {
            "genre_id": 2,
            "count": 1,
            "results": [
                {
                    "game_id": 45181,
                    "name": "Mass Effect Trilogy",
                    "trailer_url": "",
                    "is_liked": False,
                    "description": "Sci-fi RPG trilogy.",
                    "genres": ["RPG"],
                    "rating": 92.5,
                }
            ],
        }

        response = self.client.get(self.url, {"genre_id": 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get_candidates.assert_called_once_with(
            user_id=self.user.id,
            genre_id=2,
            retry_no=0,
        )

    def test_get_candidates_unauthorized_returns_401(self):
        anonymous_client = APIClient()
        response = anonymous_client.get(self.url, {"genre_id": 2})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error_detail", response.data)

    def test_get_candidates_invalid_genre_id_returns_400(self):
        for invalid in [0, 9, "abc"]:
            with self.subTest(genre_id=invalid):
                response = self.client.get(self.url, {"genre_id": invalid})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("genre_id", response.data["error_detail"])

    def test_get_candidates_invalid_retry_no_returns_400(self):
        for invalid in [-1, "abc"]:
            with self.subTest(retry_no=invalid):
                response = self.client.get(
                    self.url,
                    {"genre_id": 2, "retry_no": invalid},
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("retry_no", response.data["error_detail"])

    @patch("apps.match.views.candidates.MatchCandidatesQueryService.get_candidates")
    def test_get_candidates_not_found_returns_404_when_empty(self, mock_get_candidates):
        mock_get_candidates.return_value = {
            "genre_id": 2,
            "count": 0,
            "results": [],
        }

        response = self.client.get(self.url, {"genre_id": 2, "retry_no": 0})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_detail"],
            "해당 장르의 게임을 찾을 수 없습니다.",
        )

    @patch("apps.match.views.candidates.MatchCandidatesQueryService.get_candidates")
    def test_get_candidates_service_unavailable_returns_503(self, mock_get_candidates):
        mock_get_candidates.side_effect = MatchCandidatesDataUnavailable()

        response = self.client.get(self.url, {"genre_id": 2, "retry_no": 0})

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data["error_detail"],
            "외부 게임 데이터 서비스가 일시적으로 불가합니다.",
        )
