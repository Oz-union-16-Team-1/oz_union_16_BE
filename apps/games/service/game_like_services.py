from django.db import transaction
from django.db.models import F

from apps.games.models import Game
from apps.users.models import UserLikeBookmark


class GameLikeGameNotFoundError(Exception):
    """좋아요 대상 게임이 없을 때 발생하는 예외입니다."""


class GameLikeBookmarkNotFoundError(Exception):
    """좋아요 취소 대상 기록이 없을 때 발생하는 예외입니다."""


class GameLikeService:
    @staticmethod
    def like_game(*, user, game_id: int) -> dict[str, int]:
        """
        게임 좋아요를 생성합니다.

        - 게임이 없거나 차단된 게임이면 404
        - 이미 좋아요한 게임이면 중복 생성하지 않고 현재 like_count 반환
        - 새로 좋아요가 생성된 경우에만 like_count 증가
        """
        with transaction.atomic():
            game = (
                Game.objects.select_for_update()
                .filter(game_id=game_id, is_ban=False)
                .first()
            )

            if game is None:
                raise GameLikeGameNotFoundError("해당 게임을 찾을 수 없습니다.")

            _, created = UserLikeBookmark.objects.get_or_create(
                user=user,
                game=game,
            )

            if created:
                Game.objects.filter(game_id=game.game_id).update(
                    like_count=F("like_count") + 1
                )
                game.refresh_from_db(fields=["like_count"])

            return {
                "game_id": int(game.game_id),
                "like_count": int(game.like_count),
            }

    @staticmethod
    def unlike_game(*, user, game_id: int) -> dict[str, int]:
        """
        게임 좋아요를 취소합니다.

        - 게임이 없거나 차단된 게임이면 404
        - 좋아요 기록이 없으면 404
        - 좋아요 기록 삭제 후 like_count 감소
        - like_count는 0 아래로 내려가지 않도록 방어
        """
        with transaction.atomic():
            game = (
                Game.objects.select_for_update()
                .filter(game_id=game_id, is_ban=False)
                .first()
            )

            if game is None:
                raise GameLikeGameNotFoundError("해당 게임을 찾을 수 없습니다.")

            deleted_count, _ = UserLikeBookmark.objects.filter(
                user=user,
                game=game,
            ).delete()

            if deleted_count == 0:
                raise GameLikeBookmarkNotFoundError("좋아요 기록을 찾을 수 없습니다.")

            Game.objects.filter(game_id=game.game_id, like_count__gt=0).update(
                like_count=F("like_count") - 1
            )
            game.refresh_from_db(fields=["like_count"])

            return {
                "game_id": int(game.game_id),
                "like_count": int(game.like_count),
            }
