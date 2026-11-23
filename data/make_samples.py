import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

rng = np.random.default_rng(7)
OUT = Path(__file__).parent / "samples"


def make(n, w, h, rmin, rmax, noise, shade, blur, clump=0.0):
    img, pts = np.zeros((h, w), np.float32), []
    for _ in range(n):
        if pts and rng.random() < clump:  # place next to an existing cell: touching clumps
            cx, cy = pts[rng.integers(len(pts))]
            a, d = rng.uniform(0, 6.283), rng.uniform(1.2, 1.9) * rmax
            x, y = np.clip(cx + d * np.cos(a), 12, w - 12), np.clip(cy + d * np.sin(a), 12, h - 12)
        else:
            x, y = rng.uniform(12, w - 12), rng.uniform(12, h - 12)
        pts.append((x, y))
        s, amp = rng.uniform(rmin, rmax) * 0.6, rng.uniform(0.5, 1.0)
        x0, x1 = int(max(0, x - 4 * s)), int(min(w, x + 4 * s + 1))
        y0, y1 = int(max(0, y - 4 * s)), int(min(h, y + 4 * s + 1))
        yy, xx = np.mgrid[y0:y1, x0:x1]
        img[y0:y1, x0:x1] += amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * s * s))
    img = img * (1 - shade * np.linspace(0, 1, w)[None, :]) + 0.06  # uneven illumination plus background
    img = ndi.gaussian_filter(img + noise * rng.standard_normal((h, w)), blur)
    return Image.fromarray((np.clip(img / np.percentile(img, 99.7), 0, 1) * 255).astype(np.uint8))


SPEC = [("sparse", "Sparse nuclei", 70, 640, 480, 5, 8, 0.03, 0.0, 0.6, 0.0),
        ("uneven", "Dense, uneven lighting", 220, 640, 480, 4, 7, 0.05, 0.55, 0.8, 0.0),
        ("clumped", "Touching cells, slightly out of focus", 150, 640, 480, 5, 8, 0.04, 0.2, 1.4, 0.5)]

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    manifest = []
    for key, title, n, w, h, r0, r1, noise, shade, blur, clump in SPEC:
        make(n, w, h, r0, r1, noise, shade, blur, clump).save(OUT / f"{key}.png")
        manifest.append({"file": f"{key}.png", "title": title, "truth": n})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
