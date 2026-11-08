import os

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = ["localhost"]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
]
MIDDLEWARE = []
ROOT_URLCONF = "config.urls"
EMAIL_HOST = os.environ["MAIL_RELAY_HOST"]
EMAIL_PORT = 587
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
