"""Blob backends: content-addressed storage for large artifacts.

The store repo holds only pointer records (Artifact); the bytes live here,
addressed by sha256, so the same checkpoint/build-output/dataset is
identical and dedupe-able across every node that touches it.
"""

from redthread.blobs.base import BlobBackend
from redthread.blobs.rsync import RsyncBackend

__all__ = ["BlobBackend", "RsyncBackend"]
