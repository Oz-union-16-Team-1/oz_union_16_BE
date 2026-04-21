import os

from config.settings.base import *

DEBUG = False

ALLOWED_HOSTS = [
    "oz-pgti.duckdns.org",
    "oz-union-16-fe.vercel.app",
    "13.211.150.226",
    "localhost",
    "127.0.0.1",
]

STATIC_URL = "/static/"

STATIC_ROOT = os.path.join(BASE_DIR, "static")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")


CORS_ALLOWED_ORIGINS = [
    "https://oz-union-16-fe.vercel.app",
    "https://oz-pgti.duckdns.org",
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
