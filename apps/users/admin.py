import math
from contextlib import suppress

from django.apps import apps
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from apps.users.choices import SocialProvider, StatusChoices
from apps.users.models import SocialUser, User, UserLikeBookmark, UserPreference

with suppress(admin.sites.NotRegistered):
    admin.site.unregister(BlacklistedToken)
with suppress(admin.sites.NotRegistered):
    admin.site.unregister(OutstandingToken)
with suppress(admin.sites.NotRegistered):
    admin.site.unregister(Group)

admin.site.site_header = "PGTI 관리자"
admin.site.site_title = "PGTI 관리자"
admin.site.index_title = "관리자 페이지"

apps.get_app_config("auth").verbose_name = "인증 및 권한"
apps.get_app_config("users").verbose_name = "회원 관리"

Group._meta.verbose_name = "그룹"
Group._meta.verbose_name_plural = "그룹"

User._meta.verbose_name = "회원"
User._meta.verbose_name_plural = "회원"
SocialUser._meta.verbose_name = "소셜 회원"
SocialUser._meta.verbose_name_plural = "소셜 회원"
UserLikeBookmark._meta.verbose_name = "게임 좋아요"
UserLikeBookmark._meta.verbose_name_plural = "게임 좋아요"
UserPreference._meta.verbose_name = "회원 선호 데이터"
UserPreference._meta.verbose_name_plural = "회원 선호 데이터"

GENRE_DIMENSIONS = (
    "액션/격투",
    "어드벤처/플랫폼",
    "RPG/스토리",
    "전략/시뮬",
    "스포츠/레이싱",
    "두뇌/퍼즐",
    "슈팅",
    "음악/리듬",
)

MOOD_DIMENSIONS = (
    ("캐주얼", "하드코어"),
    ("밝음", "어두움"),
    ("2D", "3D"),
    ("정적", "동적"),
    ("솔로", "멀티"),
    ("낮음", "높음"),
)


class UserPreferenceDashboard(UserPreference):
    class Meta:
        proxy = True
        verbose_name = "사용자 특성 데이터"
        verbose_name_plural = "사용자 특성 데이터"


class BlacklistedUser(User):
    class Meta:
        proxy = True
        verbose_name = "블랙리스트 회원"
        verbose_name_plural = "블랙리스트 회원"


@admin.action(description="선택한 회원 활성화")
def activate_users(modeladmin, request, queryset):
    queryset.update(status=StatusChoices.ACTIVE, is_active=True)


@admin.action(description="선택한 회원 차단")
def suspend_users(modeladmin, request, queryset):
    queryset.update(status=StatusChoices.SUSPENDED, is_active=False)


