#!/usr/bin/env python3
"""
remove_bg.py — Smart background removal for pixel art / AI-generated sprites

Modes:
  flood:  edge-connected flood fill (safe for characters with bg-colored pixels)
  chroma: global green chroma key
  smart:  flood fill THEN removes isolated lime-green islands (best for complex cases)

Usage:
  python3 remove_bg.py input.png [output.png] [--mode flood|chroma|smart] [--tolerance 40]
  python3 remove_bg.py folder/                # batch, smart mode default
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


def flood_fill(data, bg_color, tolerance):
    """BFS flood fill from image edges. Returns boolean mask of pixels to remove."""
    h, w = data.shape[:2]
    visited = np.zeros((h, w), dtype=bool)
    remove  = np.zeros((h, w), dtype=bool)
    queue   = deque()

    for x in range(w):
        queue.append((0, x))
        queue.append((h - 1, x))
    for y in range(h):
        queue.append((y, 0))
        queue.append((y, w - 1))

    while queue:
        y, x = queue.popleft()
        if y < 0 or y >= h or x < 0 or x >= w or visited[y, x]:
            continue
        visited[y, x] = True
        px = tuple(data[y, x, :3])
        if color_distance(px, bg_color) <= tolerance:
            remove[y, x] = True
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                    queue.append((ny, nx))

    return remove


def is_lime_green(pixel, tolerance=60):
    """True if a pixel is 'lime green' background color — bright green, low red+blue."""
    r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
    return (
        g > 160 and          # green channel dominant
        g - r > tolerance and  # greener than red
        g - b > tolerance      # greener than blue
    )


def remove_islands(data, tolerance=60):
    """
    Find isolated connected regions of lime-green pixels NOT connected to edges,
    and remove them. Handles interior trapped background like green boxes/halos.
    """
    h, w = data.shape[:2]
    alpha = data[:, :, 3]

    # Build a mask of remaining visible lime-green pixels
    visible = alpha > 0
    r = data[:,:,0].astype(int)
    g = data[:,:,1].astype(int)
    b = data[:,:,2].astype(int)
    green_mask = visible & (g > 160) & ((g - r) > tolerance) & ((g - b) > tolerance)

    # Label connected components in green_mask
    labeled  = np.zeros((h, w), dtype=np.int32)
    label_id = 0
    touches_edge = set()

    for sy in range(h):
        for sx in range(w):
            if not green_mask[sy, sx] or labeled[sy, sx] != 0:
                continue
            label_id += 1
            queue = deque([(sy, sx)])
            labeled[sy, sx] = label_id
            is_edge = False
            while queue:
                y, x = queue.popleft()
                if y == 0 or y == h-1 or x == 0 or x == w-1:
                    is_edge = True
                for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < h and 0 <= nx < w and green_mask[ny, nx] and labeled[ny, nx] == 0:
                        labeled[ny, nx] = label_id
                        queue.append((ny, nx))
            if is_edge:
                touches_edge.add(label_id)

    # Remove all components NOT touching edges (trapped interior islands)
    island_mask = (labeled > 0) & ~np.isin(labeled, list(touches_edge))
    removed = island_mask.sum()
    data[island_mask, 3] = 0
    return removed


def remove_smart(src: Path, dst: Path, tolerance: int = 45):
    """Flood fill from edges + remove isolated green islands."""
    img  = Image.open(src).convert("RGBA")
    w, h = img.size
    data = np.array(img)

    bg_color = tuple(data[0, 0, :3])

    # Step 1: flood fill from edges
    mask = flood_fill(data, bg_color, tolerance)
    data[mask, 3] = 0
    edge_removed = mask.sum()

    # Step 2: remove trapped interior green islands
    island_removed = remove_islands(data, tolerance=50)

    result = Image.fromarray(data.astype(np.uint8), "RGBA")
    result.save(dst)
    print(f"  ✅ {src.name} → {dst.name} "
          f"({edge_removed} edge + {island_removed} island px removed, bg={bg_color})")


def remove_flood(src: Path, dst: Path, tolerance: int = 40):
    img  = Image.open(src).convert("RGBA")
    data = np.array(img)
    bg_color = tuple(data[0, 0, :3])
    mask = flood_fill(data, bg_color, tolerance)
    data[mask, 3] = 0
    result = Image.fromarray(data.astype(np.uint8), "RGBA")
    result.save(dst)
    print(f"  ✅ {src.name} → {dst.name} ({mask.sum()} px removed, flood fill)")


def remove_chroma(src: Path, dst: Path, tolerance: int = 40):
    img  = Image.open(src).convert("RGBA")
    data = np.array(img, dtype=np.int16)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    mask = (g > 180) & (g - r > tolerance) & (g - b > tolerance)
    data[:,:,3] = np.where(mask, 0, a)
    result = Image.fromarray(data.astype(np.uint8), "RGBA")
    result.save(dst)
    print(f"  ✅ {src.name} → {dst.name} ({mask.sum()} px removed, chroma key)")


def process(src, dst, mode, tolerance):
    if mode == "chroma":
        remove_chroma(src, dst, tolerance)
    elif mode == "flood":
        remove_flood(src, dst, tolerance)
    else:
        remove_smart(src, dst, tolerance)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input")
    parser.add_argument("output", nargs="?")
    parser.add_argument("--mode", choices=["flood","chroma","smart"], default="smart")
    parser.add_argument("--tolerance", type=int, default=45)
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
