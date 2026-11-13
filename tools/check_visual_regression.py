"""Exact PNG visual-regression checker for deterministic Chromium captures.

Baseline files live under tests/visual-baseline/. When a baseline is absent,
candidate mode reports it without failing. Pass --require-baseline to make
missing or changed screenshots fail.
"""

from __future__ import annotations

import argparse, hashlib, json, struct, sys, zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_PATTERN = "web-ui-*.png"


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE) or len(data) < 24:
        raise ValueError(f"{path} is not a valid PNG")
    return struct.unpack(">II", data[16:24])


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(
    candidate_dir: Path,
    baseline_dir: Path,
    require_baseline: bool,
    *,
    pattern: str = DEFAULT_PATTERN,
) -> int:
    if not candidate_dir.exists():
        print(f"candidate directory does not exist: {candidate_dir}", file=sys.stderr)
        return 2
    if not candidate_dir.is_dir():
        print(f"candidate path is not a directory: {candidate_dir}", file=sys.stderr)
        return 2

    candidates = sorted(candidate_dir.glob(pattern))
    if not candidates:
        print(
            f"no PNG candidates matching {pattern!r} in {candidate_dir}",
            file=sys.stderr,
        )
        return 2

    failed = False
    report = []
    for candidate in candidates:
        baseline = baseline_dir / candidate.name
        item = {
            "name": candidate.name,
            "candidate_sha256": digest(candidate),
            "candidate_size": png_size(candidate),
        }
        if not baseline.exists():
            item["status"] = "missing-baseline"
            failed = failed or require_baseline
        else:
            item["baseline_sha256"] = digest(baseline)
            item["baseline_size"] = png_size(baseline)
            item["status"] = "match" if item["candidate_sha256"] == item["baseline_sha256"] else "changed"
            failed = failed or item["status"] == "changed"
        report.append(item)

    print(json.dumps(report, indent=2))
    return 1 if failed else 0


# --- 🖼️ PNG fixtures for the tests (was tools/image_support/png.py): 8-bit RGB, not interlaced; rectangles are half-open (left, top, right, bottom) ---

def _rgb(color):
    if not isinstance(color, (tuple, list)) or len(color) != 3 or any(
        type(channel) is not int or not 0 <= channel <= 255 for channel in color
    ):
        raise ValueError("color must contain three integer channels from 0 to 255")
    return bytes(color)


def rgb_png(width, height, color, *, rectangles=()):
    """Return a PNG filled with color and optional (box, color) rectangles."""
    if any(type(n) is not int or not 1 <= n <= 4096 for n in (width, height)):
        raise ValueError("dimensions must be integers from 1 to 4096")
    pixels = bytearray(_rgb(color) * (width * height))
    for box, fill in rectangles:
        if not isinstance(box, (tuple, list)) or len(box) != 4 or any(type(n) is not int for n in box):
            raise ValueError("rectangle must contain four integer coordinates")
        left, top, right, bottom = box
        if not (0 <= left <= right <= width and 0 <= top <= bottom <= height):
            raise ValueError("rectangle must be inside the image")
        row = _rgb(fill) * (right - left)
        for y in range(top, bottom):
            start = (y * width + left) * 3
            pixels[start:start + len(row)] = row

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    stride = width * 3
    scanlines = b"".join(b"\0" + pixels[y * stride:(y + 1) * stride] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, default=Path("."))
    parser.add_argument("--baseline-dir", type=Path, default=Path("tests/visual-baseline"))
    parser.add_argument("--require-baseline", action="store_true")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN)
    args = parser.parse_args(argv)
    return compare(
        args.candidate_dir,
        args.baseline_dir,
        args.require_baseline,
        pattern=args.pattern,
    )


if __name__ == "__main__":
    raise SystemExit(main())
