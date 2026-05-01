from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.match.models import MatchGenreImagePublished
from apps.match.services.genre_image_candidates import (
    GenreImageCandidate,
    GenreImageCandidatesService,
)
from apps.users.models import User

UserModel = get_user_model()


class MatchGenreImagePublishService:
    def __init__(
        self, candidates_service: GenreImageCandidatesService | None = None
    ) -> None:
        self.candidates_service = candidates_service or GenreImageCandidatesService()

    def build_candidates(
        self, limit_per_genre: int = 5
    ) -> dict[int, list[GenreImageCandidate]]:
        return self.candidates_service.build_candidates_by_genre(
            limit_per_genre=limit_per_genre
        )

    @transaction.atomic
    def seed_or_refresh(
        self, user: User | None, limit_per_genre: int = 5
    ) -> tuple[int, int]:
        candidates_by_genre = self.build_candidates(limit_per_genre=limit_per_genre)
        updated = 0
        missing = 0

        for genre_id in range(1, 9):
            candidates = candidates_by_genre.get(genre_id, [])
            if not candidates:
                missing += 1
                continue

            top1 = candidates[0]
            images = top1.get("images", [])
            if not images:
                missing += 1
                continue

            MatchGenreImagePublished.objects.update_or_create(
                api_genre_id=genre_id,
                defaults={
                    "game_id": top1["game_id"],
                    "image_url": images[0]["url"],
                    "selected_by": user,
                },
            )
            updated += 1

        return updated, missing

    @transaction.atomic
    def pick_candidate_image(
        self,
        obj: MatchGenreImagePublished,
        game_id: int,
        image_index: int,
        user: User | None,
        limit_per_genre: int = 5,
    ) -> tuple[bool, str]:
        candidates_by_genre = self.build_candidates(limit_per_genre=limit_per_genre)
        candidate_map = {
            c["game_id"]: c for c in candidates_by_genre.get(obj.api_genre_id, [])
        }
        picked = candidate_map.get(game_id)

        if picked is None:
            return (
                False,
                "선택한 게임은 현재 후보 5개에 없습니다. 새로고침 후 다시 선택하세요.",
            )

        images = picked.get("images", [])
        if not images:
            return False, "선택 가능한 이미지가 없습니다."

        if image_index < 0 or image_index >= len(images):
            image_index = 0

        obj.game_id = picked["game_id"]
        obj.image_url = images[image_index]["url"]
        obj.selected_by = user
        obj.save(update_fields=["game", "image_url", "selected_by", "updated_at"])

        return (
            True,
            f"장르 {obj.api_genre_id} 게시본을 game_id={picked['game_id']}로 반영했습니다.",
        )
