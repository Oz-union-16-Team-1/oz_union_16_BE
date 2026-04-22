import json
import time
from unittest.mock import patch

from django.test import SimpleTestCase

import apps.match.services.genre_image_batch as batch_module
from apps.match.constants import (
    MATCH_GENRE_IMAGE_ALLOWED_CATEGORIES,
    MATCH_GENRE_IMAGE_MIN_RATING,
    MATCH_GENRE_IMAGE_MIN_RATING_COUNT,
    MATCH_GENRE_IMAGE_REQUIRED_PLATFORM,
    MATCH_GENRE_IMAGE_REQUIRED_STATUS,
)
from apps.match.services.genre_image_assignment import GenreImageCandidate
from apps.match.services.genre_image_batch import MatchGenreImageBatchService
from apps.match.tests.helpers import FakeRedis


class MatchGenreImageBatchServiceTest(SimpleTestCase):
    def setUp(self):
        self.service = MatchGenreImageBatchService()
        self.service.redis = FakeRedis()
        self.service.cache_key = "match:genre:image_map:v1"

    def _valid_game(self, *, game_id: int, release_ts: int, cover_url: str):
        return {
            "id": game_id,
            "category": MATCH_GENRE_IMAGE_ALLOWED_CATEGORIES[0],
            "status": MATCH_GENRE_IMAGE_REQUIRED_STATUS,
            "platforms": [MATCH_GENRE_IMAGE_REQUIRED_PLATFORM],
            "rating": MATCH_GENRE_IMAGE_MIN_RATING + 20.0,
            "rating_count": MATCH_GENRE_IMAGE_MIN_RATING_COUNT + 100,
            "first_release_date": release_ts,
            "cover": {"url": cover_url},
        }

    @patch.object(batch_module, "API_TO_IGDB_IMAGE_GENRE_MAP", {1: [4]})
    @patch.object(batch_module.igdb_client, "query_games")
    # 필터 조건을 통과한 게임만 후보로 남김
    def test_fetch_candidates_filters_valid_rows(self, mock_query_games):
        release_ts = int(time.time())
        valid = self._valid_game(
            game_id=100,
            release_ts=release_ts,
            cover_url="//images.igdb.com/igdb/image/upload/t_thumb/co1.jpg",
        )
        invalid_low_rating = {
            **valid,
            "id": 101,
            "rating": MATCH_GENRE_IMAGE_MIN_RATING - 1.0,
        }

        mock_query_games.return_value = [valid, invalid_low_rating]
        result = self.service._fetch_candidates_by_genre()

        self.assertIn(1, result)
        self.assertEqual(len(result[1]), 1)
        self.assertEqual(result[1][0].game_id, 100)

    @patch.object(batch_module, "API_TO_IGDB_IMAGE_GENRE_MAP", {1: [4]})
    @patch.object(batch_module.igdb_client, "query_games")
    # 동일 game_id 중복 데이터는 1건으로 정리
    def test_fetch_candidates_deduplicates_same_game_id(self, mock_query_games):
        release_ts = int(time.time())
        valid = self._valid_game(
            game_id=100,
            release_ts=release_ts,
            cover_url="//images.igdb.com/igdb/image/upload/t_thumb/co1.jpg",
        )
        duplicate = {**valid, "rating": MATCH_GENRE_IMAGE_MIN_RATING}

        mock_query_games.return_value = [valid, duplicate]
        result = self.service._fetch_candidates_by_genre()

        self.assertEqual(len(result[1]), 1)
        self.assertEqual(result[1][0].game_id, 100)

    @patch.object(batch_module, "API_TO_IGDB_IMAGE_GENRE_MAP", {1: [4]})
    @patch.object(batch_module.igdb_client, "query_games")
    # cover URL은 https + t_1080p 형태로 정규화한다.
    def test_fetch_candidates_normalizes_cover_url(self, mock_query_games):
        release_ts = int(time.time())
        valid = self._valid_game(
            game_id=100,
            release_ts=release_ts,
            cover_url="//images.igdb.com/igdb/image/upload/t_thumb/co1.jpg",
        )

        mock_query_games.return_value = [valid]
        result = self.service._fetch_candidates_by_genre()

        image_url = result[1][0].image_url
        self.assertIn("https://", image_url)
        self.assertIn("t_1080p", image_url)

    @patch.object(batch_module, "assign_genre_images")
    # 후보 부족 시 월 단위 컷오프 완화를 통해 다음 단계에서 배정에 성공
    def test_run_relaxes_cutoff_until_candidate_matches(self, mock_assign):
        now_ts = 1_700_000_000
        release_ts = now_ts - (40 * 24 * 60 * 60)  # 30일 실패, 60일 통과

        candidate = GenreImageCandidate(
            game_id=200,
            image_url="https://images.igdb.com/igdb/image/upload/t_1080p/co2.jpg",
            rating=81.2,
            rating_count=90,
        )
        self.service._release_ts_by_genre_game = {1: {200: release_ts}}

        def assign_side_effect(*, candidates_by_genre):
            if candidates_by_genre.get(1):
                return {
                    1: {
                        "game_id": 200,
                        "image_url": candidate.image_url,
                        "rating": 81.2,
                        "rating_count": 90,
                    }
                }
            raise RuntimeError("no candidates")

        mock_assign.side_effect = assign_side_effect

        with (
            patch.object(
                self.service,
                "_fetch_candidates_by_genre",
                return_value={1: [candidate]},
            ),
            patch.object(batch_module.time, "time", return_value=now_ts),
        ):
            result = self.service.run()

        self.assertEqual(result["fallback"], "none")
        self.assertEqual(result["cutoff_days"], 60)
        saved = json.loads(self.service.redis.get(self.service.cache_key))
        self.assertIn("1", saved)

    @patch.object(batch_module, "assign_genre_images", side_effect=RuntimeError("fail"))
    # 모든 완화 단계 실패 시 이전 캐시를 fallback으로 재사용
    def test_run_uses_previous_cache_when_all_cutoff_steps_fail(self, _):
        previous_map = {
            "1": {
                "game_id": 999,
                "image_url": "https://images.igdb.com/igdb/image/upload/t_1080p/prev.jpg",
                "rating": 77.0,
                "rating_count": 88,
            }
        }
        self.service.redis.set(self.service.cache_key, json.dumps(previous_map))

        with patch.object(
            self.service, "_fetch_candidates_by_genre", return_value={1: []}
        ):
            result = self.service.run()

        self.assertEqual(result["fallback"], "previous_cache")
        self.assertEqual(result["updated_count"], 1)

        saved = json.loads(self.service.redis.get(self.service.cache_key))
        self.assertEqual(saved, previous_map)
