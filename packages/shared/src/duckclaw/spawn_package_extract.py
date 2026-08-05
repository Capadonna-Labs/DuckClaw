"""Extract spawn package archives to a flat files dict."""

from __future__ import annotations

import io
import tarfile
import zipfile


def extract_spawn_package(data: bytes) -> dict[str, str]:
    """Return relative path → text content from zip or gzip tar."""
    if data[:2] == b"PK":
        return _extract_zip(data)
    if data[:2] in (b"\x1f\x8b", b"\x42\x5a"):
        return _extract_tar(data)
    # try zip anyway
    try:
        return _extract_zip(data)
    except zipfile.BadZipFile:
        return _extract_tar(data)


def _normalize_member(name: str) -> str:
    parts = name.replace("\\", "/").split("/")
    # drop single root folder like demo-worker-spawn-package/
    if len(parts) > 1 and parts[0].endswith("-spawn-package"):
        parts = parts[1:]
    return "/".join(p for p in parts if p and p != ".")


def _extract_zip(data: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = _normalize_member(info.filename)
            if not rel:
                continue
            raw = zf.read(info)
            try:
                out[rel] = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
    return out


def _extract_tar(data: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            rel = _normalize_member(member.name)
            if not rel:
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            raw = extracted.read()
            try:
                out[rel] = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
    return out
