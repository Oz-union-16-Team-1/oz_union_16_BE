from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.games.models import Game
from apps.match.constants import (
    MATCH_RESULT_POP_BOOST,
    MATCH_RESULT_SCORE_NORMALIZER,
    MATCH_RESULT_SIM_GENRE_WEIGHT,
    MATCH_RESULT_SIM_MOOD_WEIGHT,
    MATCH_RESULT_WEIGHT_DISLIKE_PENALTY,
    MATCH_RESULT_WEIGHT_LIKE_BONUS,
    MATCH_RESULT_WEIGHT_POP,
    MATCH_RESULT_WEIGHT_REC,
    MATCH_RESULT_WEIGHT_SIM,
)
from apps.match.models import MatchGameGenreMap, MatchGamePreference, MatchGameRating
from apps.match.services.responses_result_query import (
    MatchResponsesResultDataUnavailable,
    MatchResponsesResultQueryService,
    MatchResponsesResultValidationError,
    RankedGame,
)
from apps.users.models import UserLikeBookmark, UserPreference


class MatchResponsesResultFixtureMixin:
    @classmethod
    def _vector(cls, seed: int) -> list[float]:
        base = (seed % 7) + 1
        return [(base + i) / 100.0 for i in range(14)]

    @classmethod
    def _create_game(
        cls,
        *,
        game_id: int,
        rating: float,
        genre_ids: list[int],
    ) -> Game:
        game = Game.objects.create(
            game_id=game_id,
            name=f"Game {game_id}",
            slug=f"game-{game_id}",
            summary="summary",
            storyline="",
            category=0,
            status=0,
            first_release_date=datetime(2021, 1, 1, tzinfo=timezone.utc),
            rating=rating,
            rating_count=50,
            aggregated_rating=80.0,
            aggregated_rating_count=5,
            total_rating=rating,
            total_rating_count=50,
            game_modes=[1, 2],
            player_perspectives=[2],
            themes=[1],
            genres=genre_ids,
            videos=[{"video_id": "abc"}],
            game_type=0,
            is_ban=False,
        )

        MatchGamePreference.objects.create(
            game_id=game,
            game_preference_vector=cls._vector(game_id),
        )

        for genre_id in genre_ids:
            MatchGameGenreMap.objects.create(game_id=game, igdb_genre_id=genre_id)

        return game


