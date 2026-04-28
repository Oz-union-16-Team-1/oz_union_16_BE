from apps.users.models import UserLikeBookmark


class UserLikeBookmarkService:
    @staticmethod
    def get_user_bookmarks(user):
        return (
            UserLikeBookmark.objects
            .filter(user=user)
            .select_related("game")
            .order_by("-created_at")
        )