@admin.action(description="선택한 회원 비밀번호 초기화")
def reset_password(modeladmin, request, queryset):
    for user in queryset:
        user.set_password("Password1234@")
        user.save(update_fields=["password"])


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    change_list_template = "admin/users/user/change_list.html"
    likes_dashboard_url_name = "users_user_likes"
    list_display = (
        "id",
        "login_id_display",
        "nickname_display",
        "like_count_display",
        "signup_type_display",
        "is_active_display",
        "created_at_display",
    )
    list_display_links = ("id",)

    ordering = ("-created_at",)
    search_fields = ("id", "login_id", "nickname", "email", "name")
    list_filter = ("is_active", "is_staff", "created_at")
    exclude = ("email", "phone_number", "birthday", "profile_img_url", "groups")
    actions = [activate_users, suspend_users, reset_password]
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/likes/",
                self.admin_site.admin_view(self.likes_dashboard_view),
                name=self.likes_dashboard_url_name,
            ),
        ]
        return custom_urls + super().get_urls()

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("social_users")
            .annotate(like_count_value=Count("like_bookmarks", distinct=True))
        )

    @admin.display(description="로그인아이디", ordering="login_id")
    def login_id_display(self, obj):
        return obj.login_id

    @admin.display(description="닉네임", ordering="nickname")
    def nickname_display(self, obj):
        return obj.nickname

    @admin.display(description="좋아요 수", ordering="like_count_value")
    def like_count_display(self, obj):
        url = self.get_likes_dashboard_url(obj)
        return format_html('<a href="{}">{}</a>', url, obj.like_count_value)

    @admin.display(description="가입유형")
    def signup_type_display(self, obj):
        provider_labels = {
            SocialProvider.KAKAO: "카카오",
            SocialProvider.NAVER: "네이버",
            SocialProvider.GOOGLE: "구글",
        }
        providers = [social_user.provider for social_user in obj.social_users.all()]
        if not providers:
            return "일반"
        return ", ".join(
            provider_labels.get(provider, provider) for provider in providers
        )

    @admin.display(boolean=True, description="로그인 가능")
    def is_active_display(self, obj):
        return obj.is_active

    @admin.display(description="생성일", ordering="created_at")
    def created_at_display(self, obj):
        return obj.created_at

    def get_likes_dashboard_url(self, obj):
        return reverse("admin:users_user_likes", args=[obj.pk])

    def likes_dashboard_view(self, request, object_id):
        user = self.get_object(request, object_id)
        if user is None:
            return self._get_obj_does_not_exist_redirect(
                request,
                self.model._meta,
                object_id,
            )

        preference = self.get_user_preference(user)
        genre_scores, mood_scores = self.get_preference_scores(preference)
        likes = (
            UserLikeBookmark.objects.filter(user=user)
            .select_related("game")
            .order_by("-created_at")
        )
        context = {
            **self.admin_site.each_context(request),
            "title": f"{user.login_id} 좋아요 및 취향 대시보드",
            "opts": self.model._meta,
            "original": user,
            "user_obj": user,
            "preference": preference,
            "genre_scores": genre_scores,
            "mood_scores": mood_scores,
            "primary_genre": self.get_primary_genre(preference, genre_scores),
            "radar": self.build_radar_context(genre_scores),
            "likes": likes,
            "like_count": likes.count(),
            "signup_type": self.signup_type_display(user),
        }
        return TemplateResponse(
            request,
            "admin/users/user/likes_dashboard.html",
            context,
        )

    def get_user_preference(self, user):
        try:
            return user.preference
        except ObjectDoesNotExist:
            return None

    def get_preference_scores(self, preference):
        vector = []
        if preference and preference.match_vector is not None:
            vector = [float(value) for value in preference.match_vector]
        vector = (vector + [0.0] * 14)[:14]
        genre_scores = [
            {
                "label": label,
                "value": round(vector[index], 2),
                "percent": max(0, min(vector[index], 1)) * 100,
            }
            for index, label in enumerate(GENRE_DIMENSIONS)
        ]
        mood_scores = [
            {
                "left": left,
                "right": right,
                "value": round(vector[index + 8], 2),
                "percent": max(0, min(vector[index + 8], 1)) * 100,
            }
            for index, (left, right) in enumerate(MOOD_DIMENSIONS)
        ]
        return genre_scores, mood_scores

    def get_primary_genre(self, preference, genre_scores):
        if preference is None or preference.match_vector is None:
            return "-"
        return max(genre_scores, key=lambda score: score["value"])["label"]

    def build_radar_context(self, genre_scores):
        center = 150
        radius = 105
        points = []
        labels = []
        grid = []
        for score_index, score in enumerate(genre_scores):
            angle = (math.pi * 2 * score_index / len(genre_scores)) - (math.pi / 2)
            value = max(0, min(score["value"], 1))
            points.append(
                f"{center + math.cos(angle) * radius * value:.1f},"
                f"{center + math.sin(angle) * radius * value:.1f}"
            )
            labels.append(
                {
                    "text": score["label"],
                    "x": center + math.cos(angle) * (radius + 34),
                    "y": center + math.sin(angle) * (radius + 34),
                }
            )
        for grid_value in (0.25, 0.5, 0.75, 1):
            polygon_points = []
            for index in range(len(genre_scores)):
                angle = (math.pi * 2 * index / len(genre_scores)) - (math.pi / 2)
                polygon_points.append(
                    f"{center + math.cos(angle) * radius * grid_value:.1f},"
                    f"{center + math.sin(angle) * radius * grid_value:.1f}"
                )
            grid.append(" ".join(polygon_points))
        return {
            "center": center,
            "axis_end": radius,
            "points": " ".join(points),
            "labels": labels,
            "grid": grid,
        }


