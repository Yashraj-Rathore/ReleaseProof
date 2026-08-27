"""Local development settings."""

from apps.web.releaseproof.settings.base import *  # noqa: F403
from apps.web.releaseproof.settings.base import env_bool

DEBUG = env_bool("DJANGO_DEBUG", default=True)
