import os

from config.settings.base import *

DEBUG = True

# RAW_ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "")
# if not RAW_ALLOWED_HOSTS:
#     raise ValueError("DJANGO_ALLOWED_HOSTS must be set")

# ALLOWED_HOSTS = RAW_ALLOWED_HOSTS.split(" ")

ALLOWED_HOSTS = ["0.0.0.0", "localhost", "127.0.0.1"]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

INTERNAL_IPS = [
    "127.0.0.1",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# 로컬 개발 시에는 편리하게 페이지를 볼 수 있도록 유지합니다.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = tuple(
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"]
) + ("rest_framework.renderers.BrowsableAPIRenderer",)
