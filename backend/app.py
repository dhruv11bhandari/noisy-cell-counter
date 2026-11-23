import base64
import io
import logging
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from PIL import Image

import counter
import stats

ROOT = Path(__file__).resolve().parent.parent
FRONT, SAMPLES = ROOT / "frontend", ROOT / "data" / "samples"
JEFFREYS = stats.PRIORS["jeffreys"]

app = Flask(__name__, static_folder=None)
try:
    MAX_UPLOAD_MB = max(1, min(100, int(os.environ.get("MAX_UPLOAD_MB", 25))))
    MAX_CONCURRENT = max(1, min(32, int(os.environ.get("MAX_CONCURRENT", 2))))
    RATE = max(1, min(10000, int(os.environ.get("RATE_LIMIT_PER_MIN", 30))))
except ValueError as exc:
    raise RuntimeError("MAX_UPLOAD_MB, MAX_CONCURRENT and RATE_LIMIT_PER_MIN must be integers") from exc
LIMITS = {"/api/v1/analyze": RATE, "/api/v1/model": RATE * 8}
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 2**20
if os.environ.get("TRUST_PROXY") == "1":  # set when behind nginx or a load balancer
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ncc")
slots = threading.BoundedSemaphore(MAX_CONCURRENT)
hits = defaultdict(deque)
hits_lock = threading.Lock()


@app.before_request
def rate_limit():
    cap = LIMITS.get(request.path)
    if request.method != "POST" or not cap:
        return None
    now = time.monotonic()
    with hits_lock:
        q = hits[(request.remote_addr or "unknown", request.path)]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= cap:
            return jsonify(error="Too many requests. Please wait a minute."), 429
        q.append(now)
        if len(hits) > 20000:
            hits.clear()
    return None


@app.after_request
def secure(r):
    r.headers.update({
        "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()"})
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
    return r


@app.errorhandler(413)
def too_big(_):
    return jsonify(error="That file is too large."), 413


@app.errorhandler(500)
def broken(_):
    return jsonify(error="Something went wrong on the server."), 500


@app.get("/")
def index():
    return send_from_directory(FRONT, "index.html", max_age=0)


@app.get("/assets/<path:p>")
def assets(p):
    return send_from_directory(FRONT / "assets", p, max_age=3600)


@app.get("/samples/<path:p>")
def sample_file(p):
    return send_from_directory(SAMPLES, p, max_age=3600)


@app.get("/healthz")
def health():
    return jsonify(ok=True)


@app.get("/api/v1/samples")
def samples():
    f = SAMPLES / "manifest.json"
    return app.response_class(f.read_text(encoding="utf-8"), mimetype="application/json") if f.exists() else jsonify([])


@app.post("/api/v1/analyze")
def analyze():
    a = request.args
    try:
        k = int(a.get("k", 4))
        radius = float(a.get("radius") or 0)
        sens = float(a.get("sens", 1))
        if not 2 <= k <= 8 or not np.isfinite(radius + sens) or not 0 <= radius <= 40 or not 0.3 <= sens <= 3:
            raise ValueError
        if a.get("polarity", "auto") not in {"auto", "bright", "dark"}:
            raise ValueError
        if a.get("channel", "auto") not in {"auto", "r", "g", "b", "gray"}:
            raise ValueError
        if a.get("engine", "classical") not in {"classical", "cellpose"}:
            raise ValueError
    except (ValueError, OverflowError):
        return jsonify(error="Bad settings."), 400
    try:
        raw = request.get_data(cache=False)
        if not raw:
            return jsonify(error="Choose an image before analysing."), 400
        g, sat = counter.load(raw, a.get("channel", "auto"))
    except Exception:
        return jsonify(error="Couldn’t read that file. Use PNG, JPG, TIFF, BMP or WebP."), 400
    if not slots.acquire(timeout=10):
        return jsonify(error="The server is busy. Please try again in a moment."), 503
    try:
        engine, note, pts = "classical", "", None
        if a.get("engine") == "cellpose":
            try:
                c, r = counter.cellpose_engine(g)
                pts, info, engine = np.c_[c, np.full(len(c), r)], dict(snr=99.0, coverage=0.0), "cellpose"
            except Exception as e:
                note = f"Cellpose unavailable ({type(e).__name__}); used the classical detector."
        if pts is None:
            pts, info = counter.detect(g, radius, sens, a.get("polarity", "auto"))
        h, w = g.shape
        buf = io.BytesIO()
        Image.fromarray((g * 255).astype(np.uint8)).save(buf, "JPEG", quality=88)
        pr = stats.PRIORS.get(a.get("prior"), JEFFREYS)
        return jsonify(w=w, h=h, engine=engine, note=note, n=len(pts), points=np.round(pts, 1).tolist(),
                       flags=counter.flags(info, len(pts), sat),
                       preview="data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
                       **stats.model(stats.tiles(pts[:, :2], h, w, k), pr))
    except Exception:
        log.exception("analysis failed")
        return jsonify(error="Analysis failed on this image."), 500
    finally:
        slots.release()


@app.post("/api/v1/model")
def remodel():
    d = request.get_json(silent=True)
    d = d if isinstance(d, dict) else {}
    try:
        raw_points = d.get("points", [])
        if not isinstance(raw_points, list):
            raise ValueError
        pts = np.asarray(raw_points, float).reshape(-1, 3)
        w, h, k = float(d["w"]), float(d["h"]), int(d.get("k", 4))
        ok = len(pts) <= 50000 and np.isfinite(pts).all() and 0 < w <= 20000 and 0 < h <= 20000 and 2 <= k <= 8
    except (KeyError, TypeError, ValueError):
        ok = False
    if not ok:
        return jsonify(error="Bad request."), 400
    pts = pts[(pts[:, 0] >= 0) & (pts[:, 0] < w) & (pts[:, 1] >= 0) & (pts[:, 1] < h)]
    pr = stats.PRIORS.get(str(d.get("prior")), JEFFREYS)
    return jsonify(n=len(pts), **stats.model(stats.tiles(pts[:, :2], h, w, k), pr))


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8000)), threaded=True)
