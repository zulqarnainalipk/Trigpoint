// TrigPoint imagery layer: backends, sources, views, stretch, gap fill, statistics, candidate areas,
// the file check, provenance and datasheet. Loaded after review.js and before app.js.
// Everything shown comes from the server; text is inserted with textContent or escaped.

"use strict";

const DEFAULT_IMAGERY = { backend: "", source: "single", days: 120, q: 20, view: "true_color", stretch: "percentile",
                          fill: "none", kind: "built_up", strict: 90, minpx: 30, clear: false };
const IMG = { views: null, backends: [], controller: null, timer: null, last: null, shown: false, candLayer: null,
              candData: null, blobUrl: null };
const SOURCE_LABEL = { single: "Single scene", median: "Cloudless median", clearsky: "Clear-sky layer" };
const STRICT = [["99", "Very strict (99th percentile)"], ["95", "Strict (95th)"], ["90", "Medium (90th)"], ["80", "Loose (80th)"]];

function ip() {
  if (!prefs.imagery) prefs.imagery = { ...DEFAULT_IMAGERY };
  for (const k of Object.keys(DEFAULT_IMAGERY)) if (!(k in prefs.imagery)) prefs.imagery[k] = DEFAULT_IMAGERY[k];
  return prefs.imagery;
}
function setIp(k, v) { ip()[k] = v; savePrefs(); }

