from django.contrib import admin
from django.contrib.auth.hashers import make_password
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode

from apps.users.choices import StatusChoices
from apps.users.models import SocialUser, User, UserLikeBookmark, UserPreference


class UserLikeBookmarkInline(admin.TabularInline):
    model = UserLikeBookmark
    extra = 0
    can_delete = False
    fields = ("game_id", "created_at")
    readonly_fields = ("game_id", "created_at")
    ordering = ("-created_at",)
    verbose_name = "최근 좋아요 게임"
    verbose_name_plural = "최근 좋아요 게임 목록"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by("-created_at")[:20]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.action(description="선택한 회원 활성화")
def activate_users(modeladmin, request, queryset):
    queryset.update(
        status=StatusChoices.ACTIVE,
        is_active=True,
    )


@admin.action(description="선택한 회원 차단")
def suspend_users(modeladmin, request, queryset):
    queryset.update(
        status=StatusChoices.SUSPENDED,
        is_active=False,
    )


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "login_id",
        "nickname",
        "email",
        "status",
        "created_at",
    )

    ordering = ("-created_at",)

    search_fields = (
        "id",
        "login_id",
        "nickname",
        "email",
        "name",
    )

    list_filter = (
        "status",
        "created_at",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "like_more_link",
    )

    fieldsets = (
        ("기본 정보", {
            "fields": (
                "id",
                "login_id",
                "name",
                "nickname",
                "email",
                "status",
                "gender",
                "phone_number",
                "birthday",
                "profile_img_url",
                "created_at",
                "updated_at",
                "like_more_link",
            )
        }),
        ("권한 정보", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),
        ("비밀번호", {
            "fields": (
                "password",
            )
        }),
    )

    inlines = [UserLikeBookmarkInline]
    actions = [activate_users, suspend_users]

    def save_model(self, request, obj, form, change):
        """
        admin에서 비밀번호를 직접 수정할 때 평문 저장 방지.
        이미 해시된 비밀번호는 그대로 둔다.
        """
        if obj.password and not obj.password.startswith("pbkdf2_"):
            obj.password = make_password(obj.password)

        super().save_model(request, obj, form, change)

    def like_more_link(self, obj):
        if not obj:
            return "-"

        total_count = obj.like_bookmarks.count()

        if total_count <= 20:
            return f"총 {total_count}건"

        url = reverse("admin:users_userlikebookmark_changelist")
        query = urlencode({"user__id__exact": obj.id})

        return format_html(
            '<a class="button" href="{}?{}">더보기(총 {}건)</a>',
            url,
            query,
            total_count,
        )

    like_more_link.short_description = "좋아요 전체 목록"


@admin.register(UserLikeBookmark)
class UserLikeBookmarkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_login_id",
        "user_nickname",
        "user_email",
        "game_id",
        "created_at",
    )

    ordering = ("-created_at",)

    search_fields = (
        "user__login_id",
        "user__nickname",
        "user__email",
        "game_id",
    )

    list_filter = (
        "created_at",
    )

    readonly_fields = (
        "id",
        "user",
        "game_id",
        "created_at",
        "updated_at",
    )

    def user_login_id(self, obj):
        return obj.user.login_id

    user_login_id.short_description = "로그인아이디"

    def user_nickname(self, obj):
        return obj.user.nickname

    user_nickname.short_description = "닉네임"

    def user_email(self, obj):
        return obj.user.email

    user_email.short_description = "이메일"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SocialUser)
class SocialUserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "provider_id",
        "user",
        "created_at",
    )

    search_fields = (
        "provider",
        "provider_id",
        "user__login_id",
        "user__nickname",
        "user__email",
    )

    list_filter = (
        "provider",
        "created_at",
    )

    readonly_fields = (
        "id",
        "provider",
        "provider_id",
        "user",
        "created_at",
        "updated_at",
    )


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "has_survey_vector",
        "has_match_vector",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "user__login_id",
        "user__nickname",
        "user__email",
    )

    readonly_fields = (
        "id",
        "user",
        "survey_vector",
        "match_vector",
        "created_at",
        "updated_at",
    )

    def has_survey_vector(self, obj):
        return obj.survey_vector is not None

    has_survey_vector.boolean = True
    has_survey_vector.short_description = "설문 벡터 있음"

    def has_match_vector(self, obj):
        return obj.match_vector is not None

    has_match_vector.boolean = True
    has_match_vector.short_description = "매칭 벡터 있음"