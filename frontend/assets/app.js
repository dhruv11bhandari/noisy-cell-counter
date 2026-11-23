"use strict";
const $ = s => document.querySelector(s), items = [], f = x => x >= 100 ? Math.round(x) : x.toFixed(1),
  esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]),
  ids = ["rad", "sen", "k", "pri", "pol", "chn", "eng"], MK = ["D", "p", "lo", "hi", "alo", "ahi", "f", "seq", "gap", "label"];
let mode = "view", T;
try { const s = JSON.parse(localStorage.getItem("ncc") || "{}"); for (const i of ids) if (s[i] != null) $("#" + i).value = s[i]; } catch (e) {}

const qs = () => new URLSearchParams({radius: $("#rad").value, sens: $("#sen").value, k: $("#k").value, prior: $("#pri").value,
  polarity: $("#pol").value, channel: $("#chn").value, engine: $("#eng").value});

async function call(url, opt) {
  const r = await fetch(url, opt);
  let d = {};
  try { d = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error(d.error || "Request failed (" + r.status + ")");
  return d;
}

function spark(s) {
  const [lo, hi] = s, mx = Math.max(...hi), mn = Math.min(...lo), n = lo.length, X = i => 4 + i * 192 / (n - 1 || 1),
    Y = v => 52 - (v - mn) / (mx - mn || 1) * 48, P = a => a.map((v, i) => X(i).toFixed(1) + "," + Y(v).toFixed(1)).join(" ");
  return `<svg viewBox="0 0 200 56" width="100%" height="56" role="img" aria-label="Credible interval narrowing as tiles are added"><polyline points="${P(hi)}" fill="none" stroke="#ff3d9a" stroke-width="1.6"/><polyline points="${P(lo)}" fill="none" stroke="#ff3d9a" stroke-width="1.6"/></svg>`;
}

function paint(it) {
  const d = it.d, c = it.el.querySelector("canvas"), k = it.k;
  c.width = d.w; c.height = d.h;
  const x = c.getContext("2d");
  x.drawImage(it.img, 0, 0);
  x.strokeStyle = "rgba(120,200,255,.3)"; x.lineWidth = 1;
  for (let i = 1; i < k; i++) { x.beginPath(); x.moveTo(i * d.w / k, 0); x.lineTo(i * d.w / k, d.h); x.moveTo(0, i * d.h / k); x.lineTo(d.w, i * d.h / k); x.stroke(); }
  x.strokeStyle = "#ff3d9a"; x.lineWidth = Math.max(1.5, d.w / 500);
  for (const [px, py, r] of d.points) { x.beginPath(); x.arc(px, py, Math.max(2, r), 0, 6.283); x.stroke(); }
}

function panel(it) {
  const d = it.d, k = it.k, od = d.p < .05,
    tr = it.truth != null ? `<div class="kv"><b>Known true count</b>${it.truth}, so the detector is off by ${(Math.abs(d.n - it.truth) / it.truth * 100).toFixed(1)}%</div>` : "",
    fl = (d.flags || []).map(t => `<div class="chip">${esc(t)}</div>`).join(""),
    body = d.D === undefined ? "" : `<div class="kv"><b>90% credible interval for the whole image</b>${f(d.alo)} to ${f(d.ahi)} <i>(plain Poisson: ${f(d.lo)} to ${f(d.hi)})</i></div>
<div class="kv"><b>${k * k} tiles, ${esc(d.engine)} detector</b>mean ${d.tilemean.toFixed(1)} per tile, dispersion D = ${d.D.toFixed(2)}</div>
<div class="v${od ? " w" : ""}">${od ? `Overdispersed (p = ${d.p.toFixed(3)}): tiles vary more than Poisson noise allows, so the interval is widened by √D = ${d.f.toFixed(2)}.` : `Consistent with Poisson noise (p = ${d.p.toFixed(3)}), so the plain interval stands.`}</div>
<div class="v${d.label === "calibrated" ? "" : " w"}">Leave-one-tile-out calibration: average gap ${d.gap.toFixed(2)}, ${esc(d.label)}.</div>
<div class="kv"><b>Interval for the per-tile rate as tiles are added</b>${spark(d.seq)}</div>`;
  it.el.querySelector(".st").innerHTML = `<div class="n">${d.n}<small>cells</small></div>${fl}${tr}${body}`;
  obs(it); sum();
}

function obs(it) {
  const d = it.d, el = it.el.querySelector(".od");
  if (!d) return;
  const v = it.el.querySelector("input").value.split(/[\s,;]+/).map(parseFloat).filter(isFinite);
  if (!v.length) { el.textContent = ""; return; }
  const h = v.reduce((a, b) => a + b) / v.length, g = Math.abs(d.n - h) / ((d.n + h) / 2 || 1) * 100;
  el.innerHTML = `Your mean <b>${f(h)}</b> vs detector <b>${d.n}</b>: they differ by <b>${g.toFixed(1)}%</b> of the consensus` +
    (d.alo === undefined ? "." : `, and your value is ${h >= d.alo && h <= d.ahi ? "inside" : "outside"} the 90% interval.`);
}

async function edit(it, e) {
  if (mode === "view" || !it.d) return;
  const c = e.currentTarget, b = c.getBoundingClientRect(), x = (e.clientX - b.left) * c.width / b.width,
    y = (e.clientY - b.top) * c.height / b.height, P = it.d.points;
  if (mode === "add") {
    const rs = P.map(p => p[2]).sort((a, b) => a - b);
    P.push([+x.toFixed(1), +y.toFixed(1), rs.length ? rs[rs.length >> 1] : 6]);
  } else {
    let bi = -1, bd = 1e9;
    P.forEach((p, i) => { const dd = Math.hypot(p[0] - x, p[1] - y); if (dd < bd) { bd = dd; bi = i; } });
    if (bi < 0 || bd > Math.max(10, P[bi][2] * 1.6)) return;
    P.splice(bi, 1);
  }
  it.d.n = P.length; paint(it);
  const id = it.seq = (it.seq || 0) + 1;
  try {
    const m = await call("/api/v1/model", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({points: P, w: it.d.w, h: it.d.h, k: it.k, prior: $("#pri").value})});
    if (id !== it.seq) return;
    for (const q of MK) delete it.d[q];
    Object.assign(it.d, m); panel(it);
  } catch (err) { it.el.querySelector(".nt").textContent = err.message; }
}

