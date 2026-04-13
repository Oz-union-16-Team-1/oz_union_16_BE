from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from pgvector.django import VectorField

EMBEDDING_DIM = 0  # TODO: 벡터 길이(차원 수)를 고정하는 값을 정해야 함


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, login_id, email, password=None, **extra_fields):
        if not login_id:
            raise ValueError("login_id is required")
        if not email:
            raise ValueError("email is required")

        email = self.normalize_email(email)
        user = self.model(login_id=login_id, email=email, **extra_fields)
        user.set_password(password)  # 해시 저장
        user.save(using=self._db)
        return user

    def create_superuser(self, login_id, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("superuser must have is_superuser=True")

        return self.create_user(login_id, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class GenderChoices(models.TextChoices):
        MALE = "M", "M"
        WOMAN = "W", "W"

    class StatusChoices(models.TextChoices):
        ACTIVE = "ACTIVE", "active"
        BLOCKED = "BLOCKED", "blocked"

    user_id = models.BigAutoField(primary_key=True)
    login_id = models.CharField(max_length=30, unique=True, db_index=True)
    email = models.EmailField(unique=True)

    # AbstractBaseUser.password를 오버라이드해서, ERD의 hashed_password 컬럼명만 db_column으로 매핑
    password = models.CharField(max_length=128, db_column="hashed_password")

    name = models.CharField(max_length=30)
    nickname = models.CharField(max_length=10)
    phone_number = models.CharField(max_length=20)
    gender = models.CharField(max_length=1, choices=GenderChoices.choices)
    birthday = models.DateField()
    status = models.CharField(
        max_length=10, choices=StatusChoices, default=StatusChoices.ACTIVE
    )
    profile_img_url = models.CharField(max_length=255, blank=True, null=True)

    is_staff = models.BooleanField(default=False)  # admin 로그인 권한
    is_active = models.BooleanField(default=True)  # 계정 활성화 여부

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = (
        "login_id"  # 로그인 식별자는 login_id를 사용 (AUTH_USER_MODEL 기준)
    )
    REQUIRED_FIELDS = ["email", "name"]

    objects = UserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.login_id


class SocialUser(models.Model):
    id = models.BigAutoField(primary_key=True)
    provider = models.CharField(max_length=20)
    provider_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="social_users",
    )

    class Meta:
        db_table = (
            "social_users"  # 동일 소셜 계정(provider+provider_id)의 중복 연동 방지
        )
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_id"],
                name="uq_social_provider_provider_id",
            )
        ]


class UserLikeBookmark(models.Model):
    user_game_like_id = models.BigAutoField(primary_key=True)
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
    user_preferences_id = models.BigAutoField(primary_key=True)
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
