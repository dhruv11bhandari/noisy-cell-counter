import io

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

FORMATS = {"PNG", "JPEG", "MPO", "TIFF", "BMP", "WEBP"}
MAX_PIXELS = 40_000_000
MAX_SIDE = 1200  # working resolution
RADII = np.array([3, 4, 5.5, 7.5, 10.5, 14.5])  # cell radii searched, in working pixels


def load(raw, channel="auto"):
    im = Image.open(io.BytesIO(raw))
    if im.format not in FORMATS or im.width * im.height > MAX_PIXELS:
        raise ValueError("unsupported image")
    im.seek(0)  # first page of a multi-page TIFF
    if im.mode[0] in "IF":  # 16/32-bit greyscale
        a = np.asarray(im, dtype=np.float32)
    else:
        rgb = np.asarray(im.convert("RGB"))
        ch = {"r": 0, "g": 1, "b": 2}.get(channel)
        if ch is None and channel != "gray":  # auto: the channel carrying the most signal
            ch = int(np.argmax(rgb[::4, ::4].reshape(-1, 3).std(0)))
        a = (rgb[..., ch] if ch is not None else np.asarray(im.convert("L"))).astype(np.float32)
    top = 255 if a.max() <= 255 else 65535 if a.max() <= 65535 else 0
    sat = float((a >= top).mean()) if top else 0.0
    lo, hi = np.percentile(a, [1, 99.8])  # robust stretch: ignores hot pixels and dim background
    a = np.clip((a - lo) / (hi - lo + 1e-9), 0, 1).astype(np.float32)
    s = min(1.0, MAX_SIDE / max(a.shape))
    return (ndi.zoom(a, s, order=1) if s < 1 else a), sat


def detect(g, radius=0.0, sens=1.0, polarity="auto"):
    dark = polarity == "dark" or (polarity == "auto" and (g > otsu(g)).mean() > 0.5)
    if dark:  # dark cells on a bright field: flip so cells are bright
        g = 1 - g
    radii = np.array([radius]) if radius else RADII
    S = np.stack([-(s * s) * ndi.gaussian_laplace(g, s, truncate=3.0) for s in radii / np.sqrt(2)])
    sc = S.max(0)
    pos = sc[sc > 0]
    th = max(0.03, otsu(pos) / sens) if pos.size else 1.0
    z, y, x = np.nonzero((ndi.maximum_filter(S, size=(3, 3, 3)) == S) & (S > th))
    o = np.argsort(-S[z, y, x])[:20000]
    z, y, x = z[o], y[o], x[o]
    r, v, P = radii[z], S[z, y, x], np.c_[x, y].astype(float)
    drop = set()
    if len(P) > 1:
        for i, j in cKDTree(P).query_pairs(1.3 * radii.max()):
            if np.hypot(*(P[i] - P[j])) < 0.65 * (r[i] + r[j]):
                drop.add(i if v[i] < v[j] else j)
    keep = [i for i in range(len(P)) if i not in drop]
    noise = 1.4826 * np.median(np.abs(sc - np.median(sc))) + 1e-6
    info = dict(snr=float(np.median(v[keep]) / noise) if keep else 0.0,
                coverage=float(min(1.0, np.pi * (r[keep] ** 2).sum() / g.size)))
    info["crowded"] = 0.0
    if len(keep) > 1:
        kept_points, kept_radii = P[keep], r[keep]
        nearest = cKDTree(kept_points).query(kept_points, k=2)[0][:, 1]
        typical_radius = float(np.median(kept_radii))
        info["crowded"] = float(np.mean(nearest < 3.0 * typical_radius))
    return np.c_[P[keep], r[keep]], info


def flags(info, n, sat):
    out = []
    if n == 0:
        out.append("No cells found. Try a different cell size, sensitivity or polarity.")
    elif info["snr"] < 5:
        out.append("Low contrast or noisy image: the count may be unreliable.")
    if info["coverage"] > 0.55:
        out.append("Very dense field: touching cells are probably undercounted.")
    elif info.get("crowded", 0.0) > 0.25:
        out.append("Many cells are close together: touching cells may be merged or undercounted.")
    if sat > 0.03:
        out.append("Over-exposed areas hide cell boundaries.")
    if n > 5000:
        out.append("Unusually many detections: check the image or lower the sensitivity.")
    return out


def otsu(a):
    h, e = np.histogram(a, 256)
    c = (e[:-1] + e[1:]) / 2
    w0 = np.cumsum(h)
    w1 = w0[-1] - w0
    s = np.cumsum(h * c)
    m0 = s / np.maximum(w0, 1)
    m1 = (s[-1] - s) / np.maximum(w1, 1)
    return c[np.argmax(w0 * w1 * (m0 - m1) ** 2)]


def cellpose_engine(g):
    from cellpose import models
    m = models.CellposeModel(gpu=False).eval((g * 255).astype(np.uint8))[0]
    n = int(m.max())
    if not n:
        return np.zeros((0, 2)), 8.0
    c = np.array(ndi.center_of_mass(m > 0, m, range(1, n + 1)))[:, ::-1]
    return c, float(np.sqrt(np.median(np.bincount(m.ravel())[1:]) / np.pi))