async function run(it) {
  const id = it.seq = (it.seq || 0) + 1;
  it.el.classList.add("busy"); it.k = +$("#k").value;
  it.el.querySelector(".nt").textContent = "Preparing image analysis…";
  try {
    const d = await call("/api/v1/analyze?" + qs(), {method: "POST", body: it.file});
    if (id !== it.seq) return;
    it.d = d; it.el.querySelector(".nt").textContent = d.note || "";
    it.img = new Image(); it.img.onload = () => paint(it); it.img.src = d.preview;
    panel(it);
  } catch (e) {
    if (id === it.seq) { it.el.querySelector(".st").textContent = e.message; it.el.querySelector(".nt").textContent = ""; }
  } finally { if (id === it.seq) it.el.classList.remove("busy"); }
}

function save(name, data) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(data instanceof Blob ? data : new Blob([data], {type: "text/csv"}));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function sum() {
  const ok = items.filter(i => i.d);
  $("#sum").hidden = !items.length;
  $("#sumtxt").textContent = ok.length + (ok.length === 1 ? " image, " : " images, ") + ok.reduce((a, i) => a + i.d.n, 0) + " cells in total";
}

function add(file, truth) {
  if (!file) return;
  if (file.size > 25 * 2 ** 20) { alert(`${file.name || "This image"} is larger than 25 MB.`); return; }
  if (file.type && !file.type.startsWith("image/")) { alert(`${file.name || "This file"} is not an image.`); return; }
  const el = document.createElement("article");
  el.className = "card";
  el.innerHTML = '<div class="vw"><canvas></canvas></div><div class="b"><h3></h3><div class="st">Analysing…</div><div class="nt"></div>' +
    '<label class="ob">Your own manual count(s), optional<input placeholder="e.g. 4, 7, 5, 6"></label><div class="od"></div>' +
    '<div class="act"><button class="ghost sv">Save image</button><button class="ghost rm">Remove</button></div></div>';
  el.querySelector("h3").textContent = file.name || "pasted image";
  $("#out").prepend(el);
  const it = {file, el, d: null, truth, k: 4, img: new Image()};
  items.push(it);
  el.querySelector("input").oninput = () => obs(it);
  el.querySelector("canvas").onclick = e => edit(it, e);
  el.querySelector(".sv").onclick = () => el.querySelector("canvas").toBlob(b => save((file.name || "image").replace(/\.\w+$/, "") + "-counted.png", b));
  el.querySelector(".rm").onclick = () => { items.splice(items.indexOf(it), 1); el.remove(); sum(); };
  sum(); run(it);
}

