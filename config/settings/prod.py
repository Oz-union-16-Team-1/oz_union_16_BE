import os

from config.settings.base import *

DEBUG = False

ALLOWED_HOSTS = ["oz-pgti.duckdns.org", "13.211.150.226", "localhost", "127.0.0.1"]

STATIC_URL = "/static/"

STATIC_ROOT = os.path.join(BASE_DIR, "static")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
