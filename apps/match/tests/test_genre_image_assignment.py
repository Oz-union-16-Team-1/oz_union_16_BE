from django.test import SimpleTestCase

from apps.match.services.genre_image_assignment import (
    GenreImageCandidate,
    _sort_candidates,
    assign_genre_images,
)


class MatchGenreImageAssignmentTest(SimpleTestCase):
    # 후보 정렬은 rating > rating_count > game_id 우선순위를 따른다.
    def test_sort_candidates_priority(self):
        candidates = [
            GenreImageCandidate(game_id=1, image_url="u1", rating=90.0, rating_count=10),
            GenreImageCandidate(game_id=2, image_url="u2", rating=92.0, rating_count=5),
            GenreImageCandidate(game_id=3, image_url="u3", rating=92.0, rating_count=20),
            GenreImageCandidate(game_id=4, image_url="u4", rating=92.0, rating_count=20),
        ]

        sorted_list = _sort_candidates(candidates)
        self.assertEqual([c.game_id for c in sorted_list], [4, 3, 2, 1])

    # 앞 장르에서 사용한 game_id는 다음 장르에서 제외하고 차순위 후보를 배정
    def test_assign_genre_images_deduplicates_across_genres(self):
        candidates_by_genre = {
            1: [
                GenreImageCandidate(100, "u100", 95.0, 50),
                GenreImageCandidate(101, "u101", 90.0, 40),
            ],
            2: [
                GenreImageCandidate(100, "u100", 97.0, 60),  # 중복 후보
                GenreImageCandidate(102, "u102", 89.0, 30),
            ],
        }

        result = assign_genre_images(
            candidates_by_genre=candidates_by_genre,
            priority=[1, 2],
        )

        self.assertEqual(result[1]["game_id"], 100)
        self.assertEqual(result[2]["game_id"], 102)
        self.assertNotEqual(result[1]["game_id"], result[2]["game_id"])

    # 배정 가능한 후보가 없으면 RuntimeError로 배치 실패를 명확히 알림
    def test_assign_genre_images_raises_when_empty(self):
        with self.assertRaises(RuntimeError):
            assign_genre_images(candidates_by_genre={1: []}, priority=[1])
