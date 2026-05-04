from django.apps import apps
from django.contrib import admin
from django.db.models import Avg, Count

from apps.games.models import Game
from apps.games.service.game_dashboard_services import GameDashboardService

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
    change_form_template = "admin/games/game/change_form.html"
    list_display = (
        "game_id_display",
        "name",
        "dashboard_genres",
        "dashboard_like_count",
        "dashboard_rating_count",
        "dashboard_average_star",
        "is_ban_display",
    )
    list_display_links = ("game_id_display",)

    ordering = ("-created_at",)
    search_fields = ("game_id", "name", "name_ko")
    list_filter = ("is_ban", "created_at")
    readonly_fields = ("game_id", "created_at")
    actions = (ban_games, unban_games)
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    @admin.display(description="게임 ID", ordering="game_id")
    def game_id_display(self, obj):
        return obj.game_id

    @admin.display(description="장르")
    def dashboard_genres(self, obj):
        genres = GameDashboardService._get_genre_names(obj)
        return ", ".join(genres) if genres else "-"

    @admin.display(description="총 좋아요 수", ordering="like_count")
    def dashboard_like_count(self, obj):
        return obj.like_count

    @admin.display(description="총 평가 수", ordering="dashboard_match_rating_count")
    def dashboard_rating_count(self, obj):
        return getattr(obj, "dashboard_match_rating_count", 0) or 0

    @admin.display(description="평균 별점")
    def dashboard_average_star(self, obj):
        avg = getattr(obj, "dashboard_average_star_rating", None)
        return round(float(avg), 2) if avg is not None else "-"

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

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        dashboard = GameDashboardService.get_dashboard(int(object_id))
        extra_context["dashboard"] = dashboard
        extra_context["title"] = f"{dashboard['basic_info']['game_name']} 상세페이지"
        return super().change_view(request, object_id, form_url, extra_context)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                dashboard_match_rating_count=Count("match_ratings"),
                dashboard_average_star_rating=Avg("match_ratings__star_rating"),
            )
        )

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GameBlacklist)
class GameBlacklistAdmin(admin.ModelAdmin):
    change_form_template = "admin/games/game/change_form.html"
    list_display = (
        "game_id_display",
        "name",
        "dashboard_genres",
        "dashboard_like_count",
        "dashboard_rating_count",
        "dashboard_average_star",
        "is_ban_display",
    )
    list_display_links = ("game_id_display",)

    ordering = ("-created_at",)
    search_fields = ("game_id", "name")
    list_filter = ("created_at",)
    readonly_fields = ("game_id", "name", "name_ko", "created_at")
    actions = (unban_games,)
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    @admin.display(description="게임 ID", ordering="game_id")
    def game_id_display(self, obj):
        return obj.game_id

    @admin.display(description="장르")
    def dashboard_genres(self, obj):
        genres = GameDashboardService._get_genre_names(obj)
        return ", ".join(genres) if genres else "-"

    @admin.display(description="총 좋아요 수", ordering="like_count")
    def dashboard_like_count(self, obj):
        return obj.like_count

    @admin.display(description="총 평가 수", ordering="dashboard_match_rating_count")
    def dashboard_rating_count(self, obj):
        return getattr(obj, "dashboard_match_rating_count", 0) or 0

    @admin.display(description="평균 별점")
    def dashboard_average_star(self, obj):
        avg = getattr(obj, "dashboard_average_star_rating", None)
        return round(float(avg), 2) if avg is not None else "-"

    @admin.display(boolean=True, description="블랙리스트", ordering="is_ban")
    def is_ban_display(self, obj):
        return obj.is_ban

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        dashboard = GameDashboardService.get_dashboard(int(object_id))
        extra_context["dashboard"] = dashboard
        extra_context["title"] = f"{dashboard['basic_info']['game_name']} 상세페이지"
        return super().change_view(request, object_id, form_url, extra_context)

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
        return (
            super()
            .get_queryset(request)
            .filter(is_ban=True)
            .annotate(
                dashboard_match_rating_count=Count("match_ratings"),
                dashboard_average_star_rating=Avg("match_ratings__star_rating"),
            )
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False
