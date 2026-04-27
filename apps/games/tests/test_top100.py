from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Game
from apps.games.service.game_list_top100_services import GameTop100Service


class GameTop100APITest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # 1. Serializer Missing 해결용 데이터
        # 95.56으로 설정하여 반올림 이슈(95.5 vs 95.6) 해결
        # genres에 999를 넣어 Missing 59(매핑 없는 장르) 해결
        # cover에 //를 넣어 Missing 76-77(// 시작 경로) 해결
        cls.game_main = Game.objects.create(
            game_id=1,
            name="Main Game",
            total_rating=95.56,
            total_rating_count=100,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[12, 999],
            cover="//images.igdb.com/test.jpg",
        )

        # 2. Service 100개 제한(break) 로직 확인용 대량 데이터
        bulk_games = []
        for i in range(2, 105):
            bulk_games.append(
                Game(
                    game_id=i,
                    name=f"Game {i}",
                    total_rating=80.0,
                    total_rating_count=60,
                    first_release_date=timezone.now() - timezone.timedelta(days=2),
                    genres=[12],
                )
            )
        Game.objects.bulk_create(bulk_games)

        cls.url = reverse("game_list_top100")

    def test_get_top100_success_and_logic_coverage(self):
        """정상 조회 및 시리얼라이저 분기(반올림, // 이미지, 장르 매핑) 검증"""
        response = self.client.get(self.url, {"genre_id": 0})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Service: 100개 제한 확인
        self.assertEqual(len(response.data), 100)

        # Serializer: // 경로 처리 확인 (Missing 76-77)
        self.assertEqual(response.data[0]["cover"], "https://images.igdb.com/test.jpg")

        # Serializer: 평점 반올림 확인 (95.56 -> 95.6)
        self.assertEqual(float(response.data[0]["total_rating"]), 95.6)

    def test_view_missing_and_invalid_param(self):
        """View Missing 39, 48-50 해결: 파라미터 누락 및 잘못된 값"""
        # 파라미터 누락 (Missing 39)
        self.assertEqual(self.client.get(self.url).status_code, 400)

        # 잘못된 값 (ValueError 분기 - Missing 48-50)
        self.assertEqual(
            self.client.get(self.url, {"genre_id": "abc"}).status_code, 400
        )
        self.assertEqual(self.client.get(self.url, {"genre_id": 99}).status_code, 400)

    def test_service_empty_mapping_coverage(self):
        """Service Missing 45-48 해결: 매핑 테이블에 없는 ID 직접 테스트"""
        # View 필터링을 우회하기 위해 서비스 직접 호출
        result = GameTop100Service.get_top_100_games(genre_id=99)
        self.assertEqual(result, [])

    def test_view_500_error_coverage(self):
        """View의 Exception 블록(500 에러) 커버"""
        with patch(
            "apps.games.service.game_list_top100_services.GameTop100Service.get_top_100_games"
        ) as mocked:
            mocked.side_effect = Exception("Internal Error")
            response = self.client.get(self.url, {"genre_id": 0})
            self.assertEqual(response.status_code, 500)
