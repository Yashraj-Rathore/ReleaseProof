"""Object-storage adapters."""

from adapters.object_storage.fake import FakeObjectStorage
from adapters.object_storage.s3 import S3ObjectStorage, S3Settings

__all__ = ("FakeObjectStorage", "S3ObjectStorage", "S3Settings")