function mk(tag, text, cls, attrs) {
  const n = document.createElement(tag);
  if (text != null) n.textContent = text;
  if (cls) n.className = cls;
  if (attrs) for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

function num(v, d = 2) { return v == null || Number.isNaN(+v) ? "n/a" : (+v).toFixed(d); }
function pct(v, d = 0) { return v == null || Number.isNaN(+v) ? "n/a" : (100 * v).toFixed(d) + "%"; }

// ------------------------------------------------------------------ server data

async function loadImageryData() {
  try { IMG.views = await (await api("/api/views")).json(); } catch (e) { IMG.views = null; }
}

function activeBackend() {
  const p = ip();
  return IMG.backends.find((b) => b.name === p.backend) || null;
}

function renderBackends(list, defaultName) {
  IMG.backends = list || IMG.backends;
  const sel = $("img-backend");
  if (!sel) return;
  const p = ip();
  if (!p.backend || !IMG.backends.some((b) => b.name === p.backend)) p.backend = defaultName || "demo";
  sel.textContent = "";
  for (const b of IMG.backends) {
    const state = b.ready === true ? "ready" : b.ready === false ? "not ready" : "not checked";
    const o = mk("option", `${b.label} (${state})`);
    o.value = b.name;
    if (b.name === p.backend) o.selected = true;
    sel.appendChild(o);
  }
  showBackendStatus();
}

function showBackendStatus() {
  const b = activeBackend();
  const el = $("img-backend-status");
  if (!el) return;
  el.textContent = b ? b.reason : "";
  el.className = "hint-small" + (b && b.ready === false ? " warn-text" : "");
  const badge = $("backend-badge");
  if (badge && b) {
    badge.textContent = "Imagery: " + (b.name === "demo" ? "demo (synthetic)" : b.name === "ee" ? "Earth Engine" : "Planetary Computer");
    badge.className = "badge " + (b.name === "demo" ? "warn" : b.ready === false ? "err" : b.ready ? "ok" : "muted");
    badge.title = b.reason;
  }
  const note = $("img-synth-note");
  if (note) note.hidden = !(b && b.name === "demo");
  updateImagerySummary();
}

async function checkBackends() {
  const btn = $("img-check");
  btn.disabled = true;
  $("img-backend-status").textContent = "Checking the connection…";
  try {
    const j = await (await api("/api/backends?check=1")).json();
    renderBackends(j.backends, j.default);
    announce("Backend check finished. " + ($("img-backend-status").textContent || ""));
  } catch (e) {
    $("img-backend-status").textContent = "The check failed: " + e.message;
  } finally { btn.disabled = false; }
}

function updateImagerySummary() {
  const p = ip(), b = activeBackend();
  const s = $("img-sum");
  if (s) s.textContent = `${b ? (b.name === "demo" ? "Demo" : b.name === "ee" ? "Earth Engine" : "Planetary Computer") : "?"}, ${(SOURCE_LABEL[p.source] || p.source).toLowerCase()}`;
}

// ------------------------------------------------------------------ controls

function renderViewTabs() {
  const box = $("view-tabs");
  if (!box || !IMG.views) return;
  const p = ip();
  box.textContent = "";
  for (const [name, c] of Object.entries(IMG.views.composites)) {
    const b = mk("button", name.replace(/_/g, " "), "view-tab" + (p.view === name ? " active" : ""));
    b.type = "button";
    b.setAttribute("aria-pressed", String(p.view === name));
    b.title = c.description;
    b.addEventListener("click", () => chooseView(name));
    box.appendChild(b);
  }
  const sel = $("img-index");
  if (sel.options.length <= 1) {
    for (const [name, i] of Object.entries(IMG.views.indices)) {
      const o = mk("option", `${name.toUpperCase()}: ${i.description.split(".")[0]}`);
      o.value = name;
      sel.appendChild(o);
    }
  }
  sel.value = IMG.views.indices[p.view] ? p.view : "";
  const hb = $("img-index-help");
  if (hb) hb.dataset.help = IMG.views.indices[p.view] ? "index:" + p.view : "view_index";
  HelpCenter.refreshLabels($("imagery-body"));
}

function chooseView(name) {
  setIp("view", name);
  renderViewTabs();
  announce("View: " + name.replace(/_/g, " "));
  if (IMG.shown) fetchPreview(false);
  else if (mode === "edit") $("preview-status").textContent = "View chosen. Press Fetch image to see it.";
}

function syncImageryUI() {
  const p = ip();
  document.querySelectorAll('input[name="img-source"]').forEach((r) => { r.checked = r.value === p.source; });
  $("img-days").value = p.days;
  $("img-q").value = p.q;
  $("img-q-wrap").hidden = p.source !== "clearsky";
  $("img-days-wrap").hidden = false;
  $("img-stretch").value = p.stretch;
  $("img-fill").value = p.fill;
  $("img-kind").value = p.kind;
  $("img-strict").value = String(p.strict);
  $("img-minpx").value = p.minpx;
  $("img-clear").checked = !!p.clear;
  renderViewTabs();
  updateImagerySummary();
}

function fillStaticOptions() {
  const stretch = $("img-stretch");
  if (!stretch.options.length) {
    for (const [v, t] of [["percentile", "Percentile (default)"], ["log", "Log"], ["sqrt", "Square root"], ["linear", "Linear (fixed range)"]]) {
      const o = mk("option", t); o.value = v; stretch.appendChild(o);
    }
  }
  const fill = $("img-fill");
  if (!fill.options.length) {
    for (const [v, t] of [["none", "None (leave empty pixels black)"], ["mean", "Band mean"], ["nearest", "Nearest scene, then band mean"]]) {
      const o = mk("option", t); o.value = v; fill.appendChild(o);
    }
  }
  const kind = $("img-kind");
  if (!kind.options.length) {
    for (const [v, t] of [["built_up", "Built-up or bare ground"], ["hot", "Hot ground or flare"], ["bare", "Dry bare surface"], ["bright", "Bright surfaces"]]) {
      const o = mk("option", t); o.value = v; kind.appendChild(o);
    }
  }
  const strict = $("img-strict");
  if (!strict.options.length) {
    for (const [v, t] of STRICT) { const o = mk("option", t); o.value = v; strict.appendChild(o); }
  }
}

// ------------------------------------------------------------------ fetching and showing the image

function imageryQuery(extra = "") {
  const p = ip();
  const parts = [`box_km=${editEditor.boxKm}`, `lat=${editEditor.lat}`, `lon=${editEditor.lon}`, `backend=${encodeURIComponent(p.backend)}`,
    `source=${p.source}`, `days=${p.days}`, `q=${p.q}`, `view=${p.view}`, `stretch=${p.stretch}`, `fill=${p.fill}`];
  return parts.join("&") + extra;
}

function setBusy(on, text) {
  $("btn-preview").disabled = on;
  $("img-cancel").hidden = !on;
  $("img-progress").hidden = !on;
  clearInterval(IMG.timer);
  $("img-timer").textContent = "";
  if (on) {
    // the status line is read out once; the counter is only for the eyes, so a screen reader is not interrupted every second
    $("preview-status").textContent = text;
    const t0 = Date.now();
    const tick = () => { $("img-timer").textContent = `${Math.round((Date.now() - t0) / 1000)} s`; };
    tick();
    IMG.timer = setInterval(tick, 1000);
  }
}

function friendlyError(msg) {
  const b = activeBackend();
  let hint = "";
  if (/Earth Engine/i.test(msg)) hint = " Choose Demo or Planetary Computer in the Backend list, or see docs/BACKENDS.md to set up Earth Engine.";
  else if (/not reachable|internet/i.test(msg)) hint = " Check the internet connection, or choose Demo.";
  else if (/No (usable )?Sentinel-2/i.test(msg)) hint = " Try a longer look-back period.";
  return msg + hint;
}

async function fetchPreview(force = true) {
  if (mode !== "edit" || !activeId) return;
  if (IMG.controller) IMG.controller.abort();
  const ctl = new AbortController();
  IMG.controller = ctl;
  const live = force || !IMG.shown;
  setBusy(true, live ? "Getting the image…" : "Drawing…");
  $("preview-status").className = "mono muted";
  $("img-stale").hidden = true;
  try {
    const res = await api(`/api/preview/${encodeURIComponent(activeId)}?${imageryQuery(force ? "&force=1" : "")}`, { signal: ctl.signal });
    const meta = JSON.parse(res.headers.get("X-Preview-Meta") || "{}");
    const blob = await res.blob();
    if (IMG.blobUrl) URL.revokeObjectURL(IMG.blobUrl);
    IMG.blobUrl = URL.createObjectURL(blob);
    const img = $("preview-img");
    img.src = IMG.blobUrl;
    img.hidden = false;
    const p = ip();
    const siteName = (currentSite() || {}).name || activeId;
    img.alt = `${meta.synthetic ? "Synthetic demo image" : "Satellite image"} of ${siteName}: ${p.view.replace(/_/g, " ")} view, ` +
      `${(SOURCE_LABEL[meta.source] || meta.source || "").toLowerCase()}, ${meta.date || "date unknown"}.`;
    $("img-badge").hidden = !meta.synthetic;
    $("img-empty").hidden = true;
    const fillInfo = meta.fill && meta.fill.gap_pixels
      ? ` Empty pixels: ${meta.fill.gap_pixels}` + (meta.fill.method === "none" ? " (left empty)." : meta.fill.method === "mean"
        ? `, filled with the band mean.` : `, ${meta.fill.nearest} from the nearest scene and ${meta.fill.mean} with the band mean.`) : "";
    const scenes = meta.n_scenes > 1 ? `${meta.n_scenes} scenes` : "1 scene";
    $("preview-caption").textContent =
      `${meta.synthetic ? "SYNTHETIC DEMO IMAGE. " : ""}${SOURCE_LABEL[meta.source] || meta.source}, ${meta.date || "?"}, ${scenes}. ` +
      `Cloud ${pct(meta.cloud_share, 0)} of valid pixels, data in ${pct(meta.valid_share, 0)} of the box. ${num(meta.gsd_m, 1)} m per pixel, box ${meta.box_km} km. ` +
      `View ${meta.view.replace(/_/g, " ")}, stretch ${meta.stretch}.${fillInfo}` + (dirty[activeId] ? " Showing the unsaved position." : "");
    $("preview-status").textContent = "";
    IMG.last = { id: activeId, lat: editEditor.lat, lon: editEditor.lon, box: editEditor.boxKm, meta };
    IMG.shown = true;
    announce(`Image ready. ${meta.synthetic ? "Synthetic demo image. " : ""}${(SOURCE_LABEL[meta.source] || "")}, ${meta.date || ""}.`);
  } catch (e) {
    if (e.name === "AbortError") { $("preview-status").textContent = "Cancelled."; return; }
    $("preview-status").textContent = "Could not get the image. " + friendlyError(e.message);
    $("preview-status").className = "mono err-text";
    announce("Could not get the image. " + e.message, true);
  } finally {
    if (IMG.controller === ctl) { setBusy(false); IMG.controller = null; }
  }
}

function cancelFetch() { if (IMG.controller) IMG.controller.abort(); }

function imageryReset() {
  if (IMG.controller) IMG.controller.abort();
  IMG.shown = false;
  IMG.last = null;
  const img = $("preview-img");
  img.hidden = true;
  img.removeAttribute("src");
  $("img-badge").hidden = true;
  $("img-empty").hidden = false;
  $("preview-caption").textContent = "";
  $("preview-status").textContent = "";
  $("img-stale").hidden = true;
  $("img-stats-out").textContent = "";
  $("img-gap-out").textContent = "";
  clearCandidates();
  syncImageryUI();
}

// the picture no longer matches the box on screen
function imagePositionChanged() {
  if (!IMG.shown || !IMG.last || !editEditor) return;
  const moved = Math.abs(editEditor.lat - IMG.last.lat) > 1e-6 || Math.abs(editEditor.lon - IMG.last.lon) > 1e-6 || Math.abs(editEditor.boxKm - IMG.last.box) > 1e-6;
  const s = $("img-stale");
  if (s.hidden === moved) { s.hidden = !moved; if (moved) announce("The box moved. The picture still shows the old position."); }
}

// ------------------------------------------------------------------ statistics

function table(caption, headers, rows) {
  const t = mk("table", null, "stat-table");
  t.appendChild(mk("caption", caption));
  const hr = mk("tr");
  headers.forEach((h) => hr.appendChild(mk("th", h, null, { scope: "col" })));
  const th = mk("thead"); th.appendChild(hr); t.appendChild(th);
  const tb = mk("tbody");
  rows.forEach((r) => {
    const tr = mk("tr");
    r.forEach((c, i) => tr.appendChild(i === 0 ? mk("th", c, null, { scope: "row" }) : mk("td", c)));
    tb.appendChild(tr);
  });
  t.appendChild(tb);
  const wrap = mk("div", null, "table-wrap");
  wrap.appendChild(t);
  return wrap;
}

async function loadStats() {
  if (mode !== "edit" || !activeId) return;
  const out = $("img-stats-out");
  out.textContent = "Calculating…";
  $("img-stats-btn").disabled = true;
  try {
    const j = await (await api(`/api/imagery/${encodeURIComponent(activeId)}/stats?${imageryQuery()}&clear=${ip().clear ? 1 : 0}`)).json();
    out.textContent = "";
    const ul = mk("ul", null, "reading");
    j.reading.forEach((t) => ul.appendChild(mk("li", t)));
    out.appendChild(ul);
    const row = (name, d) => [name, num(d.mean, 3), num(d.std, 3), num(d.skew, 2), num(d.p5, 3), num(d.p50, 3), num(d.p95, 3)];
    const heads = ["", "Mean", "Spread", "Skew", "5th", "Median", "95th"];
    out.appendChild(table("Indices over the " + (ip().clear ? "clear" : "valid") + " pixels", heads, Object.entries(j.indices).map(([k, v]) => row(k.toUpperCase(), v))));
    out.appendChild(table("Reflectance by band (0 to 1)", heads, Object.entries(j.bands).map(([k, v]) => row(k, v))));
    out.appendChild(mk("p", `Pixels used: ${j.pixels_used}. Data in ${pct(j.valid_share)}, clear in ${pct(j.clear_share)}.` + (j.meta.synthetic ? " Synthetic demo image." : ""), "hint-small"));
    announce("Statistics ready.");
  } catch (e) {
    out.textContent = "Could not calculate statistics. " + friendlyError(e.message);
    out.className = "err-text";
    setTimeout(() => { out.className = ""; }, 100);
  } finally { $("img-stats-btn").disabled = false; }
}

async function runGapTest() {
  if (mode !== "edit" || !activeId) return;
  const out = $("img-gap-out");
  out.textContent = "Testing…";
  $("img-gap-btn").disabled = true;
  try {
    const j = await (await api(`/api/imagery/${encodeURIComponent(activeId)}/gapfill_test?${imageryQuery()}`)).json();
    out.textContent = "";
    const rows = [["Band mean", num(j.mean, 4), j.reference_std ? num(j.mean / j.reference_std, 2) : "n/a"]];
    if (j.nearest != null) rows.push(["Nearest scene, then band mean", num(j.nearest, 4), j.reference_std ? num(j.nearest / j.reference_std, 2) : "n/a"]);
    out.appendChild(table(`Error of each fill on ${j.hidden_pixels} hidden pixels (${pct(j.fraction, 1)} of the box)`, ["Method", "Error (reflectance)", "Error against the picture's own spread"], rows));
    out.appendChild(mk("p", j.nearest != null
      ? (j.nearest < j.mean ? "The nearest scene fill is closer to the truth on this picture." : "On this picture the band mean is as good as the nearest scene.")
      : "No second scene was available, so only the band mean was tested.", "hint-small"));
    announce("Gap-fill test finished.");
  } catch (e) {
    out.textContent = "Could not run the test. " + friendlyError(e.message);
  } finally { $("img-gap-btn").disabled = false; }
}

// ------------------------------------------------------------------ candidate areas

function clearCandidates() {
  if (IMG.candLayer) { map.removeLayer(IMG.candLayer); IMG.candLayer = null; }
  IMG.candData = null;
  const o = $("img-cand-out");
  if (o) o.textContent = "";
  const c = $("img-cand-clear");
  if (c) c.hidden = true;
}

function drawCandidates(data, focusRank) {
  if (IMG.candLayer) map.removeLayer(IMG.candLayer);
  IMG.candLayer = L.geoJSON(data.geojson, {
    style: (f) => ({ color: cssVar("--cand") || "#ff4fd8", weight: f.properties.rank === focusRank ? 4 : 2, dashArray: "6 4", fillOpacity: f.properties.rank === focusRank ? 0.28 : 0.1 }),
    onEachFeature: (f, layer) => layer.bindTooltip(`Candidate ${f.properties.rank}`, { permanent: false }),
  }).addTo(map);
}

async function findCandidates() {
  if (mode !== "edit" || !activeId) return;
  const out = $("img-cand-out");
  out.textContent = "Looking…";
  $("img-cand-btn").disabled = true;
  const p = ip();
  try {
    const j = await (await api(`/api/imagery/${encodeURIComponent(activeId)}/candidates?${imageryQuery()}&kind=${p.kind}&percentile=${p.strict}&min_px=${p.minpx}`)).json();
    IMG.candData = j;
    out.textContent = "";
    out.appendChild(mk("p", j.description + `. Threshold ${num(j.threshold, 3)}.` + (j.meta.synthetic ? " Synthetic demo image." : ""), "hint-small"));
    if (!j.regions.length) {
      out.appendChild(mk("p", "No region is large enough. Try Loose, or a smaller minimum size."));
    } else {
      const rows = j.regions.map((r) => [`${r.rank}`, r.area_km2 == null ? `${r.pixels} px` : num(r.area_km2, 3) + " km²",
        r.distance_from_centre_m == null ? `${num(r.distance_from_centre_px, 0)} px` : Math.round(r.distance_from_centre_m) + " m",
        `${num(r.compactness, 2)} / ${num(r.elongation, 1)}`]);
      const wrap = table("Candidate areas, largest first", ["Rank", "Area", "From centre", "Compact / long"], rows);
      out.appendChild(wrap);
      const bar = mk("div", null, "cand-actions");
      j.regions.slice(0, 8).forEach((r) => {
        const b = mk("button", `Show ${r.rank}`, null, { type: "button", "aria-label": `Show candidate ${r.rank} on the map` });
        b.addEventListener("click", () => showCandidate(r));
        bar.appendChild(b);
      });
      out.appendChild(bar);
      out.appendChild(mk("p", "These outlines are an aid for your eyes. They never move the site.", "hint-small"));
      drawCandidates(j, 0);
      $("img-cand-clear").hidden = false;
    }
    announce(`${j.regions.length} candidate area${j.regions.length === 1 ? "" : "s"} found.`);
  } catch (e) {
    out.textContent = "Could not find candidate areas. " + friendlyError(e.message);
  } finally { $("img-cand-btn").disabled = false; }
}

function showCandidate(r) {
  if (!IMG.candData) return;
  drawCandidates(IMG.candData, r.rank);
  if (r.centroid_lonlat) map.flyTo([r.centroid_lonlat[1], r.centroid_lonlat[0]], Math.max(map.getZoom(), 15), { animate: !motionReduced() });
  announce(`Showing candidate ${r.rank} on the map.`);
}

// ------------------------------------------------------------------ file check, provenance, datasheet

async function openValidator() {
  const d = openDialog("validate-dialog");
  const out = $("val-out");
  out.textContent = "Checking…";
  try {
    const j = await (await api("/api/validate")).json();
    out.textContent = "";
    out.appendChild(mk("p", j.ok ? `No errors. ${j.warnings.length} warning${j.warnings.length === 1 ? "" : "s"}.` : `${j.errors.length} error${j.errors.length === 1 ? "" : "s"} to fix.`,
      "val-summary " + (j.ok ? "ok" : "bad"), { role: "status" }));
    const list = (title, items, cls) => {
      if (!items.length) return;
      out.appendChild(mk("h3", title));
      const ul = mk("ul", null, "val-list " + cls);
      items.forEach((t) => ul.appendChild(mk("li", t)));
      out.appendChild(ul);
    };
    list("Errors (the file cannot be used until these are fixed)", j.errors, "bad");
    list("Warnings (advice)", j.warnings, "warn");
    if (j.ok && !j.warnings.length) out.appendChild(mk("p", "The roster follows every rule the tool checks.", "muted"));
    announce(j.ok ? "File check passed." : "File check found errors.");
  } catch (e) { out.textContent = "The check could not run: " + e.message; }
  return d;
}

const ANSWERS_KEY = "site-curator-datasheet-answers";
function loadAnswers() { try { return JSON.parse(localStorage.getItem(ANSWERS_KEY)) || {}; } catch (e) { return {}; } }
function saveAnswers(a) { try { localStorage.setItem(ANSWERS_KEY, JSON.stringify(a)); } catch (e) { /* storage blocked */ } }

async function openDatasheet() {
  openDialog("datasheet-dialog");
  await refreshDatasheet();
}

function collectAnswers() {
  const a = {};
  document.querySelectorAll("#ds-form textarea").forEach((t) => { if (t.value.trim()) a[t.dataset.key] = t.value.trim(); });
  return a;
}

async function refreshDatasheet(rebuildForm = true) {
  const answers = rebuildForm ? loadAnswers() : collectAnswers();
  saveAnswers(answers);
  const j = await (await api("/api/datasheet", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }) })).json();
  IMG.datasheet = j;
  if (rebuildForm) {
    const form = $("ds-form");
    form.textContent = "";
    for (const [key, q] of Object.entries(j.questions)) {
      const wrap = mk("div", null, "ds-q");
      const id = "ds-" + key;
      wrap.appendChild(mk("label", `${q.section}: ${q.question}`, null, { for: id }));
      const t = mk("textarea", null, "full", { id, rows: "2", "data-key": key });
      t.value = answers[key] || "";
      t.addEventListener("input", () => { clearTimeout(IMG.dsTimer); IMG.dsTimer = setTimeout(() => refreshDatasheet(false), 500); });
      wrap.appendChild(t);
      form.appendChild(wrap);
    }
  }
  $("ds-gaps").textContent = j.gaps.remaining ? `${j.gaps.remaining} of ${j.gaps.total} questions are still open. The datasheet marks them [TO COMPLETE].`
    : "All questions are answered.";
  $("ds-preview").textContent = j.markdown;
}

