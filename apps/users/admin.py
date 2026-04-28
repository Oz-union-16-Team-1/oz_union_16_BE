from contextlib import suppress

from django.apps import apps
from django.contrib import admin
from django.contrib.auth.models import Group
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from apps.users.choices import StatusChoices
from apps.users.models import SocialUser, User, UserLikeBookmark, UserPreference

with suppress(admin.sites.NotRegistered):
    admin.site.unregister(BlacklistedToken)
with suppress(admin.sites.NotRegistered):
    admin.site.unregister(OutstandingToken)

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


class UserPreferenceDashboard(UserPreference):
    class Meta:
        proxy = True
        verbose_name = "사용자 특성 데이터"
        verbose_name_plural = "사용자 특성 데이터"


class UserLikeBookmarkInline(admin.TabularInline):
    model = UserLikeBookmark
    extra = 0
    can_delete = False
    fields = ("game_id", "created_at")
    readonly_fields = ("game_id", "created_at")
    ordering = ("-created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).order_by("-created_at")[:20]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
    list_display = (
        "id",
        "login_id_display",
        "nickname_display",
        "email_display",
        "status_display",
        "is_active_display",
        "created_at_display",
    )

    ordering = ("-created_at",)
    search_fields = ("id", "login_id", "nickname", "email", "name")
    list_filter = ("status", "is_active", "is_staff", "created_at")
    inlines = [UserLikeBookmarkInline]
    actions = [activate_users, suspend_users, reset_password]
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    @admin.display(description="로그인아이디", ordering="login_id")
    def login_id_display(self, obj):
        return obj.login_id

    @admin.display(description="닉네임", ordering="nickname")
    def nickname_display(self, obj):
        return obj.nickname

    @admin.display(description="이메일", ordering="email")
    def email_display(self, obj):
        return obj.email

    @admin.display(description="상태", ordering="status")
    def status_display(self, obj):
        return obj.get_status_display()

    @admin.display(boolean=True, description="로그인 가능")
    def is_active_display(self, obj):
        return obj.is_active

    @admin.display(description="생성일", ordering="created_at")
    def created_at_display(self, obj):
        return obj.created_at


@admin.register(UserLikeBookmark)
class UserLikeBookmarkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_login_id",
        "user_nickname",
        "user_email",
        "game_id",
        "created_at_display",
    )

    ordering = ("-created_at",)
    search_fields = ("user__login_id", "user__nickname", "user__email", "game_id")
    list_filter = ("created_at",)
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    @admin.display(description="로그인아이디")
    def user_login_id(self, obj):
        return obj.user.login_id

    @admin.display(description="닉네임")
    def user_nickname(self, obj):
        return obj.user.nickname

    @admin.display(description="이메일")
    def user_email(self, obj):
        return obj.user.email

    @admin.display(description="좋아요 생성일", ordering="created_at")
    def created_at_display(self, obj):
        return obj.created_at

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SocialUser)
class SocialUserAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "provider_id", "user")
    search_fields = (
        "provider",
        "provider_id",
        "user__login_id",
        "user__nickname",
        "user__email",
    )
    list_select_related = ("user",)
    empty_value_display = "-"


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
