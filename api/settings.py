import logging
import os
from pathlib import Path

import environ
from celery.schedules import crontab
from rest_framework.response import Response

from api.logging import FancyFormatter

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
    "DEFAULT_THROTTLE_RATES": {
        "user_account_creation": "4/hour",
        "resend_email": "3/hour",
        "guest_account_creation": "2/hour",
        "login": "10/hour",
        "password_reset": "3/hour",
        "event_creation": "6/hour",
    },
}

SESS_EXP_SECONDS = 3600  # 1 hour

LONG_SESS_EXP_SECONDS = 31536000  # 1 year

EMAIL_CODE_EXP_SECONDS = 1800  # 30 minutes

PWD_RESET_EXP_SECONDS = 1800  # 30 minutes

URL_CODE_EXP_SECONDS = 1209600  # 14 days

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
SEND_EMAILS = env.bool("SEND_EMAILS", default=False)

BASE_URL = env("BASE_URL")

# Automated tasks
CELERY_BEAT_SCHEDULE = {
    "daily_cleanup": {
        "task": "api.tasks.daily_cleanup",
        "schedule": crontab(hour=0, minute=0),  # Every day at midnight
    },
}
CELERY_BROKER_URL = "redis://localhost:6379/0"

LOG_DIR = env("LOG_DIR")
os.makedirs(LOG_DIR, exist_ok=True)  # Make the log directory if it doesn't exist
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname:<8} {asctime}] {module:<12} {funcName:<25} {message}",
            "style": "{",
        },
        "simple": {
            "()": FancyFormatter,
            "format": "[{levelname:<8} {asctime}] {message}",
            "datefmt": "%H:%M:%S",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "level": "DEBUG" if DEBUG else "WARNING",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": f"{LOG_DIR}/django.log",
            "formatter": "verbose",
            "level": "DEBUG",
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 5,
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": True,
        },
        "api": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}


# Custom logger just to add some of my own custom logging functions
# We love DRY!!!
class PlancakeLogger(logging.Logger):
    def db_error(self, msg, *args, **kwargs):
        self.error("Database error: %s", msg, *args, **kwargs)


# Now any logger in the project will have access to this class
logging.setLoggerClass(PlancakeLogger)