class MatchResponsesResultServiceTest(MatchResponsesResultFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            login_id="resp_result_svc_user",
            password="Pass1234!",
            name="테스터",
            nickname="resp_result_svc_tester",
            gender="M",
        )

        # genre_id=2 -> igdb [2, 10]
        cls.games = []
        for idx, rating in enumerate([96, 91, 88, 84, 79, 75, 70], start=1):
            game = cls._create_game(game_id=9300 + idx, rating=rating, genre_ids=[2])
            cls.games.append(game)

        cls.liked_game_id = cls.games[0].game_id
        UserLikeBookmark.objects.create(user=cls.user, game_id=cls.liked_game_id)

        pref, _ = UserPreference.objects.get_or_create(user=cls.user)
        pref.match_vector = [0.1] * 14
        pref.save(update_fields=["match_vector"])

    def setUp(self) -> None:
        self.service = MatchResponsesResultQueryService()

    def test_get_results_success_with_cursor(self):
        first = self.service.get_results(
            user_id=self.user.id,
            genre_id=2,
            page_size=3,
        )

        self.assertEqual(first["user_id"], self.user.id)
        self.assertGreater(first["count"], 0)
        self.assertLessEqual(first["count"], 15)
        self.assertLessEqual(len(first["results"]), 3)

        if first["next"]:
            first_ids = [row["game_id"] for row in first["results"]]
            second = self.service.get_results(
                user_id=self.user.id,
                genre_id=2,
                page_size=3,
                cursor=first["next"],
            )
            second_ids = [row["game_id"] for row in second["results"]]
            self.assertEqual(len(set(first_ids).intersection(second_ids)), 0)

    def test_get_results_invalid_cursor_raises_validation_error(self):
        with self.assertRaises(MatchResponsesResultValidationError):
            self.service.get_results(
                user_id=self.user.id,
                genre_id=2,
                page_size=5,
                cursor="not-a-valid-cursor",
            )

    def test_get_results_empty_when_no_genre_candidates(self):
        result = self.service.get_results(
            user_id=self.user.id,
            genre_id=7,
            page_size=5,
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["results"], [])

    def test_get_results_wraps_unexpected_exception_as_data_unavailable(self):
        with patch.object(self.service, "_liked_ids", side_effect=RuntimeError("boom")):
            with self.assertRaises(MatchResponsesResultDataUnavailable):
                self.service.get_results(
                    user_id=self.user.id,
                    genre_id=2,
                    page_size=5,
                )

    def test_internal_tau_merge_paginate_and_caps(self):
        items = [
            RankedGame(
                game_id=i,
                title=f"g{i}",
                slug="",
                genres=[],
                thumbnail_url="",
                rating=80.0,
                is_liked=(i % 2 == 0),
                final_score=0.9,
                pop_score=0.8,
                rec_score=0.7,
            )
            for i in range(1, 21)
        ]

        self.assertEqual(self.service._apply_tau_steps([]), [])
        high = self.service._apply_tau_steps(items)
        self.assertEqual(len(high), 15)

        low = [
            RankedGame(
                game_id=999,
                title="low",
                slug="",
                genres=[],
                thumbnail_url="",
                rating=10.0,
                is_liked=False,
                final_score=0.24,
                pop_score=0.2,
                rec_score=0.1,
            )
        ]
        self.assertEqual(self.service._apply_tau_steps(low), [])

        merged = self.service._merge_unique(items[:2], [items[1], items[2]])
        self.assertEqual(len(merged), 3)
        self.assertEqual(self.service._count_liked(merged), 1)
        self.assertEqual(self.service._liked_cap(15), 4)
        self.assertEqual(self.service._take_by_popularity(items, 0), [])

        page, nxt = self.service._paginate(items=high, cursor=None, page_size=3)
        self.assertEqual(len(page), 3)
        self.assertIsNotNone(nxt)

        low_cursor = self.service._encode_cursor(-1.0, 0)
        page2, nxt2 = self.service._paginate(items=high, cursor=low_cursor, page_size=3)
        self.assertEqual(page2, [])
        self.assertIsNone(nxt2)

    def test_internal_vector_numeric_and_thumbnail_helpers(self):
        self.assertEqual(self.service._normalize_page_size(True), 5)
        self.assertEqual(self.service._normalize_page_size(0), 5)
        self.assertEqual(self.service._normalize_page_size(999), 15)

        self.assertEqual(self.service._allowed_game_ids_by_genre(genre_id=99), set())

        self.assertEqual(self.service._to_vector(None), [])
        self.assertEqual(self.service._to_vector("bad"), [])
        self.assertEqual(self.service._to_vector(123), [])
        self.assertEqual(self.service._to_vector([1, "x"]), [])
        self.assertEqual(len(self.service._to_vector([1, 2, 3])), 3)

        self.assertEqual(self.service._cosine_similarity([], []), 0.0)
        self.assertEqual(self.service._cosine_similarity([1.0], [1.0, 2.0]), 0.0)
        self.assertEqual(self.service._cosine_similarity([0.0, 0.0], [1.0, 2.0]), 0.0)

        self.assertEqual(self.service._safe_float(None, default=1.2), 1.2)
        self.assertEqual(self.service._safe_float(object(), default=1.2), 1.2)
        self.assertEqual(self.service._safe_float("3.5", default=0.0), 3.5)

        self.assertEqual(self.service._to_pop_score(None), 0.5)
        self.assertEqual(self.service._to_pop_score(-10), 0.5)
        self.assertEqual(self.service._to_pop_score(250), 1.0)

        self.assertEqual(self.service._to_rec_score("bad"), 0.0)
        self.assertEqual(
            self.service._to_rec_score(datetime(1960, 1, 1, tzinfo=timezone.utc)),
            0.0,
        )
        self.assertGreaterEqual(self.service._to_rec_score(datetime.now()), 0.0)

        self.assertEqual(self.service._normalize_rating(None), 0.0)
        self.assertEqual(self.service._normalize_rating(120), 100.0)

        self.assertEqual(self.service._to_thumbnail_url(""), "")
        self.assertIn(
            "https:",
            self.service._to_thumbnail_url(
                "//images.igdb.com/igdb/image/upload/t_thumb/abc.jpg"
            ),
        )
        self.assertIn(
            "t_1080p",
            self.service._to_thumbnail_url(
                "https://images.igdb.com/igdb/image/upload/t_thumb/abc.jpg"
            ),
        )
        self.assertIn("abc123.jpg", self.service._to_thumbnail_url("abc123"))

        c = self.service._encode_cursor(0.7777777, 123)
        s, g, o = self.service._decode_cursor(c)
        self.assertEqual(g, 123)
        self.assertAlmostEqual(s, 0.777778, places=6)
        self.assertIsNone(o)

    def test_internal_fallback_and_mean_vector_helpers(self):
        self.assertEqual(
            self.service._fallback_popular(
                source_ids=None,
                excluded_ids=set(),
                limit=0,
                liked_ids=set(),
            ),
            [],
        )
        self.assertEqual(
            self.service._fallback_popular(
                source_ids=set(),
                excluded_ids=set(),
                limit=3,
                liked_ids=set(),
            ),
            [],
        )

        self.assertEqual(self.service._genres_by_game(set()), {})
        self.assertIsNone(self.service._mean_vector_for_game_ids([]))
        self.assertIsNone(self.service._mean_vector_for_game_ids([99999999]))

        liked_mean = self.service._load_liked_mean_vector(user_id=self.user.id)
        self.assertIsNotNone(liked_mean)
        self.assertEqual(len(liked_mean), 14)

        self.assertIsNone(self.service._load_disliked_mean_vector(user_id=self.user.id))
        MatchGameRating.objects.create(
            user=self.user,
            game=self.games[1],
            star_rating=1,
            effective_rating="1.00",
            rating_count=1,
        )
        disliked_mean = self.service._load_disliked_mean_vector(user_id=self.user.id)
        self.assertIsNotNone(disliked_mean)
        self.assertEqual(len(disliked_mean), 14)

    def test_internal_series_dedupe_keeps_highest_ranked_variant(self):
        service = MatchResponsesResultQueryService()

        items = [
            RankedGame(
                game_id=1001,
                title="Way of the Hunter",
                slug="way-of-the-hunter",
                genres=["시뮬레이션"],
                thumbnail_url="",
                rating=80.0,
                is_liked=False,
                final_score=0.95,
                pop_score=0.8,
                rec_score=0.7,
            ),
            RankedGame(
                game_id=1002,
                title="Way of the Hunter Deluxe Edition",
                slug="way-of-the-hunter-deluxe-edition",
                genres=["시뮬레이션"],
                thumbnail_url="",
                rating=81.0,
                is_liked=False,
                final_score=0.94,
                pop_score=0.8,
                rec_score=0.7,
            ),
            RankedGame(
                game_id=1003,
                title="Way of the Hunter Complete",
                slug="way-of-the-hunter-complete",
                genres=["시뮬레이션"],
                thumbnail_url="",
                rating=82.0,
                is_liked=False,
                final_score=0.93,
                pop_score=0.8,
                rec_score=0.7,
            ),
            RankedGame(
                game_id=2001,
                title="Portal 2",
                slug="portal-2",
                genres=["퍼즐"],
                thumbnail_url="",
                rating=90.0,
                is_liked=False,
                final_score=0.90,
                pop_score=0.9,
                rec_score=0.6,
            ),
        ]

        deduped = service._dedupe_series_variants(items, limit=15)
        deduped_ids = [x.game_id for x in deduped]

        # same series는 상위 1개만 남아야 함
        self.assertIn(1001, deduped_ids)
        self.assertNotIn(1002, deduped_ids)
        self.assertNotIn(1003, deduped_ids)
        self.assertIn(2001, deduped_ids)

    def test_result_similarity_excludes_dim14_popularity_axis(self):
        # 같은 1~13차원, dim14만 다른 벡터
        user_vec = [0.2] * 13 + [0.0]
        game_vec = [0.2] * 13 + [1.0]

        # 전체 14차원 코사인은 dim14 차이 영향이 있음
        full_sim = self.service._cosine_similarity(user_vec, game_vec)
        self.assertLess(full_sim, 1.0)

        # result sim 벡터(1~13차원)로 자르면 dim14 영향이 사라져야 함
        user_sim_vec = self.service._result_sim_vector(user_vec)
        game_sim_vec = self.service._result_sim_vector(game_vec)

        self.assertEqual(len(user_sim_vec), 13)
        self.assertEqual(len(game_sim_vec), 13)

        split_sim = self.service._cosine_similarity(user_sim_vec, game_sim_vec)
        self.assertAlmostEqual(split_sim, 1.0, places=6)

    def test_result_split_similarity_applies_genre_mood_weights(self):
        # genre_sim=1.0, mood_sim=-1.0 이 되도록 구성
        a = [1.0] * 8 + [1.0] * 5
        b = [1.0] * 8 + [-1.0] * 5

        sim = self.service._result_split_similarity(a, b)

        expected = (
            (1.0 * MATCH_RESULT_SIM_GENRE_WEIGHT)
            + (-1.0 * MATCH_RESULT_SIM_MOOD_WEIGHT)
        ) / (MATCH_RESULT_SIM_GENRE_WEIGHT + MATCH_RESULT_SIM_MOOD_WEIGHT)

        self.assertAlmostEqual(sim, expected, places=6)

    def test_result_split_similarity_can_change_ranking(self):
        # user: 장르/분위기 모두 높은 선호
        user_vec = [0.8] * 8 + [0.9] * 5

        # A: 장르축이 상대적으로 유리, 분위기축 일부 약함
        cand_a = [
            0.9888577985863465,
            0.394227938329771,
            0.6310651114170431,
            0.5632984196964456,
            0.9080130881770461,
            0.9074032673590061,
            0.8409676478246163,
            0.6225467217716928,
            0.6422815588981324,
            0.21218425489136972,
            0.10128960738923942,
            0.8527728370158154,
            0.5005894505851264,
        ]

        # B: 장르 일부 약하지만 분위기/성향축이 더 맞음
        cand_b = [
            0.06854450205579687,
            0.2883592827942677,
            0.9305031449685998,
            0.7381716557116453,
            0.3289245241923653,
            0.8732205961998928,
            0.12128305283711271,
            0.8071425851507292,
            0.404598428838434,
            0.9408717058741171,
            0.5018505343199596,
            0.7755175526898117,
            0.47798429169201584,
        ]

        # 비가중 코사인(기준 비교)
        unweighted_a = self.service._cosine_similarity(user_vec, cand_a)
        unweighted_b = self.service._cosine_similarity(user_vec, cand_b)
        self.assertGreater(unweighted_a, unweighted_b)

        # 분리식 sim(목표 정책)
        split_a = self.service._result_split_similarity(user_vec, cand_a)
        split_b = self.service._result_split_similarity(user_vec, cand_b)
        self.assertGreater(split_b, split_a)

    def test_compose_final_score_applies_pop_boost_110(self):
        sim = 0.5
        pop = 0.9
        rec = 0.5
        like_bonus = 0.2
        dislike_penalty = 0.1

        score = self.service._compose_final_score(
            sim=sim,
            pop=pop,
            rec=rec,
            like_bonus=like_bonus,
            dislike_penalty=dislike_penalty,
        )

        expected_raw = (
            (sim * MATCH_RESULT_WEIGHT_SIM)
            + (pop * MATCH_RESULT_WEIGHT_POP * MATCH_RESULT_POP_BOOST)
            + (rec * MATCH_RESULT_WEIGHT_REC)
            + (like_bonus * MATCH_RESULT_WEIGHT_LIKE_BONUS)
            - (dislike_penalty * MATCH_RESULT_WEIGHT_DISLIKE_PENALTY)
        )
        expected = round(max(0.0, expected_raw) / MATCH_RESULT_SCORE_NORMALIZER, 6)

        self.assertEqual(score, expected)

    def test_internal_series_dedupe_keeps_highest_ranked_variant(self):
        service = MatchResponsesResultQueryService()

        items = [
            RankedGame(
                game_id=1001,
                title="Way of the Hunter",
                slug="way-of-the-hunter",
                genres=["시뮬레이션"],
                thumbnail_url="",
                rating=80.0,
                is_liked=False,
                final_score=0.95,
                pop_score=0.8,
                rec_score=0.7,
                parent_game_id=9000,
            ),
            RankedGame(
                game_id=1002,
                title="Way of the Hunter: Night Hunting Pack",
                slug="way-of-the-hunter-night-hunting-pack",
                genres=["시뮬레이션"],
                thumbnail_url="",
                rating=81.0,
                is_liked=False,
                final_score=0.94,
                pop_score=0.8,
                rec_score=0.7,
                parent_game_id=9000,
            ),
            RankedGame(
                game_id=1003,
                title="Way of the Hunter: Map Pack 2",
                slug="way-of-the-hunter-map-pack-2",
                genres=["시뮬레이션"],
                thumbnail_url="",
                rating=82.0,
                is_liked=False,
                final_score=0.93,
                pop_score=0.8,
                rec_score=0.7,
                parent_game_id=9000,
            ),
            RankedGame(
                game_id=2001,
                title="Portal 2",
                slug="portal-2",
                genres=["퍼즐"],
                thumbnail_url="",
                rating=90.0,
                is_liked=False,
                final_score=0.90,
                pop_score=0.9,
                rec_score=0.6,
            ),
        ]

        deduped = service._dedupe_series_variants(items, limit=15)
        deduped_ids = [x.game_id for x in deduped]

        self.assertIn(1001, deduped_ids)
        self.assertNotIn(1002, deduped_ids)
        self.assertNotIn(1003, deduped_ids)
        self.assertIn(2001, deduped_ids)


    def test_internal_series_dedupe_does_not_merge_similar_titles_of_different_series(self):
        service = MatchResponsesResultQueryService()

        items = [
            RankedGame(
                game_id=3001,
                title="Resident Evil 4",
                slug="resident-evil-4",
                genres=["액션"],
                thumbnail_url="",
                rating=89.0,
                is_liked=False,
                final_score=0.91,
                pop_score=0.8,
                rec_score=0.7,
                parent_game_id=9101,
            ),
            RankedGame(
                game_id=3002,
                title="Resident Evil 4 VR",
                slug="resident-evil-4-vr",
                genres=["액션"],
                thumbnail_url="",
                rating=88.0,
                is_liked=False,
                final_score=0.90,
                pop_score=0.8,
                rec_score=0.7,
                parent_game_id=9102,
            ),
        ]

        deduped = service._dedupe_series_variants(items, limit=15)
        deduped_ids = [x.game_id for x in deduped]

        self.assertIn(3001, deduped_ids)
        self.assertIn(3002, deduped_ids)
        self.assertEqual(len(deduped_ids), 2)


    def test_get_results_keeps_15_after_dedupe_fill_and_preserves_final_sort(self):
        def _mk(game_id: int, score: float, parent: int | None = None) -> RankedGame:
            return RankedGame(
                game_id=game_id,
                title=f"Game {game_id}",
                slug=f"game-{game_id}",
                genres=["어드벤처"],
                thumbnail_url="",
                rating=80.0,
                is_liked=False,
                final_score=score,
                pop_score=0.8,
                rec_score=0.7,
                parent_game_id=parent,
            )

        # 상위권에 같은 시리즈(parent=5000) 다수 배치 -> dedupe 후 개수 감소 유도
        ranked_pool = []
        for i in range(1, 7):
            ranked_pool.append(_mk(1000 + i, 0.99 - (i * 0.001), parent=5000))
        for i in range(7, 25):
            ranked_pool.append(_mk(1000 + i, 0.95 - ((i - 7) * 0.01), parent=None))

        allowed_ids = {item.game_id for item in ranked_pool}

        with patch.object(self.service, "_liked_ids", return_value=set()), \
                patch.object(self.service, "_allowed_game_ids_by_genre", return_value=allowed_ids), \
                patch.object(self.service, "_load_user_vector", return_value=[0.1] * 14), \
                patch.object(self.service, "_load_liked_mean_vector", return_value=None), \
                patch.object(self.service, "_load_disliked_mean_vector", return_value=None), \
                patch.object(self.service, "_score_personalized_once", return_value=ranked_pool), \
                patch.object(self.service, "_fallback_popular", return_value=[]), \
                patch.object(self.service, "_paginate", wraps=self.service._paginate) as paginate_spy:

            result = self.service.get_results(
                user_id=self.user.id,
                genre_id=2,
                page_size=15,
            )

        self.assertEqual(result["count"], 15)
        self.assertEqual(len(result["results"]), 15)

        final_ranked = paginate_spy.call_args.kwargs["items"]
        self.assertEqual(len(final_ranked), 15)

        keys = [self.service._canonical_game_key(item) for item in final_ranked]
        self.assertEqual(len(keys), len(set(keys)))  # dedupe key 중복 제거 유지

        expected = sorted(
            final_ranked,
            key=lambda item: (item.final_score, item.game_id),
            reverse=True,
        )
        self.assertEqual(
            [item.game_id for item in final_ranked],
            [item.game_id for item in expected],
        )

    def test_internal_series_dedupe_strips_edition_suffix_without_parent_collection(self):
        service = MatchResponsesResultQueryService()

        items = [
            RankedGame(
                game_id=3101,
                title="Marvel's Guardians of the Galaxy",
                slug="marvel-guardians-galaxy",
                genres=["액션"],
                thumbnail_url="",
                rating=90.0,
                is_liked=False,
                final_score=0.95,
                pop_score=0.9,
                rec_score=0.7,
            ),
            RankedGame(
                game_id=3102,
                title="Marvel's Guardians of the Galaxy: Digital Deluxe Edition",
                slug="marvel-guardians-galaxy-digital-deluxe-edition",
                genres=["액션"],
                thumbnail_url="",
                rating=88.0,
                is_liked=False,
                final_score=0.94,
                pop_score=0.8,
                rec_score=0.7,
            ),
            RankedGame(
                game_id=3103,
                title="Marvel's Guardians of the Galaxy: Cosmic Deluxe Edition",
                slug="marvel-guardians-galaxy-cosmic-deluxe-edition",
                genres=["액션"],
                thumbnail_url="",
                rating=87.0,
                is_liked=False,
                final_score=0.93,
                pop_score=0.8,
                rec_score=0.7,
            ),
            RankedGame(
                game_id=3201,
                title="Portal 2",
                slug="portal-2",
                genres=["퍼즐"],
                thumbnail_url="",
                rating=92.0,
                is_liked=False,
                final_score=0.90,
                pop_score=0.9,
                rec_score=0.6,
            ),
        ]

        deduped = service._dedupe_series_variants(items, limit=15)
        deduped_ids = [x.game_id for x in deduped]

        self.assertIn(3101, deduped_ids)
        self.assertNotIn(3102, deduped_ids)
        self.assertNotIn(3103, deduped_ids)
        self.assertIn(3201, deduped_ids)


