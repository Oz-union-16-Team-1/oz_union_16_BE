from django.contrib.auth.models import AnonymousUser

from apps.games.models import Game
from apps.games.serializer.game_list_detail_serializers import GameListDetailSerializer


class GameDetailNotFoundError(Exception):
    """게임 상세 조회 대상이 없을 때 발생하는 예외입니다."""


class GameListDetailService:
    @staticmethod
    def get_game_detail(game_id: int, user=None) -> dict:
        """
        게임 상세 조회 API 응답 데이터를 반환합니다.

        - 존재하지 않는 게임이면 GameDetailNotFoundError 발생
        - 블랙리스트 처리된 게임은 상세 조회 대상에서 제외
        - 로그인 유저인 경우 좋아요 여부(is_liked)를 함께 계산
        """
        try:
            game = Game.objects.get(game_id=game_id, is_ban=False)
        except Game.DoesNotExist as exc:
            raise GameDetailNotFoundError("해당 게임을 찾을 수 없습니다.") from exc

        liked_game_ids = set()

        if (
            user is not None
            and not isinstance(user, AnonymousUser)
            and user.is_authenticated
        ):
            is_liked = user.like_bookmarks.filter(game_id=game.game_id).exists()
            if is_liked:
                liked_game_ids.add(game.game_id)

        serializer = GameListDetailSerializer(
            game,
            context={"liked_game_ids": liked_game_ids},
        )

        return serializer.data