@admin.register(BlacklistedUser)
class BlacklistedUserAdmin(UserAdmin):
    change_list_template = "admin/users/blacklisteduser/change_list.html"
    likes_dashboard_url_name = "users_blacklisteduser_likes"
    readonly_fields = ("blacklisted_at_display",)
    list_display = (
        "id",
        "login_id_display",
        "nickname_display",
        "like_count_display",
        "signup_type_display",
        "is_active_display",
        "blacklisted_at_display",
    )
    ordering = ("-updated_at",)
    list_filter = ("is_active", "updated_at", "created_at")
    actions = [activate_users, reset_password]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=StatusChoices.SUSPENDED)

    def get_likes_dashboard_url(self, obj):
        return reverse("admin:users_blacklisteduser_likes", args=[obj.pk])

    @admin.display(description="블랙리스트 시간", ordering="updated_at")
    def blacklisted_at_display(self, obj):
        return obj.updated_at


@admin.register(UserLikeBookmark)
class UserLikeBookmarkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_login_id",
        "user_nickname",
        "game_display",
        "created_at_display",
    )

    ordering = ("-created_at",)
    search_fields = ("user__login_id", "user__nickname", "game__name")
    list_filter = ("user", "created_at")
    list_select_related = ("user", "game")
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    @admin.display(description="로그인아이디")
    def user_login_id(self, obj):
        return obj.user.login_id

    @admin.display(description="닉네임")
    def user_nickname(self, obj):
        return obj.user.nickname

    @admin.display(description="좋아요 게임")
    def game_display(self, obj):
        return getattr(obj.game, "name", obj.game_id)

    @admin.display(description="좋아요 생성일", ordering="created_at")
    def created_at_display(self, obj):
        return obj.created_at

    def get_model_perms(self, request):
        return {}

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "has_survey_vector",
        "has_match_vector",
    )

    search_fields = ("user__login_id", "user__nickname", "user__email")
    list_select_related = ("user",)
    empty_value_display = "-"

    @admin.display(boolean=True, description="설문 벡터 있음")
    def has_survey_vector(self, obj):
        return obj.survey_vector is not None

    @admin.display(boolean=True, description="매칭 벡터 있음")
    def has_match_vector(self, obj):
        return obj.match_vector is not None

    def get_model_perms(self, request):
        return {}


@admin.register(UserPreferenceDashboard)
class UserPreferenceDashboardAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_login_id",
        "user_nickname",
        "has_survey_vector",
        "has_match_vector",
    )

    search_fields = ("user__login_id", "user__nickname", "user__email")
    list_select_related = ("user",)
    empty_value_display = "-"

    @admin.display(description="로그인아이디")
    def user_login_id(self, obj):
        return obj.user.login_id

    @admin.display(description="닉네임")
    def user_nickname(self, obj):
        return obj.user.nickname

    @admin.display(boolean=True, description="설문 데이터")
    def has_survey_vector(self, obj):
        return obj.survey_vector is not None

    @admin.display(boolean=True, description="매칭 데이터")
    def has_match_vector(self, obj):
        return obj.match_vector is not None

    def get_model_perms(self, request):
        return {}


if not hasattr(admin.site, "_pgti_original_get_app_list"):
    admin.site._pgti_original_get_app_list = admin.site.get_app_list


def ordered_get_app_list(request, app_label=None):
    app_list = admin.site._pgti_original_get_app_list(request, app_label)
    user_model_order = {
        "회원": 0,
        "블랙리스트 회원": 1,
    }
    for app in app_list:
        if app["app_label"] == "users":
            app["models"].sort(
                key=lambda model: user_model_order.get(model["name"], 99)
            )
    return app_list


admin.site.get_app_list = ordered_get_app_list