function downloadText(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = mk("a", null, null, { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ------------------------------------------------------------------ wiring

function wireImagery() {
  fillStaticOptions();
  $("img-backend").addEventListener("change", (e) => { setIp("backend", e.target.value); showBackendStatus(); IMG.shown = false; });
  $("img-check").addEventListener("click", checkBackends);
  document.querySelectorAll('input[name="img-source"]').forEach((r) => r.addEventListener("change", () => {
    setIp("source", r.value); syncImageryUI(); IMG.shown = false;
  }));
  $("img-days").addEventListener("change", (e) => { setIp("days", Math.min(1100, Math.max(5, parseInt(e.target.value, 10) || 120))); e.target.value = ip().days; IMG.shown = false; });
  document.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => { setIp("days", +b.dataset.days); $("img-days").value = ip().days; IMG.shown = false; }));
  $("img-q").addEventListener("change", (e) => { setIp("q", Math.min(50, Math.max(1, parseInt(e.target.value, 10) || 20))); e.target.value = ip().q; IMG.shown = false; });
  $("img-index").addEventListener("change", (e) => { if (e.target.value) chooseView(e.target.value); else renderViewTabs(); });
  $("img-stretch").addEventListener("change", (e) => { setIp("stretch", e.target.value); if (IMG.shown) fetchPreview(false); });
  $("img-fill").addEventListener("change", (e) => { setIp("fill", e.target.value); if (IMG.shown) fetchPreview(false); });
  $("btn-preview").addEventListener("click", () => fetchPreview(true));
  $("img-cancel").addEventListener("click", cancelFetch);
  $("img-stats-btn").addEventListener("click", loadStats);
  $("img-clear").addEventListener("change", (e) => setIp("clear", e.target.checked));
  $("img-gap-btn").addEventListener("click", runGapTest);
  $("img-kind").addEventListener("change", (e) => setIp("kind", e.target.value));
  $("img-strict").addEventListener("change", (e) => setIp("strict", +e.target.value));
  $("img-minpx").addEventListener("change", (e) => { setIp("minpx", Math.max(1, parseInt(e.target.value, 10) || 30)); e.target.value = ip().minpx; });
  $("img-cand-btn").addEventListener("click", findCandidates);
  $("img-cand-clear").addEventListener("click", () => { clearCandidates(); announce("Candidate outlines removed from the map."); });
  $("tool-validate").addEventListener("click", () => { toggleToolsMenu(false); openValidator(); });
  $("val-rerun").addEventListener("click", openValidator);
  $("exp-datasheet").addEventListener("click", openDatasheet);
  $("exp-prov").addEventListener("click", (e) => { e.currentTarget.href = `/api/provenance?download=1&comments=${$("exp-comments").checked ? 1 : 0}`; });
  $("ds-download").addEventListener("click", async () => {
    await refreshDatasheet(false);
    downloadText("datasheet.md", IMG.datasheet.markdown, "text/markdown");
    showToast(IMG.datasheet.gaps.remaining ? `Datasheet saved with ${IMG.datasheet.gaps.remaining} open questions.` : "Datasheet saved.", "ok");
  });
  syncImageryUI();
}

function imageryStatus(status) {
  renderBackends(status.backends, status.default_backend);
  syncImageryUI();
}
