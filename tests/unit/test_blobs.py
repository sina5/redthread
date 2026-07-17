import pytest

from redthread.blobs.rsync import RsyncBackend
from redthread.hashing import sha256_file


def test_put_get_roundtrip_and_content_addressing(tmp_path):
    backend = RsyncBackend(tmp_path / "backend")
    source = tmp_path / "file.bin"
    source.write_bytes(b"payload")

    digest = backend.put(source)
    assert digest == sha256_file(source)
    assert backend.exists(digest)

    dest = tmp_path / "restored.bin"
    result = backend.get(digest, dest)
    assert result == dest
    assert dest.read_bytes() == b"payload"


def test_put_is_idempotent(tmp_path):
    backend = RsyncBackend(tmp_path / "backend")
    source = tmp_path / "file.bin"
    source.write_bytes(b"same content")
    d1 = backend.put(source)
    d2 = backend.put(source)
    assert d1 == d2


def test_get_missing_blob_raises(tmp_path):
    backend = RsyncBackend(tmp_path / "backend")
    with pytest.raises(FileNotFoundError):
        backend.get("0" * 64, tmp_path / "out.bin")
