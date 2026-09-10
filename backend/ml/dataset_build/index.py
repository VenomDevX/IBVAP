"""Stage 1 — index every source image exactly once.

This is the only full pass over the source trees; every later stage reads the
index rather than re-walking ~677k files. Each record carries the two hashes
dedup needs (md5 for exact, dHash for near) and the dimensions later stages use
to pick the best representative of a duplicate group.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True, slots=True)
class ImageRecord:
    # slots is not a micro-optimisation here: the corpus is 677k records held in
    # memory at once, and dropping the per-instance __dict__ saves ~100 bytes
    # each. Without it the build was killed by the OS for memory exhaustion.
    path: str  # absolute, resolved
    source: str  # "detector" | "crops"
    rel: str  # path relative to its source root, forward slashes
    width: int
    height: int
    size: int  # bytes
    md5: str
    dhash: int  # 64-bit difference hash


def _dhash_from_open(im: Image.Image, size: int = 8) -> int:
    """dHash from an already-open image. Consumes draft()-scaled data if present."""
    small = im.convert("L").resize((size + 1, size), Image.BILINEAR)
    px = small.tobytes()
    bits = 0
    stride = size + 1
    for r in range(size):
        base = r * stride
        for c in range(size):
            bits = (bits << 1) | (1 if px[base + c] < px[base + c + 1] else 0)
    return bits


def dhash(path: str | Path, size: int = 8) -> int:
    """64-bit difference hash: size rows of size+1 pixels -> size comparisons each.

    Compares each pixel with its right-hand neighbour, so the hash encodes
    horizontal gradient direction and is insensitive to overall brightness.
    Note this makes it blind to purely vertical structure — an acceptable
    trade for near-duplicate detection, where real duplicates differ in neither.

    Uses tobytes() rather than the deprecated getdata(), and draft() so JPEGs
    decode at 1/8 scale instead of full resolution.
    """
    with Image.open(path) as im:
        im.draft("L", (size + 1, size))
        return _dhash_from_open(im, size)


def label_path_for(img_path: str) -> Path:
    """YOLO convention: .../images/<split>/x.jpg -> .../labels/<split>/x.txt"""
    s = str(img_path).replace("\\", "/")
    if "/images/" in s:
        s = s.replace("/images/", "/labels/", 1)
    return Path(s).with_suffix(".txt")


def has_label_file(img_path: str) -> bool:
    """True when a label file exists, even if it is empty.

    The distinction matters and is not cosmetic. An EMPTY label file is a
    deliberate background negative and is good training data. A MISSING label
    file means the annotation was lost — detector_yolo has 846 such images in
    images/valid alone. Treating those as backgrounds would teach the model to
    ignore the objects they actually contain, so callers drop them instead.
    scripts/make_clean_split.py has always applied this rule; we match it.
    """
    return label_path_for(img_path).exists()


def read_label_classes(img_path: str) -> list[int]:
    """Class ids of every box for an image; [] when the label is absent or empty.

    Use has_label_file() to tell a background negative from a lost annotation.
    """
    try:
        text = label_path_for(img_path).read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[int] = []
    for row in text.splitlines():
        parts = row.split()
        if parts:
            try:
                out.append(int(parts[0]))
            except ValueError:
                continue  # malformed row: skip it, verify() reports the file later
    return out


def walk_images(root: Path) -> Iterator[str]:
    """Yield every image path under root. Pure scandir — cheap, no decoding."""
    stack: list[str] = [str(root)]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            if e.is_dir(follow_symlinks=False):
                stack.append(e.path)
            elif os.path.splitext(e.name)[1].lower() in IMG_EXT:
                yield e.path


def _record_for(args: tuple[str, str, str]) -> ImageRecord | None:
    """Hash and measure one image. Module-level so it is picklable by a pool.

    Returns None for unreadable or corrupt files; they cannot be trained on and
    the caller compares counts against the walk total to notice losses.
    """
    path, root, source = args
    try:
        # One disk read serves both the md5 and the decode; one decode serves
        # both the dimensions and the dHash. The first version read the file
        # twice and decoded it twice, managing only 63 img/s.
        with open(path, "rb") as fh:
            blob = fh.read()
        digest = hashlib.md5(blob).hexdigest()
        with Image.open(io.BytesIO(blob)) as im:
            w, h = im.size  # true size, before draft() rescales it
            im.draft("L", (9, 8))  # JPEG: decode at 1/8 scale
            dh = _dhash_from_open(im)
    except Exception:
        return None
    return ImageRecord(
        path=str(Path(path).resolve()),
        source=source,
        rel=os.path.relpath(path, root).replace("\\", "/"),
        width=w,
        height=h,
        size=len(blob),
        md5=digest,
        dhash=dh,
    )


def scan_tree(
    root: Path, source: str, workers: int | None = None, progress: int = 0
) -> Iterator[ImageRecord]:
    """Yield an ImageRecord for every readable image under root.

    Hashing ~677k images is CPU-bound on JPEG decode, so it runs across a
    process pool by default: single-threaded managed 139 img/s (81 min for the
    full corpus), which is an unacceptable slice of a ~30h training budget.
    Pass workers=1 to stay in-process (tests, or to debug a decode failure).
    """
    root = Path(root)
    if workers is None:
        workers = max(1, min(8, (os.cpu_count() or 4)))

    paths = walk_images(root)
    if workers == 1:
        results: Iterator[ImageRecord | None] = (
            _record_for((p, str(root), source)) for p in paths
        )
    else:
        pool = ProcessPoolExecutor(max_workers=workers)
        results = pool.map(
            _record_for, ((p, str(root), source) for p in paths), chunksize=64
        )

    n = 0
    try:
        for rec in results:
            if rec is None:
                continue
            n += 1
            if progress and n % progress == 0:
                print(f"    ...{n:,}", flush=True)
            yield rec
    finally:
        if workers != 1:
            pool.shutdown(wait=False, cancel_futures=True)


def write_index(records: Iterable[ImageRecord], out: Path) -> int:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(asdict(r)) + "\n")
            n += 1
    return n


def read_index(path: Path) -> list[ImageRecord]:
    out: list[ImageRecord] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(ImageRecord(**json.loads(line)))
    return out