$("#csv").onclick = () => {
  const cell = v => { v = String(v); return '"' + (/^[=+\-@]/.test(v) ? "'" + v : v).replace(/"/g, '""') + '"'; },
    rows = [["file", "cells", "interval_low", "interval_high", "dispersion", "p_value", "calibration"]];
  for (const i of items) if (i.d) rows.push([i.file.name || "pasted", i.d.n, i.d.alo != null ? i.d.alo.toFixed(1) : "", i.d.ahi != null ? i.d.ahi.toFixed(1) : "",
    i.d.D != null ? i.d.D.toFixed(2) : "", i.d.p != null ? i.d.p.toFixed(3) : "", i.d.label || ""]);
  save("cell-counts.csv", rows.map(r => r.map(cell).join(",")).join("\n"));
};

$("#f").onchange = e => { [...e.target.files].forEach(x => add(x)); e.target.value = ""; };
const dz = $("#drop");
dz.ondragover = e => { e.preventDefault(); dz.classList.add("on"); };
dz.ondragleave = () => dz.classList.remove("on");
dz.ondrop = e => { e.preventDefault(); dz.classList.remove("on"); [...e.dataTransfer.files].forEach(x => add(x)); };
addEventListener("paste", e => { for (const i of e.clipboardData.items) if (i.type.startsWith("image/")) add(i.getAsFile()); });

document.querySelectorAll(".seg button").forEach(b => b.onclick = () => {
  mode = b.dataset.m; document.body.dataset.mode = mode;
  document.querySelectorAll(".seg button").forEach(x => x.setAttribute("aria-pressed", x === b));
});

const lab = {rad: v => $("#rv").textContent = +v ? v + " px" : "auto", sen: v => $("#sv").textContent = (+v).toFixed(2), k: v => $("#kv").textContent = v + " × " + v};
for (const i of ids) {
  const el = $("#" + i);
  if (lab[i]) lab[i](el.value);
  el.oninput = e => {
    if (lab[i]) lab[i](e.target.value);
    try { localStorage.setItem("ncc", JSON.stringify(Object.fromEntries(ids.map(j => [j, $("#" + j).value])))); } catch (x) {}
    clearTimeout(T); T = setTimeout(() => items.forEach(run), 400);
  };
}

call("/api/v1/samples").then(list => {
  for (const s of list) {
    const b = document.createElement("button");
    b.className = "ghost"; b.textContent = "Sample: " + s.title;
    b.onclick = async () => {
      b.disabled = true;
      try {
        const r = await fetch("/samples/" + encodeURIComponent(s.file));
        if (!r.ok) throw new Error("Sample image could not be loaded.");
        add(new File([await r.blob()], s.file, {type: "image/png"}), s.truth);
      } catch (e) { alert(e.message); }
      finally { b.disabled = false; }
    };
    $("#samples").append(b);
  }
}).catch(() => {});
