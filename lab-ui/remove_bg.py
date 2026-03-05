#!/usr/bin/env python3
"""
remove_bg.py — Chroma key green (#00FF00) → transparent PNG
Usage: python3 remove_bg.py input.png [output.png]
       python3 remove_bg.py avatars/   # batch process a folder
"""

import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Installing deps...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "Pillow", "numpy", "-q"])
    from PIL import Image
    import numpy as np


def remove_green(src: Path, dst: Path, tolerance: int = 40):
    img = Image.open(src).convert("RGBA")
    data = np.array(img, dtype=np.int16)

    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]

    # Mask: green channel dominates, within tolerance of pure #00FF00
    mask = (
        (g > 180) &                    # green is high
        (g - r > tolerance) &          # greener than red
        (g - b > tolerance)            # greener than blue
    )

    data[:,:,3] = np.where(mask, 0, a)  # set alpha=0 where green
    result = Image.fromarray(data.astype(np.uint8), "RGBA")
    result.save(dst)
    print(f"  ✅ {src.name} → {dst.name} ({mask.sum()} px removed)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.is_dir():
        out_dir = target / "transparent"
        out_dir.mkdir(exist_ok=True)
        for f in sorted(target.glob("*.png")):
            if f.parent.name == "transparent":
                continue
            remove_green(f, out_dir / f.name)
        print(f"\nSaved to {out_dir}/")
    else:
        dst = Path(sys.argv[2]) if len(sys.argv) > 2 else target.with_stem(target.stem + "_transparent")
        remove_green(target, dst)


if __name__ == "__main__":
    main()
