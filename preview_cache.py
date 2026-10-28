"""Bounded, thumbnail-only AFC preview cache.

Only resized SDR JPEG thumbnails persist on disk. Original bytes are fetched to
an automatically removed TemporaryDirectory and never written into the cache.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time
from PIL import Image, ImageOps

MAX_CACHE_BYTES = 500 * 1024 * 1024
THUMB_SIZE = (320, 320)


def cache_file(cache_dir: Path, source: str) -> Path:
    digest = hashlib.sha256(source.encode('utf-8')).hexdigest()
    return Path(cache_dir) / f'{digest}.jpg'


def trim_cache(cache_dir: Path, max_bytes: int = MAX_CACHE_BYTES, keep=()) -> int:
    """LRU eviction of generated jpg thumbnails only. Return bytes remaining."""
    root = Path(cache_dir)
    if not root.exists():
        return 0
    protected = {Path(p).resolve() for p in keep}
    files = []
    for p in root.glob('*.jpg'):
        try:
            stat = p.stat()
            files.append((stat.st_mtime, p, stat.st_size))
        except OSError:
            continue
    total = sum(x[2] for x in files)
    for _, p, size in sorted(files):
        if total <= max_bytes:
            break
        if p.resolve() in protected:
            continue
        try:
            p.unlink()
            total -= size
        except OSError:
            continue
    return total


def clear_legacy_cache(cache_dir: Path) -> None:
    """Remove known old cache-owned originals, not any user-export directory.

    Earlier releases wrote full-resolution files under previews/DCIM and used a
    manifest there. The new thumbnails have hashed filenames in previews/*.jpg.
    """
    root = Path(cache_dir)
    for name in ('DCIM', 'PhotoData', '.hushphoto-staging'):
        target = root / name
        if target.is_dir():
            shutil.rmtree(target)
    for name in ('.hushphoto-manifest.json', 'hushphoto_last_export.json'):
        (root / name).unlink(missing_ok=True)


def thumbnail_from_afc(afc, source: str, cache_dir: Path,
                       cancelled=None, max_bytes: int = MAX_CACHE_BYTES) -> Path:
    """Fetch a single photo, resize it to <=320px, remove temp original.

    A failure never leaves the original behind or a partially written thumbnail.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_file(cache_dir, source)
    if out.is_file() and out.stat().st_size > 0:
        os.utime(out, None)
        return out
    if cancelled is not None and cancelled.is_set():
        raise InterruptedError('Отменено')
    with tempfile.TemporaryDirectory(prefix='hushphoto-preview-') as scratch:
        original = Path(scratch) / 'original'
        afc.read_to('/' + source.lstrip('/'), original, cancelled=cancelled)
        if cancelled is not None and cancelled.is_set():
            raise InterruptedError('Отменено')
        with Image.open(original) as opened:
            image = ImageOps.exif_transpose(opened)
            image.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
            # Preview is deliberately SDR; export pipeline retains original HEIC/HDR.
            if image.mode != 'RGB':
                image = image.convert('RGB')
            tmp = Path(scratch) / 'thumb.jpg'
            image.save(tmp, format='JPEG', quality=85, optimize=True)
        # Atomic publish on same volume; scratch may be on a different disk.
        publish = out.with_name(out.name + '.part')
        try:
            shutil.copyfile(tmp, publish)
            os.replace(publish, out)
        finally:
            publish.unlink(missing_ok=True)
    trim_cache(cache_dir, max_bytes=max_bytes, keep=(out,))
    return out