class MatchResponsesResultAPITest(MatchResponsesResultFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("match-responses-result")
        cls.user = get_user_model().objects.create_user(
            login_id="resp_result_api_user",
            password="Pass1234!",
            name="테스터",
            nickname="resp_result_api_tester",
            gender="M",
        )

        for idx, rating in enumerate([95, 89, 83, 77, 71], start=1):
            cls._create_game(game_id=9400 + idx, rating=rating, genre_ids=[2])

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_responses_result_success_returns_200(self):
        response = self.client.get(self.url, {"genre_id": 2, "page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user_id", response.data)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("results", response.data)

    def test_get_responses_result_invalid_genre_returns_400(self):
        response = self.client.get(self.url, {"genre_id": 99, "page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("genre_id", response.data["error_detail"])

    def test_get_responses_result_invalid_cursor_returns_400(self):
        response = self.client.get(
            self.url,
            {"genre_id": 2, "cursor": "bad-cursor", "page_size": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cursor", str(response.data["error_detail"]))

    def test_get_responses_result_unauthorized_returns_401(self):
        anonymous_client = APIClient()
        response = anonymous_client.get(self.url, {"genre_id": 2})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error_detail", response.data)

    def test_get_responses_result_not_found_returns_404(self):
        response = self.client.get(self.url, {"genre_id": 7, "page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_detail"], "매칭 추천 결과를 찾을 수 없습니다."
        )

    @patch(
        "apps.match.views.rating_responses_result.MatchResponsesResultQueryService.get_results"
    )
    def test_get_responses_result_service_unavailable_returns_503(
        self, mock_get_results
    ):
        mock_get_results.side_effect = MatchResponsesResultDataUnavailable()

        response = self.client.get(self.url, {"genre_id": 2, "page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data["error_detail"],
            "추천 데이터 조회 중 외부 서비스 오류가 발생했습니다.",
        )

    def test_get_responses_result_cursor_stable_after_like_toggle(self):
        # 페이지가 최소 2장 나오도록 데이터 보강
        for idx, rating in enumerate([69, 67, 65, 63, 61, 59, 57, 55], start=1):
            self._create_game(game_id=9600 + idx, rating=rating, genre_ids=[2])

        # 1페이지 조회
        first = self.client.get(self.url, {"genre_id": 2, "page_size": 3})
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertGreater(len(first.data["results"]), 0)
        self.assertIsNotNone(first.data["next"])

        # 페이지1에서 본 게임 하나를 "좋아요 토글" (상태 변화 유도)
        target_game_id = first.data["results"][0]["game_id"]
        bookmark = UserLikeBookmark.objects.filter(
            user_id=self.user.id,
            game_id=target_game_id,
        )
        if bookmark.exists():
            bookmark.delete()
        else:
            UserLikeBookmark.objects.create(
                user_id=self.user.id, game_id=target_game_id
            )

        # 기존 next cursor로 2페이지 조회 (회귀 포인트)
        second = self.client.get(
            self.url,
            {"genre_id": 2, "page_size": 3, "cursor": first.data["next"]},
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertIn("results", second.data)
        self.assertGreater(len(second.data["results"]), 0)
