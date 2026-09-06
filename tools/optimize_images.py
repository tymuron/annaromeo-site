#!/usr/bin/env python3
"""
Shrink oversized originals in site/assets so the static site is not heavier
than what Tilda actually served (Tilda never served the originals — its
lazyloader requested resized variants from optim.tildacdn). Keeps filenames
so no HTML changes are needed.

Rules
  * JPEG/PNG wider or taller than MAX_EDGE px -> scaled down to MAX_EDGE.
  * JPEG re-encoded at QUALITY with progressive + optimize.
  * PNG: only resized (kept lossless) unless it has no alpha, in which case a
    large PNG (> 1 MB) is left as PNG but resized.
  * GIF / SVG / WEBP / ICO untouched.
  * Never touches files under assets/thb (already-resized thumbnails).

Usage: python3 tools/optimize_images.py site [--max-edge 2000] [--quality 85] [--dry]
"""
import os
import sys

from PIL import Image, ImageOps

MAX_EDGE = 2000
QUALITY = 85


def main():
    root = sys.argv[1]
    max_edge = int(sys.argv[sys.argv.index("--max-edge") + 1]) if "--max-edge" in sys.argv else MAX_EDGE
    quality = int(sys.argv[sys.argv.index("--quality") + 1]) if "--quality" in sys.argv else QUALITY
    dry = "--dry" in sys.argv
    before = after = 0
    touched = 0
    for d, _, files in os.walk(os.path.join(root, "assets", "static")):
        for fn in files:
            ext = fn.lower().rsplit(".", 1)[-1] if "." in fn else ""
            if ext not in ("jpg", "jpeg", "png"):
                continue
            p = os.path.join(d, fn)
            size0 = os.path.getsize(p)
            before += size0
            try:
                im = Image.open(p)
                im.load()
            except Exception as e:  # noqa: BLE001
                print(f"skip (unreadable) {p}: {e}", file=sys.stderr)
                after += size0
                continue
            w, h = im.size
            needs_resize = max(w, h) > max_edge
            is_jpeg = ext in ("jpg", "jpeg")
            if not needs_resize and not (is_jpeg and size0 > 600_000):
                after += size0
                continue
            im = ImageOps.exif_transpose(im)
            if needs_resize:
                im.thumbnail((max_edge, max_edge), Image.LANCZOS)
            if dry:
                print(f"would  {p}: {w}x{h} {size0//1024}k")
                after += size0
                continue
            tmp = p + ".tmp"
            if is_jpeg:
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                im.save(tmp, "JPEG", quality=quality, optimize=True, progressive=True)
            else:
                im.save(tmp, "PNG", optimize=True)
            size1 = os.path.getsize(tmp)
            if size1 < size0:
                os.replace(tmp, p)
                touched += 1
                after += size1
            else:
                os.remove(tmp)
                after += size0
    print(f"files rewritten: {touched}; {before/1e6:.1f} MB -> {after/1e6:.1f} MB")


if __name__ == "__main__":
    main()
