import os

from config.settings.base import *

DEBUG = True

# RAW_ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "")
# if not RAW_ALLOWED_HOSTS:
#     raise ValueError("DJANGO_ALLOWED_HOSTS must be set")

# ALLOWED_HOSTS = RAW_ALLOWED_HOSTS.split(" ")

ALLOWED_HOSTS = []

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

INTERNAL_IPS = [
    "127.0.0.1",
]


