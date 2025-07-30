import environ
from pathlib import Path
from rest_framework.response import Response


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

environ.Env.read_env(BASE_DIR / ".env")
env = environ.Env()

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

SECRET_KEY = env("SECRET_KEY")

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "api.urls"

WSGI_APPLICATION = "api.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
    }
}

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_TZ = False

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
}

SESS_EXP_SECONDS = 3600  # 1 hour

LONG_SESS_EXP_SECONDS = 31536000  # 1 year

EMAIL_CODE_EXP_SECONDS = 1800  # 30 minutes

PWD_RESET_EXP_SECONDS = 1800  # 30 minutes

GENERIC_ERR_RESPONSE = Response(
    {"error": {"general": ["An unknown error has occurred."]}}, status=500
)

# AWS SES Credentials
EMAIL_BACKEND = "django_ses.SESBackend"
AWS_SES_ACCESS_KEY_ID = env("AWS_SES_ACCESS_KEY_ID")
AWS_SES_SECRET_ACCESS_KEY = env("AWS_SES_SECRET_ACCESS_KEY")
AWS_SES_REGION_NAME = env("AWS_SES_REGION_NAME")
AWS_SES_REGION_ENDPOINT = env("AWS_SES_REGION_ENDPOINT")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

BASE_URL = env("BASE_URL")
