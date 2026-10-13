"""Files attached to journal entries: photos and PDFs.

What is allowed, and why:
- Only JPEG, PNG, WebP and PDF, decided by the file's own bytes, not its name.
- Photos are re-encoded, which drops GPS and device metadata, fixes rotation and
  caps the size. A decoded-pixel limit stops decompression bombs.
- Files are stored under random names outside any web root and are served only
  through the logged-in API, with headers that stop the browser running them.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
from pathlib import Path

from . import db

MAX_BYTES = 10 * 1024 * 1024
MAX_PER_ENTRY = 6
MAX_PIXELS = 50_000_000
MAX_EDGE = 2560
THUMB_EDGE = 480
PDF_MIME = "application/pdf"
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", PDF_MIME: "pdf"}


class Rejected(Exception):
    """The file can't be stored; the message is safe to show."""


def root() -> Path:
    path = Path(os.environ.get("ATTACHMENTS_DIR", "/data/attachments"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def total_cap() -> int:
    return int(os.environ.get("ATTACHMENTS_CAP_MB", "2048")) * 1024 * 1024


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:5] == b"%PDF-":
        return PDF_MIME
    return None


_UNSAFE = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]")


def clean_name(name: str | None, mime: str) -> str:
    base = _UNSAFE.sub("", os.path.basename((name or "").strip())).strip(". ")[:120]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return f"{stem or 'attachment'}.{EXT[mime]}"


def _process_image(data: bytes, mime: str) -> tuple[bytes, int, int, bytes]:
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, ValueError) as exc:
        raise Rejected("That image couldn't be read.") from exc
    img = ImageOps.exif_transpose(img)
    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE))
    width, height = img.size

    out = io.BytesIO()
    if mime == "image/jpeg":
        img.convert("RGB").save(out, "JPEG", quality=86, optimize=True)      # no exif argument: metadata is dropped
    elif mime == "image/png":
        img.save(out, "PNG", optimize=True)
    else:
        img.save(out, "WEBP", quality=86)

    thumb = img.convert("RGBA") if img.mode in ("P", "LA", "RGBA") else img.convert("RGB")
    if thumb.mode == "RGBA":
        background = Image.new("RGB", thumb.size, (255, 255, 255))
        background.paste(thumb, mask=thumb.getchannel("A"))
        thumb = background
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE))
    tb = io.BytesIO()
    thumb.save(tb, "JPEG", quality=80, optimize=True)
    return out.getvalue(), width, height, tb.getvalue()


def prepare(data: bytes, filename: str | None) -> dict:
    """Validate and clean one upload. Returns what `save` needs; raises Rejected with a readable reason."""
    if not data:
        raise Rejected("That file is empty.")
    if len(data) > MAX_BYTES:
        raise Rejected(f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    mime = sniff(data)
    if mime is None:
        raise Rejected("Only photos (JPEG, PNG, WebP) and PDFs can be attached.")
    width = height = None
    thumb = None
    if mime == PDF_MIME:
        stored = data
    else:
        stored, width, height, thumb = _process_image(data, mime)
    return {"data": stored, "mime": mime, "filename": clean_name(filename, mime), "width": width,
            "height": height, "thumb": thumb}


def _write(directory: Path, name: str, data: bytes) -> None:
    target = directory / name[:2]
    target.mkdir(parents=True, exist_ok=True)
    tmp = target / f".{name}.part"
    tmp.write_bytes(data)
    os.replace(tmp, target / name)


def _path(name: str) -> Path:
    return root() / name[:2] / name


def used_bytes() -> int:
    with db.connect() as conn:
        return int(conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM journal.attachments").fetchone()[0])


def save(log_id: int, prepared: dict) -> dict:
    """Store a prepared file against an entry. Enforces the per-entry and total limits."""
    with db.connect() as conn:
        exists = conn.execute("SELECT 1 FROM journal.activity_logs WHERE id=%s", (log_id,)).fetchone()
        if not exists:
            raise Rejected("That entry no longer exists.")
        count = conn.execute("SELECT count(*) FROM journal.attachments WHERE log_id=%s", (log_id,)).fetchone()[0]
        if count >= MAX_PER_ENTRY:
            raise Rejected(f"An entry can hold up to {MAX_PER_ENTRY} files.")
        used = int(conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM journal.attachments").fetchone()[0])
        if used + len(prepared["data"]) > total_cap():
            raise Rejected("The attachment storage is full.")

        token = uuid.uuid4().hex
        stored_name = f"{token}.{EXT[prepared['mime']]}"
        thumb_name = f"{token}.thumb.jpg" if prepared["thumb"] else None
        base = root()
        _write(base, stored_name, prepared["data"])
        if thumb_name:
            _write(base, thumb_name, prepared["thumb"])
        row = conn.execute(
            "INSERT INTO journal.attachments (log_id, filename, mime, bytes, width, height, sha256, stored_name, "
            "thumb_name) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (log_id, prepared["filename"], prepared["mime"], len(prepared["data"]), prepared["width"],
             prepared["height"], hashlib.sha256(prepared["data"]).hexdigest(), stored_name, thumb_name)).fetchone()
        conn.commit()
    return {"id": row[0], "filename": prepared["filename"], "mime": prepared["mime"], "bytes": len(prepared["data"]),
            "width": prepared["width"], "height": prepared["height"], "has_thumb": bool(thumb_name)}


def add(log_id: int, data: bytes, filename: str | None) -> dict:
    return save(log_id, prepare(data, filename))


def _public(row) -> dict:
    return {"id": row[0], "log_id": row[1], "filename": row[2], "mime": row[3], "bytes": row[4],
            "width": row[5], "height": row[6], "has_thumb": bool(row[7])}


def for_logs(log_ids: list[int]) -> dict[int, list[dict]]:
    """{log_id: [attachment metadata]} for the given entries."""
    ids = [i for i in log_ids if i is not None]
    if not ids:
        return {}
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, log_id, filename, mime, bytes, width, height, thumb_name FROM journal.attachments "
            "WHERE log_id = ANY(%s) ORDER BY id", (ids,)).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r[1], []).append(_public(r))
    return out


def get(attachment_id: int, thumb: bool = False) -> tuple[Path, str, str] | None:
    """(path on disk, mime, download name) or None."""
    with db.connect() as conn:
        row = conn.execute("SELECT stored_name, thumb_name, mime, filename FROM journal.attachments WHERE id=%s",
                           (attachment_id,)).fetchone()
    if not row:
        return None
    if thumb:
        if not row[1]:
            return None
        path, mime = _path(row[1]), "image/jpeg"
    else:
        path, mime = _path(row[0]), row[2]
    return (path, mime, row[3]) if path.is_file() else None


def _unlink(*names: str | None) -> None:
    for name in names:
        if name:
            try:
                _path(name).unlink()
            except FileNotFoundError:
                pass


def delete(attachment_id: int) -> bool:
    with db.connect() as conn:
        row = conn.execute("DELETE FROM journal.attachments WHERE id=%s RETURNING stored_name, thumb_name",
                           (attachment_id,)).fetchone()
        conn.commit()
    if not row:
        return False
    _unlink(*row)
    return True


def file_names_for_log(conn, log_id: int) -> list[str]:
    rows = conn.execute("SELECT stored_name, thumb_name FROM journal.attachments WHERE log_id=%s", (log_id,)).fetchall()
    return [n for r in rows for n in r if n]


def remove_files(names: list[str]) -> None:
    _unlink(*names)
