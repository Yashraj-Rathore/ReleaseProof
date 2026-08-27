"""ReleaseProof Django project configuration."""

from apps.web.releaseproof.celery import app as celery_app

__all__ = ("celery_app",)
