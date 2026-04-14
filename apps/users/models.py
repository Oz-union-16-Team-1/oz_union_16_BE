from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from pgvector.django import VectorField
from apps.users.choices import StatusChoices, SocialProvider, GenderChoices

EMBEDDING_DIM = 0  # TODO: 벡터 길이(차원 수)를 고정하는 값을 정해야 함


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, login_id, password=None, **extra_fields):
        if not login_id:
            raise ValueError("login_id is required")

        email = extra_fields.get('email')
        if email:
            extra_fields['email'] = self.normalize_email(email)

        user = self.model(login_id=login_id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login_id, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("superuser must have is_superuser=True")

        return self.create_user(login_id, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    login_id = models.CharField(max_length=30, unique=True, db_index=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    password = models.CharField(max_length=128, db_column="hashed_password")

    name = models.CharField(max_length=30)
    nickname = models.CharField(max_length=30)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=1, choices=GenderChoices.choices)
    birthday = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=9, choices=StatusChoices.choices, default=StatusChoices.ACTIVE
    )
    profile_img_url = models.CharField(max_length=255, blank=True, null=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "login_id"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.login_id} ({self.name})"


class SocialUser(models.Model):
    provider = models.CharField(max_length=10, choices=SocialProvider.choices)
    provider_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="social_users",
    )

    class Meta:
        db_table = (
            "social_users"
        )
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_id"],
                name="uq_social_provider_provider_id",
            )
        ]


class UserLikeBookmark(models.Model):
    game_id = models.IntegerField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="like_bookmarks",
    )

    class Meta:
        db_table = (
            "user_like_bookmarks"  # 사용자-게임 북마크는 1회만 허용 (중복 좋아요 방지)
        )
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game_id"],
                name="uq_user_game_bookmark",
            )
        ]


class UserPreference(models.Model):  # 사용자 선호 벡터는 유저당 1행(OneToOne)으로 유지
    survey_vector = VectorField(
        null=True, blank=True
    )  # TODO: 임베딩 모델 확정 후 VectorField(dimensions=...)로 차원 고정.
    match_vector = VectorField(
        null=True, blank=True
    )  # TODO: 임베딩 모델 확정 후 VectorField(dimensions=...)로 차원 고정.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="preference",
    )

    class Meta:
        db_table = "user_preferences"
