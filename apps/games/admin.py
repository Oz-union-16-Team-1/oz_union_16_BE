from django.contrib import admin
from django.apps import apps

from apps.games.models import Game

apps.get_app_config("games").verbose_name = "게임 관리"

Game._meta.verbose_name = "게임"
Game._meta.verbose_name_plural = "게임"


class GameBlacklist(Game):
    class Meta:
        proxy = True
        verbose_name = "블랙리스트 게임"
        verbose_name_plural = "블랙리스트 게임"


@admin.action(description="선택한 게임 블랙리스트 등록")
def ban_games(modeladmin, request, queryset):
    queryset.update(is_ban=True)


@admin.action(description="선택한 게임 블랙리스트 해제")
def unban_games(modeladmin, request, queryset):
    queryset.update(is_ban=False, ban_reason="")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    change_list_template = "admin/games/game/change_list.html"
    list_display = (
        "game_id",
        "name",
        "name_ko",
        "is_ban_display",
        "ban_reason",
        "rating",
        "like_count",
        "created_at",
    )

    ordering = ("-created_at",)
    search_fields = ("game_id", "name", "name_ko")
    list_filter = ("is_ban", "created_at")
    readonly_fields = ("game_id", "created_at")
    actions = (ban_games, unban_games)
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    fieldsets = (
        (
            "기본 정보",
            {
                "fields": (
                    "game_id",
                    "name",
                    "name_ko",
                    "slug",
                    "summary",
                    "storyline",
                    "rating",
                    "like_count",
                    "is_ban",
                    "ban_reason",
                    "created_at",
                )
            },
        ),
        (
            "분류 정보",
            {
                "fields": (
                    "category",
                    "status",
                    "game_type",
                    "genres",
                    "themes",
                    "keywords",
                )
            },
        ),
        (
            "이미지/영상/링크",
            {
                "fields": (
                    "cover",
                    "screenshots",
                    "videos",
                    "websites",
                )
            },
        ),
        (
            "출시/평점 정보",
            {
                "fields": (
                    "first_release_date",
                    "rating_count",
                    "aggregated_rating",
                    "aggregated_rating_count",
                    "total_rating",
                    "total_rating_count",
                    "follows",
                    "hypes",
                )
            },
        ),
    )

    @admin.display(boolean=True, description="블랙리스트", ordering="is_ban")
    def is_ban_display(self, obj):
        return obj.is_ban


@admin.register(GameBlacklist)
class GameBlacklistAdmin(admin.ModelAdmin):
    list_display = (
        "game_id",
        "name",
        "name_ko",
        "ban_reason",
        "created_at",
    )

    ordering = ("-created_at",)
    search_fields = ("game_id", "name", "name_ko")
    list_filter = ("created_at",)
    readonly_fields = ("game_id", "name", "name_ko", "created_at")
    actions = (unban_games,)
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    fieldsets = (
        (
            "블랙리스트 정보",
            {
                "fields": (
                    "game_id",
                    "name",
                    "name_ko",
                    "ban_reason",
                    "created_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_ban=True)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
