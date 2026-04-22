from django.test import SimpleTestCase

from apps.match.services import ingest_filters as f
from apps.match.constants import MATCH_INGEST_MIN_RELEASE_TS

def _valid_game() -> dict:
    return {
        "id": 1,
        "name": "ok",
        "category": 0,
        "status": 0,
        "rating": 75.0,
        "rating_count": 100,
        "aggregated_rating": 80.0,
        "first_release_date": 1700000000,
        "genres": [12],
        "videos": [1],
        "summary": "desc",
        "storyline": "",
        "platforms": [6],
    }


class IngestFiltersTest(SimpleTestCase):
    # [정상] 필터 조건을 모두 만족하면 통과해야 한다.
    def test_validate_game_pass(self):
        self.assertIsNone(f.validate_game(_valid_game()))

    # [유틸] _to_int: bool/float/string 등 입력 타입별 변환 규칙을 검증한다.
    def test_to_int_cases(self):
        self.assertIsNone(f._to_int(True))
        self.assertEqual(f._to_int(1), 1)
        self.assertEqual(f._to_int(1.0), 1)
        self.assertIsNone(f._to_int(1.2))
        self.assertEqual(f._to_int(" 42 "), 42)
        self.assertIsNone(f._to_int("abc"))

    # [유틸] _as_set: platforms 후보값 정규화 시 숫자만 추출되는지 검증한다.
    def test_as_set_cases(self):
        self.assertEqual(f._as_set(None), set())
        self.assertEqual(f._as_set("x"), set())
        self.assertEqual(
            f._as_set([1, 2.0, "3", "x", True, False, 2.2]),
            {1, 2, 3},
        )

    # [유틸] _has_description: summary/storyline 중 하나라도 있으면 True여야 한다.
    def test_has_description_cases(self):
        self.assertTrue(f._has_description({"summary": "a", "storyline": ""}))
        self.assertTrue(f._has_description({"summary": "", "storyline": "b"}))
        self.assertFalse(f._has_description({"summary": " ", "storyline": " "}))

    # [필터] aggregated_rating: None 허용, 변환 불가/기준 미달은 탈락해야 한다.
    def test_valid_aggregated_rating_cases(self):
        g = _valid_game()
        g["aggregated_rating"] = None
        self.assertTrue(f._valid_aggregated_rating(g))
        g["aggregated_rating"] = "abc"
        self.assertFalse(f._valid_aggregated_rating(g))
        g["aggregated_rating"] = 10
        self.assertFalse(f._valid_aggregated_rating(g))

    # [필터] rating/rating_count 변환 실패 또는 기준 미달 시 탈락해야 한다.
    def test_valid_rating_cases(self):
        g = _valid_game()
        g["rating"] = "abc"
        self.assertFalse(f._valid_rating(g))
        g = _valid_game()
        g["rating_count"] = 1
        self.assertFalse(f._valid_rating(g))

    # [필터] first_release_date가 없거나 변환 실패면 탈락해야 한다.
    def test_valid_release_ts_cases(self):
        g = _valid_game()
        g["first_release_date"] = "abc"
        self.assertFalse(f._valid_release_ts(g))
        g = _valid_game()
        g["first_release_date"] = None
        self.assertFalse(f._valid_release_ts(g))

    # [분기] validate_game: 각 실패 케이스에서 올바른 reason 코드가 반환되어야 한다.
    def test_validate_game_reasons(self):
        cases = [
            ("invalid_category", {"category": True}),
            ("invalid_status", {"status": None}),
            ("low_rating_or_count", {"rating_count": 0}),
            ("low_aggregated_rating", {"aggregated_rating": 10}),
            ("incomplete_data", {"summary": "", "storyline": ""}),
            ("platform_not_pc", {"platforms": [48]}),
            ("too_old_release_or_missing", {"first_release_date": MATCH_INGEST_MIN_RELEASE_TS - 1}),
        ]
        for expected, patch in cases:
            g = _valid_game()
            g.update(patch)
            self.assertEqual(f.validate_game(g), expected)
            self.assertEqual(f.validate_game({**_valid_game(), "first_release_date": None}), "incomplete_data")

    # [집계] filter_games_with_reasons: 통과 건수와 reason 카운트가 정확해야 한다.
    def test_filter_games_with_reasons(self):
        ok = _valid_game()
        bad1 = _valid_game()
        bad1["status"] = 1
        bad2 = _valid_game()
        bad2["platforms"] = [48]

        passed, reasons = f.filter_games_with_reasons([ok, bad1, bad2])

        self.assertEqual(len(passed), 1)
        self.assertEqual(reasons.get("invalid_status"), 1)
        self.assertEqual(reasons.get("platform_not_pc"), 1)
