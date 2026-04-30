from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.games.models import Game
from apps.match.models import MatchGenreImagePublished
from apps.match.services.genre_image_assets import (
    build_artwork_options,
    build_cover_option,
    build_screenshot_options,
    fetch_artwork_options_map,
    image_id_to_url,
    merge_unique_image_options,
    normalize_image_url,
)
from apps.match.services.genre_image_candidates import GenreImageCandidatesService
from apps.match.services.genre_image_publish import MatchGenreImagePublishService


class GenreImageAssetsUnitTest(SimpleTestCase):
    def test_normalize_and_build_helpers(self):
        self.assertIsNone(normalize_image_url(None))
        self.assertIsNone(normalize_image_url("   "))

        self.assertEqual(
            normalize_image_url("//images.igdb.com/igdb/image/upload/t_thumb/abc.jpg"),
            "https://images.igdb.com/igdb/image/upload/t_1080p/abc.jpg",
        )
        self.assertEqual(
            normalize_image_url("co123"),
            "https://images.igdb.com/igdb/image/upload/t_1080p/co123.jpg",
        )
        self.assertEqual(
            image_id_to_url("sc456"),
            "https://images.igdb.com/igdb/image/upload/t_1080p/sc456.jpg",
        )

        cover = build_cover_option("co999")
        self.assertEqual(len(cover), 1)
        self.assertEqual(cover[0]["label"], "대표 커버")

    def test_build_screenshot_and_artwork_options(self):
        screenshots = build_screenshot_options(
            [
                {"image_id": "sc1"},
                {"url": "//images.igdb.com/igdb/image/upload/t_thumb/sc2.jpg"},
                "sc1",  # 중복
            ]
        )
        self.assertEqual(len(screenshots), 2)
        self.assertEqual(screenshots[0]["label"], "스크린샷 #1")
        self.assertEqual(screenshots[1]["label"], "스크린샷 #2")

        artworks = build_artwork_options(
            [
                {"image_id": "aw1"},
                {"url": "//images.igdb.com/igdb/image/upload/t_thumb/aw2.jpg"},
                "aw1",  # 중복
            ]
        )
        self.assertEqual(len(artworks), 2)
        self.assertEqual(artworks[0]["label"], "아트워크 #1")
        self.assertEqual(artworks[1]["label"], "아트워크 #2")

    def test_merge_unique_image_options(self):
        merged = merge_unique_image_options(
            [
                {"url": "co1", "source": "cover", "label": "대표 커버"},
                {"url": "co1", "source": "cover", "label": "대표 커버"},
                {"url": "co2", "source": "cover", "label": "대표 커버"},
            ]
        )
        self.assertEqual(len(merged), 2)

    @patch("apps.match.services.genre_image_assets.igdb_client.query_games_raw")
    def test_fetch_artwork_options_map(self, mock_query):
        mock_query.side_effect = [
            [
                {"id": 1, "artworks": [{"image_id": "aw1"}, {"image_id": "aw2"}]},
                {"id": "bad", "artworks": [{"image_id": "x"}]},
                {"id": 0, "artworks": [{"image_id": "y"}]},
            ],
            Exception("igdb error"),
        ]

        out = fetch_artwork_options_map([1, 1, 2, 3], chunk_size=2)

        self.assertIn(1, out)
        self.assertEqual(len(out[1]), 2)
        self.assertNotIn(2, out)
        self.assertNotIn(3, out)


class GenreImageCandidatesUnitTest(TestCase):
    @staticmethod
    def _candidate(game_id: int, release_ts: int) -> dict:
        return {
            "game_id": game_id,
            "name": f"game-{game_id}",
            "rating": 88.8,
            "rating_count": 120,
            "release_ts": release_ts,
            "images": [
                {
                    "url": f"https://images.igdb.com/igdb/image/upload/t_1080p/{game_id}.jpg",
                    "source": "cover",
                    "label": "대표 커버",
                }
            ],
        }

    @classmethod
    def setUpTestData(cls) -> None:
        now = timezone.now()

        # 통과 케이스 (api_genre_id=1 -> igdb genre includes 4)
        Game.objects.create(
            game_id=8101,
            name="pass-game",
            slug="pass-game",
            genres=[4],
            category=0,
            status=0,
            first_release_date=now - timedelta(days=30),
            total_rating=90.0,
            total_rating_count=100,
            cover="co8101",
            screenshots=[{"image_id": "sc8101"}],
        )

        # 이미지 없음 -> 최종 후보 제외
        Game.objects.create(
            game_id=8102,
            name="no-image-game",
            slug="no-image-game",
            genres=[4],
            category=0,
            status=0,
            first_release_date=now - timedelta(days=30),
            total_rating=92.0,
            total_rating_count=100,
            cover=None,
            screenshots=[],
        )

        # 점수 미달 -> 필터에서 제외
        Game.objects.create(
            game_id=8103,
            name="low-rating-game",
            slug="low-rating-game",
            genres=[4],
            category=0,
            status=0,
            first_release_date=now - timedelta(days=30),
            total_rating=60.0,
            total_rating_count=100,
            cover="co8103",
            screenshots=[{"image_id": "sc8103"}],
        )

    def test_fetch_ranked_candidates_for_genre(self):
        service = GenreImageCandidatesService(scan_limit=2000)
        out = service._fetch_ranked_candidates_for_genre(
            api_genre_id=1, scan_limit=2000
        )

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["game_id"], 8101)
        self.assertGreaterEqual(len(out[0]["images"]), 2)  # cover + screenshot

    def test_assign_with_priority_and_internal_backfill(self):
        service = GenreImageCandidatesService()
        ranked = {
            gid: [
                self._candidate(10, 1_700_000_000),
                self._candidate(1000 + gid, 1_700_000_000),
            ]
            for gid in range(1, 9)
        }

        # limit=2에서 1차(중복제거) + 2차(장르내 보충) 모두 타도록 구성
        selected = service._assign_with_priority(
            ranked_by_genre=ranked, limit_per_genre=2
        )

        for gid in range(1, 9):
            self.assertEqual(len(selected[gid]), 2)

    def test_build_candidates_by_genre_main_flow(self):
        service = GenreImageCandidatesService(scan_limit=10)
        now_ts = int(timezone.now().timestamp())

        def fake_fetch(*, api_genre_id: int, scan_limit: int = 10):
            return [
                self._candidate(api_genre_id * 1000 + i, now_ts) for i in range(1, 6)
            ]

        with (
            patch.object(
                service,
                "_fetch_ranked_candidates_for_genre",
                side_effect=fake_fetch,
            ),
            patch.object(service, "_attach_artworks") as mock_attach,
        ):
            out = service.build_candidates_by_genre(limit_per_genre=5)

        self.assertEqual(len(out), 8)
        for gid in range(1, 9):
            self.assertEqual(len(out[gid]), 5)
        mock_attach.assert_called_once()

    @patch("apps.match.services.genre_image_candidates.fetch_artwork_options_map")
    def test_attach_artworks_merges(self, mock_fetch_artworks):
        service = GenreImageCandidatesService()
        selected = {gid: [] for gid in range(1, 9)}
        selected[1] = [
            self._candidate(9001, 1_700_000_000),
        ]
        mock_fetch_artworks.return_value = {
            9001: [
                {
                    "url": "aw9001",
                    "source": "artwork",
                    "label": "아트워크 #1",
                }
            ]
        }

        service._attach_artworks(selected)

        labels = [img["label"] for img in selected[1][0]["images"]]
        self.assertIn("아트워크 #1", labels)


class GenreImagePublishUnitTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            login_id="genre_publish_unit_user",
            password="Pass1234!",
            name="테스터",
            nickname="pub_unit",
            gender="M",
        )
        cls.game1 = Game.objects.create(game_id=7001, name="g1", slug="g1")
        cls.game2 = Game.objects.create(game_id=7002, name="g2", slug="g2")

    def test_seed_or_refresh_missing_and_success_mix(self):
        service = MatchGenreImagePublishService()

        candidates = {
            1: [],  # missing
            2: [{"game_id": 7001, "images": []}],  # 이미지 없음
            3: [  # 정상
                {
                    "game_id": 7002,
                    "images": [
                        {
                            "url": "https://images.igdb.com/igdb/image/upload/t_1080p/co7002.jpg"
                        }
                    ],
                }
            ],
        }

        with patch.object(service, "build_candidates", return_value=candidates):
            updated, missing = service.seed_or_refresh(
                user=self.user, limit_per_genre=5
            )

        self.assertEqual(updated, 1)
        self.assertEqual(missing, 7)

    def test_pick_candidate_image_failure_and_success_paths(self):
        obj = MatchGenreImagePublished.objects.create(
            api_genre_id=1,
            game=self.game1,
            image_url="https://images.igdb.com/igdb/image/upload/t_1080p/old.jpg",
            selected_by=self.user,
        )
        service = MatchGenreImagePublishService()

        # 1) 후보 없음
        with patch.object(service, "build_candidates", return_value={1: []}):
            ok, msg = service.pick_candidate_image(
                obj=obj,
                game_id=9999,
                image_index=0,
                user=self.user,
                limit_per_genre=5,
            )
        self.assertFalse(ok)
        self.assertIn("후보 5개", msg)

        # 2) 이미지 없음
        with patch.object(
            service,
            "build_candidates",
            return_value={1: [{"game_id": 7002, "images": []}]},
        ):
            ok, msg = service.pick_candidate_image(
                obj=obj,
                game_id=7002,
                image_index=0,
                user=self.user,
                limit_per_genre=5,
            )
        self.assertFalse(ok)
        self.assertIn("선택 가능한 이미지", msg)

        # 3) image_index 범위 밖 -> 0으로 보정 후 성공
        with patch.object(
            service,
            "build_candidates",
            return_value={
                1: [
                    {
                        "game_id": 7002,
                        "images": [
                            {
                                "url": "https://images.igdb.com/igdb/image/upload/t_1080p/new1.jpg"
                            },
                            {
                                "url": "https://images.igdb.com/igdb/image/upload/t_1080p/new2.jpg"
                            },
                        ],
                    }
                ]
            },
        ):
            ok, msg = service.pick_candidate_image(
                obj=obj,
                game_id=7002,
                image_index=99,
                user=self.user,
                limit_per_genre=5,
            )

        obj.refresh_from_db()
        self.assertTrue(ok)
        self.assertEqual(obj.game_id, 7002)
        self.assertEqual(
            obj.image_url,
            "https://images.igdb.com/igdb/image/upload/t_1080p/new1.jpg",
        )
        self.assertIn("반영", msg)

    def test_model_str(self):
        obj = MatchGenreImagePublished.objects.create(
            api_genre_id=8,
            game=self.game1,
            image_url="https://images.igdb.com/igdb/image/upload/t_1080p/x.jpg",
            selected_by=self.user,
        )
        self.assertIn("8 |", str(obj))
