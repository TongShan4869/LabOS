#!/usr/bin/env python3
"""
remove_bg.py — Smart background removal for pixel art
Two modes:
  - flood:  edge-connected flood fill (default, safe for characters with bg-colored pixels)
  - chroma: global green chroma key (fast but can eat interior greens like mantis shrimp)

Usage:
  python3 remove_bg.py input.png [output.png] [--mode flood|chroma] [--tolerance 40]
  python3 remove_bg.py avatars/                # batch folder, flood mode
"""

import sys
import argparse
from pathlib import Path
from collections import deque

try:
    from PIL import Image
    import numpy as np
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "Pillow", "numpy", "-q"])
    from PIL import Image
    import numpy as np


def color_distance(c1, c2):
    return sum((int(a) - int(b)) ** 2 for a, b in zip(c1[:3], c2[:3])) ** 0.5


def remove_flood(src: Path, dst: Path, tolerance: int = 40):
    """
    Flood fill from all 4 edges. Only removes pixels connected to the border
    that are within `tolerance` color distance of the background color
    (sampled from the top-left corner).
    Safe for characters that share colors with the background.
    """
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    data = np.array(img)

    # Sample background color from corner (most likely pure bg)
    bg_color = tuple(data[0, 0, :3])

    # Build visited mask via BFS from all edge pixels
    visited = np.zeros((h, w), dtype=bool)
    remove  = np.zeros((h, w), dtype=bool)
    queue   = deque()

    # Seed: all edge pixels
    for x in range(w):
        queue.append((0, x))
        queue.append((h - 1, x))
    for y in range(h):
        queue.append((y, 0))
        queue.append((y, w - 1))

    while queue:
        y, x = queue.popleft()
        if y < 0 or y >= h or x < 0 or x >= w:
            continue
        if visited[y, x]:
            continue
        visited[y, x] = True

        px = tuple(data[y, x, :3])
        if color_distance(px, bg_color) <= tolerance:
            remove[y, x] = True
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                    queue.append((ny, nx))

    data[remove, 3] = 0
    result = Image.fromarray(data.astype(np.uint8), "RGBA")
    result.save(dst)
    removed = remove.sum()
    print(f"  ✅ {src.name} → {dst.name} ({removed} px removed, flood fill, bg={bg_color})")


def remove_chroma(src: Path, dst: Path, tolerance: int = 40):
    """Global green chroma key — fast but can eat interior greens."""
    img = Image.open(src).convert("RGBA")
    data = np.array(img, dtype=np.int16)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    mask = (g > 180) & (g - r > tolerance) & (g - b > tolerance)
    data[:,:,3] = np.where(mask, 0, a)
    result = Image.fromarray(data.astype(np.uint8), "RGBA")
    result.save(dst)
    print(f"  ✅ {src.name} → {dst.name} ({mask.sum()} px removed, chroma key)")


def process(src: Path, dst: Path, mode: str, tolerance: int):
    if mode == "chroma":
        remove_chroma(src, dst, tolerance)
    else:
        remove_flood(src, dst, tolerance)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input",  help="Input PNG file or folder")
    parser.add_argument("output", nargs="?", help="Output PNG (single file mode)")
    parser.add_argument("--mode", choices=["flood", "chroma"], default="flood",
                        help="Removal mode (default: flood)")
    parser.add_argument("--tolerance", type=int, default=40,
                        help="Color distance tolerance (default: 40)")
    args = parser.parse_args()

    target = Path(args.input)

    if target.is_dir():
        out_dir = target / "transparent"
        out_dir.mkdir(exist_ok=True)
        for f in sorted(target.glob("*.png")):
            if f.parent.name == "transparent":
                continue
            process(f, out_dir / f.name, args.mode, args.tolerance)
        print(f"\nSaved to {out_dir}/")
    else:
        dst = Path(args.output) if args.output else target.with_stem(target.stem + "_transparent")
        process(target, dst, args.mode, args.tolerance)


if __name__ == "__main__":
    main()
