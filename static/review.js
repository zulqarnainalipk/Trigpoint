// TrigPoint review layer: preferences, review flow, filters, information
// card, map aids, dialogs and keyboard shortcuts. Loaded before app.js; the
// functions here are called from app.js once the page has booted.

"use strict";

const $ = (id) => document.getElementById(id);

// A map-less mode keeps the list, review flow and information card usable when
// the Leaflet CDN cannot be reached (or when the page is opened with ?nomap=1).
let mapMissing = false;
function makeMapStub() {
  const f = function () {};
  const p = new Proxy(f, {
    get: (t, k) => (k === Symbol.toPrimitive ? () => "" : k === "then" ? undefined : p),
    apply: () => p, construct: () => p, set: () => true,
  });
  return p;
}
if (typeof L === "undefined" || /[?&]nomap=1/.test(location.search)) {
  window.L = makeMapStub();
  mapMissing = true;
}

// ---------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------

function esc(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function cssEscape(v) { return (window.CSS && CSS.escape) ? CSS.escape(v) : String(v).replace(/"/g, '\\"'); }
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function isNarrow() { return window.matchMedia("(max-width: 860px)").matches; }
function fmtCoord(c) { return `${c[0].toFixed(5)}, ${c[1].toFixed(5)}`; }
function regionLabel(r) {
  if (!r) return "No region";
  const s = r.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function announce(msg, assertive = false) {
  const el = $(assertive ? "sr-assertive" : "sr-polite");
  if (!el) return;
  el.textContent = "";
  setTimeout(() => { el.textContent = msg; }, 30);
}

function showToast(message, type = "info", ms = 4200, action = null) {
  const el = document.createElement("div");
  el.className = "toast" + (type === "ok" ? " ok" : type === "err" ? " err" : "");
  if (type === "err") el.setAttribute("role", "alert");
  const span = document.createElement("span");
  span.textContent = message;
  el.appendChild(span);
  if (action) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = action.label;
    b.addEventListener("click", () => { el.remove(); action.fn(); });
    el.appendChild(b);
  }
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), type === "err" ? Math.max(ms, 7000) : ms);
}

function showBanner(msg) {
  const b = $("load-banner");
  b.textContent = msg;
  b.hidden = false;
}

// ---------------------------------------------------------------------
// preferences (localStorage, always guarded; falls back to memory)
// ---------------------------------------------------------------------

const PREF_KEY = "site-curator-prefs-v2";
const BLANK_FILTERS = { q: "", role: "", verified: "", region: "", priority: "", ftype: "",
                        setting: "", conf: "", quality: "", sort: "file" };
const DEFAULT_PREFS = {
  theme: "auto", fontScale: 100, basemap: "esri", defaultBox: 3, handle: 20, zoom: "fit",
  snap: true, advance: true, autosave: true, compact: false, motion: "auto",
  overlays: { label: true, ring: false, split: false, pilot: true, others: true, filtered: false, exact: false },
  filters: { ...BLANK_FILTERS }, lastSite: {}, skipped: {}, tourSeen: false, acc: {},
  imagery: null, shortcuts: true, helpButtons: true,       // imagery settings are completed in imagery.js
};

function loadPrefs() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(PREF_KEY)) || {}; } catch (e) { saved = {}; }
  const p = JSON.parse(JSON.stringify(DEFAULT_PREFS));
  for (const k of Object.keys(p)) {
    if (!(k in saved)) continue;
    if (p[k] && typeof p[k] === "object" && !Array.isArray(p[k])) Object.assign(p[k], saved[k]);
    else p[k] = saved[k];
  }
  return p;
}
let prefs = loadPrefs();
function savePrefs() {
  try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch (e) { /* storage blocked: keep going in memory */ }
}
function setPref(k, v) { prefs[k] = v; savePrefs(); }

// A DOM element with id="map" is also a window global before app.js runs, so
// map-dependent work waits for this flag.
let uiReady = false;
function applyTheme() {
  let t = prefs.theme;
  if (t === "auto") {
    t = window.matchMedia("(prefers-contrast: more)").matches ? "hc"
      : window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  document.documentElement.dataset.theme = t;
  if (uiReady) { updateOverlays(); renderPilotLayer(); }
}
function motionReduced() {
  return prefs.motion === "reduce" ||
    (prefs.motion === "auto" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}
function applyMotion() { document.documentElement.dataset.motion = motionReduced() ? "reduce" : "allow"; }
function applyFont() {
  document.documentElement.style.fontSize = prefs.fontScale + "%";
  if (uiReady) setTimeout(() => map.invalidateSize(), 50);
}
function applyHandle() {
  document.documentElement.style.setProperty("--handle", prefs.handle + "px");
  if (uiReady) { editEditor.refreshHandles(); addEditor.refreshHandles(); }
}
function applyHelpButtons() { document.documentElement.dataset.helpButtons = prefs.helpButtons === false ? "off" : "on"; }
// applied immediately so the first paint already uses the saved theme and size
applyTheme(); applyMotion(); applyFont(); applyHelpButtons();
for (const q of ["(prefers-color-scheme: light)", "(prefers-contrast: more)", "(prefers-reduced-motion: reduce)"]) {
  window.matchMedia(q).addEventListener("change", () => { applyTheme(); applyMotion(); });
}

function fileKey() { return (typeof statusInfo !== "undefined" && statusInfo && statusInfo.sites_path) || "file"; }
function skippedSet() { return new Set(prefs.skipped[fileKey()] || []); }
function saveSkipped(set) { prefs.skipped[fileKey()] = [...set]; savePrefs(); }

// ---------------------------------------------------------------------
// review state
// ---------------------------------------------------------------------

let reviewRejected = false;          // rejected flag of the open site as shown in the form
let analysis = null;                 // /api/analysis
let reference = { sites: [], same_file: false, available: false, path: "" };

const STATE_LABEL = { verified: "Kept", rejected: "Rejected", pending: "Pending", skipped: "Skipped" };
const STATE_GLYPH = { verified: "✓", rejected: "✕", pending: "○", skipped: "↷" };

function stateOf(s) { return s.rejected ? "rejected" : (s.verified ? "verified" : "pending"); }
function stateKey(s) {
  const st = stateOf(s);
  return st === "pending" && skippedSet().has(s.id) ? "skipped" : st;
}
function stateLabel(s) { return STATE_LABEL[stateKey(s)]; }
function analysisOf(id) { return analysis && analysis.sites ? analysis.sites[id] : null; }
function priorityOf(s) {
  if (s.priority) return s.priority;
  const a = analysisOf(s.id);
  return a && a.screening && a.screening.priority ? a.screening.priority : "";
}

function candidateMarkerIcon(s) {
  const k = stateKey(s);
  const cls = { verified: "mk-verified", pending: "mk-pending", rejected: "mk-rejected", skipped: "mk-skipped" }[k];
  const dim = k === "rejected" ? " dim" : "";
  return L.divIcon({ className: "map-pin" + dim, iconSize: [18, 18], html: `<i class="mk ${cls}"></i>` });
}

// ---------------------------------------------------------------------
// filters and sorting
// ---------------------------------------------------------------------

function defaultFilters() { return { ...BLANK_FILTERS, ...(prefs.filters || {}), q: "" }; }
function persistFilters() { prefs.filters = { ...filters, q: "" }; savePrefs(); }

function settingTokens(s) { return (s.setting || "").toLowerCase().split(/\s+/).filter(Boolean); }

function filterAndSortSites(all) {
  const q = (filters.q || "").trim().toLowerCase();
  const skipped = skippedSet();
  const index = new Map(all.map((s, i) => [s.id, i]));
  const out = all.filter((s) => {
    if (filters.role && s.role !== filters.role) return false;
    const st = stateOf(s);
    switch (filters.verified) {
      case "1": if (st !== "verified") return false; break;
      case "0": if (s.verified) return false; break;
      case "pend": if (st !== "pending") return false; break;
      case "rej": if (st !== "rejected") return false; break;
      case "skip": if (!(st === "pending" && skipped.has(s.id))) return false; break;
      case "active": if (st === "rejected") return false; break;
    }
    if (filters.region && (s.region || "") !== filters.region) return false;
    if (filters.priority) {
      const p = priorityOf(s);
      if (filters.priority === "none" ? p !== "" : p !== filters.priority) return false;
    }
    if (filters.ftype && (s.facility_type || "") !== filters.ftype) return false;
    if (filters.setting && !settingTokens(s).includes(filters.setting)) return false;
    if (filters.conf && (s.coord_confidence || "") !== filters.conf) return false;
    if (filters.quality) {
      const a = analysisOf(s.id);
      if (filters.quality === "issues" && !(a && (a.worst === "critical" || a.worst === "warning"))) return false;
      if (filters.quality === "critical" && !(a && a.worst === "critical")) return false;
      if (filters.quality === "split" && !(a && a.nearest_pilot_km != null)) return false;
      if (filters.quality === "unmoved" && !(a && !a.moved)) return false;
    }
    if (q) {
      const hay = [s.id, s.name, s.country, s.region, s.facility_type, s.setting, s.notes, s.comment]
        .join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const idx = (s) => index.get(s.id);
  const prio = (s) => ({ A: 0, B: 1, C: 2 }[priorityOf(s)] ?? 3);
  const roleOrder = { train: 0, test: 1, decoy: 2 };
  const cmp = {
    file: (a, b) => idx(a) - idx(b),
    role: (a, b) => (roleOrder[a.role] ?? 9) - (roleOrder[b.role] ?? 9) || a.id.localeCompare(b.id),
    name: (a, b) => (a.name || a.id).localeCompare(b.name || b.id),
    region: (a, b) => (a.region || "").localeCompare(b.region || "") || prio(a) - prio(b) || idx(a) - idx(b),
    priority: (a, b) => prio(a) - prio(b) || idx(a) - idx(b),
    status: (a, b) => ({ pending: 0, skipped: 1, verified: 2, rejected: 3 }[stateKey(a)] -
                       { pending: 0, skipped: 1, verified: 2, rejected: 3 }[stateKey(b)]) || idx(a) - idx(b),
    confidence: (a, b) => ({ low: 0, medium: 1, high: 2 }[a.coord_confidence] ?? 3) -
                          ({ low: 0, medium: 1, high: 2 }[b.coord_confidence] ?? 3) || idx(a) - idx(b),
    pilot: (a, b) => {
      const x = analysisOf(a.id), y = analysisOf(b.id);
      const da = x && x.nearest_pilot_km != null ? x.nearest_pilot_km : 1e9;
      const db = y && y.nearest_pilot_km != null ? y.nearest_pilot_km : 1e9;
      return da - db || idx(a) - idx(b);
    },
  }[filters.sort] || ((a, b) => idx(a) - idx(b));
  return out.sort(cmp);
}

function regionCount(sites) { return new Set(sites.map((s) => s.region || "")).size; }

function countBy(sites, fn) {
  const m = new Map();
  for (const s of sites) for (const v of [].concat(fn(s))) { if (v !== "" && v != null) m.set(v, (m.get(v) || 0) + 1); }
  return m;
}
function fillSelect(id, entries, current, allLabel = "All") {
  const sel = $(id);
  sel.innerHTML = `<option value="">${allLabel}</option>` +
    entries.map(([v, label]) => `<option value="${esc(v)}">${esc(label)}</option>`).join("");
  sel.value = entries.some(([v]) => v === current) ? current : "";
}
function populateFilterOptions() {
  const sites = sitesDoc.sites;
  const byCount = (m) => [...m.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
  fillSelect("f-region-filter", [...countBy(sites, (s) => s.region || "").entries()]
    .sort((a, b) => a[0].localeCompare(b[0])).map(([v, n]) => [v, `${regionLabel(v)} (${n})`]), filters.region);
  const pr = countBy(sites, (s) => priorityOf(s) || "none");
  fillSelect("f-priority-filter", ["A", "B", "C", "none"].filter((p) => pr.has(p))
    .map((p) => [p, `${p === "none" ? "No priority" : "Priority " + p} (${pr.get(p)})`]), filters.priority);
  fillSelect("f-ftype-filter", byCount(countBy(sites, (s) => s.facility_type || ""))
    .map(([v, n]) => [v, `${v.replace(/_/g, " ")} (${n})`]), filters.ftype);
  fillSelect("f-setting-filter", byCount(countBy(sites, settingTokens))
    .map(([v, n]) => [v, `${v} (${n})`]), filters.setting);
  fillSelect("f-conf-filter", ["high", "medium", "low"].map((c) => [c, c])
    .filter(([c]) => sites.some((s) => s.coord_confidence === c)), filters.conf);
  syncFilterUI();
}
const FILTER_CONTROLS = { q: "f-search", role: "f-role-filter", verified: "f-verified-filter",
  region: "f-region-filter", priority: "f-priority-filter", ftype: "f-ftype-filter",
  setting: "f-setting-filter", conf: "f-conf-filter", quality: "f-quality-filter", sort: "f-sort" };
function syncFilterUI() {
  for (const [k, id] of Object.entries(FILTER_CONTROLS)) if ($(id).value !== filters[k]) $(id).value = filters[k];
  updateFilterSummary();
}
function activeFilterCount() {
  return Object.keys(BLANK_FILTERS).filter((k) => k !== "sort" && filters[k]).length;
}
function updateFilterSummary() {
  const n = activeFilterCount();
  $("filter-summary").textContent = n ? `(${n} active)` : "";
  if (n && !$("filters-box").open) $("filters-box").open = true;
}
function clearFilters() {
  filters = { ...BLANK_FILTERS, sort: filters.sort };
  syncFilterUI(); persistFilters(); renderSidebar(); renderAllMarkers();
  announce("Filters cleared.");
}

// ---------------------------------------------------------------------
// sidebar list items, progress, chip
// ---------------------------------------------------------------------

function rovingTargetId(sites) {
  return sites.some((s) => s.id === activeId) ? activeId : (sites[0] && sites[0].id);
}

function siteListItem(s, rovingId) {
  const key = stateKey(s);
  const a = analysisOf(s.id);
  const prio = priorityOf(s);
  const li = document.createElement("li");
  li.className = "site-item" + (s.id === activeId ? " active" : "") + (s.rejected ? " is-rejected" : "");
  const tags = [];
  if (prio) tags.push(`<span class="tag prio-${esc(prio)}" title="Screening priority ${esc(prio)}">${esc(prio)}</span>`);
  if (a && (a.worst === "critical" || a.worst === "warning"))
    tags.push(`<span class="tag issue" title="Has ${esc(a.worst)} quality flags">⚠ ${esc(a.worst)}</span>`);
  if (a && a.nearest_pilot_km != null)
    tags.push(`<span class="tag pilot" title="Nearest pilot site, shares its split">pilot ${Math.round(a.nearest_pilot_km)} km</span>`);
  tags.push(`<span class="tag">${esc(s.role)}</span>`);
  const sr = [STATE_LABEL[key] + ".", prio ? `Priority ${prio}.` : "",
    a && a.worst ? `${a.worst} flag.` : "", a && a.nearest_pilot_km != null ? "Near a pilot site." : ""].join(" ");
  li.innerHTML = `
    <input type="checkbox" class="sel" tabindex="-1" aria-label="Select ${esc(s.name || s.id)} for bulk actions" ${selectedIds.has(s.id) ? "checked" : ""}>
    <button type="button" class="site-btn" data-id="${esc(s.id)}" tabindex="${s.id === rovingId ? 0 : -1}"${s.id === activeId ? ' aria-current="true"' : ""}>
      <span class="glyph-wrap state-${key}" aria-hidden="true"><span class="state-glyph"><span>${STATE_GLYPH[key]}</span></span></span>
      <span class="name">${esc(s.name || s.id)}</span>
      <span class="tags">${tags.join("")}</span>
      <span class="sr-only">${esc(sr)}</span>
    </button>`;
  const btn = li.querySelector(".site-btn"), cb = li.querySelector(".sel");
  cb.addEventListener("change", () => {
    if (cb.checked) selectedIds.add(s.id); else selectedIds.delete(s.id);
    renderBulkBar();
  });
  btn.addEventListener("click", () => {
    selectSite(s.id);
    if (isNarrow()) setSidebarCollapsed(true);
  });
  btn.addEventListener("keydown", (e) => {
    if (e.shiftKey && (e.key === " " || e.key === "Enter")) {
      e.preventDefault(); e.stopPropagation();
      cb.checked = !cb.checked; cb.dispatchEvent(new Event("change"));
      announce(`${s.name || s.id} ${cb.checked ? "selected" : "deselected"} for bulk actions.`);
      return;
    }
    const buttons = [...$("site-list").querySelectorAll(".site-btn")];
    const i = buttons.indexOf(btn);
    let t = null;
    if (e.key === "ArrowDown") t = buttons[Math.min(i + 1, buttons.length - 1)];
    else if (e.key === "ArrowUp") t = buttons[Math.max(i - 1, 0)];
    else if (e.key === "Home") t = buttons[0];
    else if (e.key === "End") t = buttons[buttons.length - 1];
    if (t) {
      e.preventDefault(); e.stopPropagation();
      buttons.forEach((b) => { b.tabIndex = -1; });
      t.tabIndex = 0; t.focus();
    }
  });
  return li;
}

function renderListMeta(sites) {
  $("list-count").textContent = `${sites.length} of ${sitesDoc.sites.length}`;
  updateFilterSummary();
}

function counts() {
  const c = { total: sitesDoc.sites.length, kept: 0, rejected: 0, pending: 0, skipped: 0 };
  const sk = skippedSet();
  for (const s of sitesDoc.sites) {
    const st = stateOf(s);
    if (st === "verified") c.kept++;
    else if (st === "rejected") c.rejected++;
    else { c.pending++; if (sk.has(s.id)) c.skipped++; }
  }
  return c;
}

function renderProgress() {
  if (!sitesDoc) return;
  const c = counts(), reviewed = c.kept + c.rejected;
  const text = `${reviewed} of ${c.total} reviewed: ${c.kept} kept, ${c.rejected} rejected, ${c.pending} pending` +
    (c.skipped ? ` (${c.skipped} skipped)` : "");
  $("progress-text").textContent = text;
  $("rail-left-count").textContent = `${c.pending} pending`;
  const bar = $("progress-bar");
  bar.setAttribute("aria-valuemax", String(c.total));
  bar.setAttribute("aria-valuenow", String(reviewed));
  bar.setAttribute("aria-valuetext", text);
  const pct = (n) => (c.total ? (100 * n) / c.total : 0) + "%";
  bar.querySelector(".seg-kept").style.width = pct(c.kept);
  bar.querySelector(".seg-rejected").style.width = pct(c.rejected);
}

function renderChip() {
  const has = mode === "edit" && activeId && sitesDoc && sitesDocHasId(activeId);
  document.querySelectorAll("[data-review]").forEach((b) => { b.disabled = !has; });
  let cls = "state-chip pending", text = "Select a site";
  if (has) {
    const s = currentSite(), key = stateKey(s);
    const list = filteredSites(), i = list.findIndex((x) => x.id === s.id);
    cls = "state-chip " + key;
    text = `${STATE_GLYPH[key]} ${STATE_LABEL[key]}` + (i >= 0 ? ` · ${i + 1} of ${list.length}` : " · not in this list");
  }
  document.querySelectorAll(".state-chip-live").forEach((chip) => {
    chip.className = cls + " state-chip-live" + (chip.classList.contains("acc-sum") ? " acc-sum" : "");
    chip.textContent = text;
  });
  $("rail-right-name").textContent = has ? (currentSite().name || activeId) : "Details";
  $("q-status").textContent = "";
  syncQuick();
}
const SAVE_TEXT = {
  saved: ["ok", "✓ All changes saved"], dirty: ["warn", "● Unsaved edits (Ctrl+S)"],
  saving: ["muted", "… Saving"], failed: ["err", "✕ Save failed"],
};
function setSaveIndicator(state) {
  const [cls, text] = SAVE_TEXT[state];
  $("save-indicator").className = "badge " + cls;
  $("save-indicator-text").textContent = text;
}

// ---------------------------------------------------------------------
// moving through the list and deciding
// ---------------------------------------------------------------------

function pickNextAfter(id) {
  const list = filteredSites();
  const i = list.findIndex((s) => s.id === id);
  const order = i < 0 ? list : [...list.slice(i + 1), ...list.slice(0, i)];
  const sk = skippedSet();
  return (order.find((s) => stateOf(s) === "pending" && !sk.has(s.id)) ||
          order.find((s) => stateOf(s) === "pending") || {}).id || null;
}

function moveSelection(delta) {
  const list = filteredSites();
  if (!list.length) { announce("The list is empty."); return; }
  const i = list.findIndex((s) => s.id === activeId);
  let n = i < 0 ? (delta > 0 ? 0 : list.length - 1) : i + delta;
  if (n < 0 || n >= list.length) { announce(n < 0 ? "Start of the list." : "End of the list."); return; }
  selectSite(list[n].id);
}

function goNextPending(dir = 1) {
  const list = filteredSites();
  if (!list.length) { announce("The list is empty."); return; }
  const i = list.findIndex((s) => s.id === activeId);
  const sk = skippedSet();
  let order = [];
  for (let k = 1; k <= list.length; k++) order.push(list[(((i < 0 ? (dir > 0 ? -1 : 0) : i) + dir * k) % list.length + list.length) % list.length]);
  const hit = order.find((s) => s.id !== activeId && stateOf(s) === "pending" && !sk.has(s.id)) ||
              order.find((s) => s.id !== activeId && stateOf(s) === "pending");
  if (!hit && !(i >= 0 && stateOf(list[i]) === "pending")) {
    showToast("No unreviewed sites in this list.", "info");
    announce("No unreviewed sites in this list.");
    return;
  }
  if (hit) selectSite(hit.id);
}

async function reviewAction(kind) {
  if (mode !== "edit" || !activeId) {
    announce("Select a site first.");
    showToast("Select a site first. Press N for the next unreviewed one.", "info");
    return;
  }
  const id = activeId, s = currentSite(), name = s.name || id;
  if (kind === "skip") {
    const sk = skippedSet(); sk.add(id); saveSkipped(sk);
    const nxt = pickNextAfter(id);
    renderSidebar(); renderAllMarkers(); renderChip();
    announce(`Skipped ${name}.`);
    if (nxt && nxt !== id) selectSite(nxt);
    else showToast("No other unreviewed sites in this list.", "info");
    return;
  }
  const nxt = kind === "pending" ? null : pickNextAfter(id);
  const ok = await saveActive({ status: kind, quiet: true });
  if (!ok) return;
  const sk = skippedSet(); sk.delete(id); saveSkipped(sk);
  renderSidebar(); renderAllMarkers(); renderChip();
  const c = counts();
  const verb = { keep: "Kept", reject: "Rejected", pending: "Marked as not reviewed:" }[kind];
  const msg = `${verb} ${name}. ${c.pending} pending.`;
  announce(msg);
  showToast(msg, "ok", 6000, { label: "Undo", fn: doUndo });
  if (kind === "pending") return;
  if (nxt && nxt !== id && prefs.advance) selectSite(nxt);
  else if (!nxt) {
    const done = c.pending === 0;
    showToast(done ? `Review complete: ${c.kept} kept, ${c.rejected} rejected. Open Export to download.`
                   : "No more unreviewed sites in this list. Clear a filter to see the rest.", "info", 8000);
    announce(done ? "Review complete." : "No more unreviewed sites in this list.");
  }
}

// ---------------------------------------------------------------------
// reference layer, analysis, neighbours
// ---------------------------------------------------------------------

async function loadReference() {
  try { reference = await (await api("/api/reference")).json(); } catch (e) { /* optional layer */ }
  renderPilotLayer();
}

let analysisTimer = null, analysisBusy = false;
function scheduleAnalysis() {
  clearTimeout(analysisTimer);
  analysisTimer = setTimeout(loadAnalysis, 300);
}
async function loadAnalysis() {
  if (analysisBusy) { scheduleAnalysis(); return; }
  analysisBusy = true;
  try {
    analysis = await (await api("/api/analysis")).json();
    if (sitesDoc) {
      populateFilterOptions();
      renderSidebar();
      if (mode === "edit" && activeId && sitesDocHasId(activeId)) renderInfo();
    }
  } catch (e) { /* the analysis is an aid; the review works without it */ }
  analysisBusy = false;
}

let liveNb = null, nbTimer = null;
function scheduleNeighbors() {
  clearTimeout(nbTimer);
  nbTimer = setTimeout(async () => {
    if (mode !== "edit" || !activeId) return;
    const id = activeId, lat = editEditor.lat, lon = editEditor.lon;
    try {
      const j = await (await api(`/api/neighbors?lat=${lat}&lon=${lon}&exclude=${encodeURIComponent(id)}`)).json();
      if (activeId !== id) return;
      liveNb = { id, data: j };
      renderNeighbors();
      updateOverlays();
    } catch (e) { /* keep the saved-position list */ }
  }, 220);
}

// ---------------------------------------------------------------------
// information card
// ---------------------------------------------------------------------

function median(xs) {
  const a = [...xs].sort((x, y) => x - y);
  if (!a.length) return null;
  const m = a.length >> 1;
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}
function typicalBox(s) {
  if (!s.facility_type) return null;
  const same = sitesDoc.sites.filter((x) => x.id !== s.id && !x.rejected && x.facility_type === s.facility_type);
  const ver = same.filter((x) => x.verified);
  const pool = ver.length >= 3 ? ver : same;
  if (pool.length < 3) return null;
  const km = Math.round(median(pool.map((x) => x.box_km)) * 4) / 4;
  return { km, n: pool.length, basis: pool === ver ? "verified sites" : "sites in this file" };
}

function mapLinks(lat, lon) {
  const la = lat.toFixed(6), lo = lon.toFixed(6);
  return [
    ["OpenStreetMap", `https://www.openstreetmap.org/?mlat=${la}&mlon=${lo}#map=15/${la}/${lo}`],
    ["Google Maps", `https://www.google.com/maps/search/?api=1&query=${la},${lo}`],
    ["Google Earth", `https://earth.google.com/web/@${la},${lo},0a,6000d,35y,0h,0t,0r`],
  ];
}

const VERDICT = {
  land: (v) => v >= 80 ? "good" : v >= 60 ? "ok" : v >= 30 ? "part water" : "mostly water",
  clear: (v) => v >= 40 ? "good" : v >= 25 ? "ok" : "few clear scenes",
  no2: (v) => v >= 4 ? "visible signal" : "weak",
  co: (v) => v >= 1 ? "visible signal" : "weak",
  fire: (v) => v >= 5 ? "frequent" : "few",
};

function screeningHtml(sc) {
  if (!sc || Object.keys(sc).filter((k) => k !== "flags").length === 0) {
    return `<p class="muted">No screening numbers in this site's notes.</p>`;
  }
  const row = (label, val, verdict) => `<tr><th scope="row">${label}</th><td>${val}</td><td>${verdict || ""}</td></tr>`;
  const num = (v, d = 1) => (v == null ? "n/a" : (+v).toFixed(d));
  let h = `<table class="metric-table"><thead class="sr-only"><tr><th>Measure</th><th>Value</th><th>Reading</th></tr></thead><tbody>`;
  if (sc.land_pct != null) h += row("Land share of 10 km window", `${num(sc.land_pct, 0)}%`, VERDICT.land(sc.land_pct));
  if (sc.s2_all != null) h += row("Clear Sentinel-2 scenes", `${sc.s2_clear} of ${sc.s2_all}` + (sc.clear_pct != null ? ` (${num(sc.clear_pct, 0)}%)` : ""),
                                 sc.clear_pct != null ? VERDICT.clear(sc.clear_pct) : "");
  if ("no2_contrast" in sc) h += row("NO2 contrast", sc.no2_contrast == null ? "n/a" : `${num(sc.no2_contrast)} µmol/m²`, sc.no2_contrast == null ? "" : VERDICT.no2(sc.no2_contrast));
  if ("co_contrast" in sc) h += row("CO contrast", sc.co_contrast == null ? "n/a" : `${num(sc.co_contrast, 2)} mmol/m²`, sc.co_contrast == null ? "" : VERDICT.co(sc.co_contrast));
  if ("fire_days" in sc) h += row("Fire detection days", sc.fire_days == null ? "n/a" : num(sc.fire_days, 0), sc.fire_days == null ? "" : VERDICT.fire(sc.fire_days));
  h += `</tbody></table>`;
  if (sc.flags && sc.flags.length) h += `<ul>${sc.flags.map((f) => `<li><span class="sev warning">flag</span>${esc(f)}</li>`).join("")}</ul>`;
  return h;
}

function neighborsHtml(data, s) {
  if (!data) return `<p class="muted">Checking neighbours…</p>`;
  const nbs = data.neighbors || [];
  let h = "";
  if (data.conflict) {
    h += `<div class="callout critical">⚠ Pilot sites within ${data.radius_km} km are in both splits (${esc(data.pilot_roles.join(" and "))}), so no single split fits this position.</div>`;
  } else if (data.required_role) {
    h += `<div class="callout info">This site must take the <b>${esc(data.required_role)}</b> split, shared with the pilot sites below.` +
      (s.role !== data.required_role ? ` Its role is ${esc(s.role)}. <button type="button" data-act="set-role" data-role="${esc(data.required_role)}">Set role to ${esc(data.required_role)}</button>` : ` Its role already matches.`) + `</div>`;
  }
  if (!nbs.length) return h + `<p class="muted">No pilot site or other candidate within ${data.radius_km} km.</p>`;
  h += `<ul>` + nbs.map((n) => `<li><div class="nb-row">
      <button type="button" class="link-btn" data-act="${n.source === "pilot" ? "goto-pilot" : "open-site"}" data-id="${esc(n.id)}" data-lat="${n.center[0]}" data-lon="${n.center[1]}">${esc(n.name)}</button>
      <span class="tag ${n.source === "pilot" ? "pilot" : ""}">${n.source === "pilot" ? "pilot, " + esc(n.role) : "candidate"}</span>
      <span class="dist">${n.distance_km} km</span></div>
      <div class="nb-cons">${esc(n.consequence)}</div></li>`).join("") + `</ul>`;
  return h;
}

// Collapsible section: state is remembered per key in the preferences.
const ACC_HELP = { "r-links": "box_size", "r-screening": "screening", "r-quality": "quality_flags", "r-neighbors": "neighbours" };
function accHtml(key, title, summary, body, defOpen = false) {
  const open = prefs.acc[key] !== undefined ? prefs.acc[key] : defOpen;
  const help = ACC_HELP[key] ? helpBtnHtml(ACC_HELP[key]) : "";
  return `<details class="acc card" data-acc="${key}"${open ? " open" : ""}>` +
    `<summary><span class="acc-title">${title}</span>${help} <span class="acc-sum">${summary}</span></summary>` +
    `<div class="acc-body">${body}</div></details>`;
}

function initAccordions(root = document) {
  root.querySelectorAll("details[data-acc]").forEach((d) => {
    const saved = prefs.acc[d.dataset.acc];
    if (saved !== undefined && d.open !== !!saved) d.open = !!saved;
  });
}
function onAccToggle(e) {
  const d = e.target;
  if (d && d.matches && d.matches("details[data-acc]")) { prefs.acc[d.dataset.acc] = d.open; savePrefs(); }
}
// Expand or collapse every section inside a bar: if any is closed, open all.
function toggleAllAcc(containerId, btnId) {
  const list = [...$(containerId).querySelectorAll("details[data-acc]")];
  if (!list.length) return;
  const open = list.some((d) => !d.open);
  list.forEach((d) => { d.open = open; prefs.acc[d.dataset.acc] = open; });
  savePrefs();
  $(btnId).dataset.state = open ? "open" : "closed";
  announce(open ? "All sections expanded." : "All sections collapsed.");
}

function neighborSummary(data) {
  if (!data) return "checking";
  const n = (data.neighbors || []).length;
  if (data.conflict) return `${n} nearby, split conflict`;
  if (data.required_role) return `${n} nearby, ${esc(data.required_role)} split`;
  return n ? `${n} nearby` : "none nearby";
}

function currentNeighborData() {
  const a = analysisOf(activeId);
  return liveNb && liveNb.id === activeId ? liveNb.data
    : (a ? { radius_km: analysis.radius_km, neighbors: a.neighbors, conflict: a.split_conflict,
             required_role: a.required_role,
             pilot_roles: [...new Set(a.neighbors.filter((n) => n.source === "pilot").map((n) => n.role))] } : null);
}

function renderNeighbors() {
  const el = $("info-nb");
  if (!el || mode !== "edit") return;
  const data = currentNeighborData();
  el.innerHTML = neighborsHtml(data, currentSite());
  const sum = $("nb-sum");
  if (sum) sum.textContent = neighborSummary(data);
}

let infoTimer = null;
function scheduleInfoRender() { clearTimeout(infoTimer); infoTimer = setTimeout(renderInfo, 150); }

function renderInfo() {
  const card = $("info-card");
  if (mode !== "edit" || !activeId || !sitesDocHasId(activeId)) { card.innerHTML = ""; return; }
  const s = currentSite(), a = analysisOf(s.id);
  const lat = editEditor.lat, lon = editEditor.lon;
  const orig = s.original_center;
  let moved = "";
  if (orig) {
    const d = haversineKm(orig, [lat, lon]);
    moved = d < 0.001 ? "at the original position" : `${d < 1 ? Math.round(d * 1000) + " m" : d.toFixed(2) + " km"} from the original`;
  }
  const prio = priorityOf(s);
  const typ = typicalBox(s);
  const q = a ? a.quality.filter((f) => f.code !== "not_verified") : [];
  const worst = q.some((f) => f.severity === "critical") ? "critical" : q.some((f) => f.severity === "warning") ? "warning" : "";
  const sc = a ? a.screening : null;

  const facility = `<dl>
    <dt>Type</dt><dd>${esc((s.facility_type || "unknown").replace(/_/g, " "))}</dd>
    <dt>Region</dt><dd>${esc(regionLabel(s.region))}${s.country ? " (" + esc(s.country) + ")" : ""}</dd>
    <dt>Setting</dt><dd>${esc(s.setting || "unknown")}</dd>
    <dt>Coordinates</dt><dd>${esc(s.coord_confidence || "unknown")} confidence</dd>
    <dt>Priority</dt><dd>${prio ? `<span class="tag prio-${esc(prio)}">${esc(prio)}</span> ` +
      ({ A: "good land share, clear scenes and a signal", B: "usable with some limits", C: "weak for one or more reasons" }[prio] || "") : "not screened"}</dd></dl>`;
  const facSum = `${prio ? `<span class="tag prio-${esc(prio)}">Priority ${esc(prio)}</span> ` : ""}${esc((s.facility_type || "").replace(/_/g, " "))}`;

  let links = `<dl><dt>Current</dt><dd class="mono">${esc(lat.toFixed(6))}, ${esc(lon.toFixed(6))}</dd>
    <dt>Original</dt><dd class="mono">${orig ? esc(fmtCoord(orig)) + " (" + esc(moved) + ")" : "not moved yet"}</dd></dl>
    <div class="ext-links">${mapLinks(lat, lon).map(([n, u]) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${n}</a>`).join("")}
    <button type="button" class="link-btn" data-act="copy-coords">Copy coordinates</button>
    ${orig ? `<button type="button" class="link-btn" data-act="reset-orig">Reset to original</button>` : ""}</div>`;
  if (typ) links += `<p>Typical box for ${esc(s.facility_type.replace(/_/g, " "))}: <b>${typ.km} km</b> (median of ${typ.n} ${typ.basis}).
    <button type="button" data-act="apply-typical" data-km="${typ.km}">Apply ${typ.km} km (T)</button></p>`;

  const scSum = sc && sc.land_pct != null ? `land ${Math.round(sc.land_pct)}%` + (sc.clear_pct != null ? `, clear ${Math.round(sc.clear_pct)}%` : "") : "none in notes";
  const qSum = q.length ? `<span class="sev ${worst || "info"}">${q.length} flag${q.length > 1 ? "s" : ""}</span>` : (a ? "no flags" : "checking");
  const qBody = q.length
    ? `<ul>${q.map((f) => `<li><span class="sev ${f.severity}">${f.severity}</span>${esc(f.message)}</li>`).join("")}</ul>`
    : `<p class="muted">${a ? "No flags." : "Checking…"}</p>`;
  const nbData = currentNeighborData();
  const radius = analysis ? analysis.radius_km : 150;

  let h = accHtml("r-facility", "Facility and priority", facSum, facility);
  h += accHtml("r-links", "Position, links and size", moved ? esc(moved) : "map links", links);
  h += accHtml("r-screening", "Screening numbers", scSum, screeningHtml(sc));
  h += accHtml("r-quality", "Quality flags", qSum, qBody, worst === "critical");
  h += accHtml("r-neighbors", `Within ${radius} km: shared split`, `<span id="nb-sum">${neighborSummary(nbData)}</span>`,
    `<div id="info-nb"></div>` + (!reference.same_file && !reference.sites.length
      ? `<p class="hint-small">Pilot roster not found at ${esc(reference.path || "the default path")}, so only candidates are compared.</p>` : ""));
  card.innerHTML = h;
  renderNeighbors();
}

function onInfoClick(e) {
  const b = e.target.closest("[data-act]");
  if (!b || mode !== "edit") return;
  const act = b.dataset.act;
  if (act === "copy-coords") {
    const t = `${editEditor.lat.toFixed(6)}, ${editEditor.lon.toFixed(6)}`;
    (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject())
      .then(() => showToast("Copied " + t, "ok"), () => showToast("Clipboard unavailable", "err"));
  } else if (act === "reset-orig") {
    const o = currentSite().original_center;
    if (o) { editEditor.setBox(o[0], o[1], editEditor.boxKm); map.panTo(o); announce("Centre reset to the original position. Save to keep it."); }
  } else if (act === "apply-typical") {
    editEditor.setBox(editEditor.lat, editEditor.lon, parseFloat(b.dataset.km));
    announce(`Box set to ${b.dataset.km} kilometres.`);
  } else if (act === "set-role") {
    patchRole(b.dataset.role);
  } else if (act === "open-site") {
    selectSite(b.dataset.id);
  } else if (act === "goto-pilot") {
    map.flyTo([+b.dataset.lat, +b.dataset.lon], Math.max(map.getZoom(), 11), { animate: !motionReduced() });
    announce("Map moved to pilot site " + b.textContent);
  }
}

async function patchRole(role) {
  if (mode !== "edit") return;
  const id = activeId;
  try {
    const j = await (await api(`/api/sites/${id}`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }) })).json();
    Object.assign(currentSite(), j.site);
    renderSidebar(); refreshWarnings(); showToast(`Role of ${id} set to ${role}.`, "ok", 5000, { label: "Undo", fn: doUndo });
  } catch (err) { showToast("Could not set role: " + err.message, "err"); }
}

function stepBox(dir) {
  if (mode !== "edit") return;
  const cur = editEditor.boxKm;
  const next = dir > 0 ? BOX_PRESETS.find((p) => p > cur + 0.01) : [...BOX_PRESETS].reverse().find((p) => p < cur - 0.01);
  if (next == null) { announce(dir > 0 ? "Already the largest preset." : "Already the smallest preset."); return; }
  editEditor.setBox(editEditor.lat, editEditor.lon, next);
  announce(`Box ${next} kilometres.`);
}

// ---------------------------------------------------------------------
// map aids: overlays, pilot layer, go to coordinates
// ---------------------------------------------------------------------

let ovLayer = null, pilotLayer = null, gotoLayer = null, gotoPoint = null;
function ensureLayers() {
  if (ovLayer || !map) return;
  ovLayer = L.layerGroup().addTo(map);
  pilotLayer = L.layerGroup().addTo(map);
  gotoLayer = L.layerGroup().addTo(map);
}

function updateOverlays() {
  ensureLayers();
  if (!ovLayer) return;
  ovLayer.clearLayers();
  if (mode !== "edit" || !statusInfo) return;
  const lat = editEditor.lat, lon = editEditor.lon, o = prefs.overlays;
  const base = { fill: false, interactive: false };
  if (o.label) {
    L.rectangle(rectBounds(lat, lon, statusInfo.label_box_km),
      { ...base, color: cssVar("--ov-label"), weight: 2, dashArray: "8 5" }).addTo(ovLayer);
  }
  if (o.ring) {
    for (const km of [statusInfo.bg_inner_km, statusInfo.bg_outer_km])
      L.circle([lat, lon], { ...base, radius: km * 1000, color: cssVar("--ov-ring"), weight: 2, dashArray: "3 7" }).addTo(ovLayer);
  }
  if (o.split) {
    L.circle([lat, lon], { ...base, radius: (statusInfo.split_radius_km || 150) * 1000,
      color: cssVar("--ov-split"), weight: 2, dashArray: "1 8" }).addTo(ovLayer);
    const nb = liveNb && liveNb.id === activeId ? liveNb.data.neighbors : ((analysisOf(activeId) || {}).neighbors || []);
    for (const n of nb) {
      L.polyline([[lat, lon], n.center], { ...base, color: cssVar(n.source === "pilot" ? "--pilot" : "--ov-split"),
        weight: 1, opacity: 0.8 }).addTo(ovLayer);
    }
  }
}

function renderPilotLayer() {
  ensureLayers();
  if (!pilotLayer) return;
  pilotLayer.clearLayers();
  if (!prefs.overlays.pilot) return;
  for (const p of reference.sites) {
    const icon = L.divIcon({ className: "map-pin", iconSize: [20, 20], html: `<i class="mk mk-pilot"></i>` });
    const m = L.marker(p.center, { icon, keyboard: false, zIndexOffset: -100 });
    m.bindTooltip(`Pilot site (read only): ${p.name || p.id}. Split: ${p.role}. Box ${p.box_km} km.`, { direction: "top" });
    pilotLayer.addLayer(m);
    if (p.box_km) L.rectangle(rectBounds(p.center[0], p.center[1], p.box_km),
      { color: cssVar("--pilot"), weight: 1, fillOpacity: 0.08, interactive: false }).addTo(pilotLayer);
  }
}

function onEditorMoved() {
  syncQuick();
  if (typeof imagePositionChanged === "function") imagePositionChanged();
  updateOverlays();
  scheduleNeighbors();
  scheduleInfoRender();
}

function flyToSite(s) {
  const mode_ = prefs.zoom, animate = !motionReduced();
  if (mode_ === "keep") map.panTo(s.center, { animate });
  else if (mode_ === "14") map.setView(s.center, 14, { animate });
  else if (animate) map.flyToBounds(rectBounds(s.center[0], s.center[1], s.box_km), { padding: [50, 50], maxZoom: 17 });
  else map.fitBounds(rectBounds(s.center[0], s.center[1], s.box_km), { padding: [50, 50], maxZoom: 17, animate: false });
}

function onSiteSelected(s) {
  prefs.lastSite[fileKey()] = s.id; savePrefs();
  lastQBox = null;
  liveNb = null;
  renderChip();
  updateOverlays();
  renderInfo();
  scheduleNeighbors();
  if ($("f-exact-grid").checked) loadExactGrid(editEditor.lat, editEditor.lon, editEditor.boxKm);
  const active = $("site-list").querySelector(".site-item.active");
  if (active) active.scrollIntoView({ block: "nearest", behavior: "auto" });
  $("goto-move").hidden = true;
  document.title = `${s.name || s.id} - TrigPoint`;
  const list = filteredSites(), i = list.findIndex((x) => x.id === s.id);
  announce(`${s.name || s.id}. ${stateLabel(s)}.` + (i >= 0 ? ` ${i + 1} of ${list.length}.` : ""));
}
function onSiteDeselected() {
  closeQuick(false);
  liveNb = null; renderChip(); updateOverlays(); $("info-card").innerHTML = "";
  $("goto-move").hidden = true; document.title = "TrigPoint";
}
function onSiteSaved() { renderChip(); renderInfo(); updateOverlays(); }

function toggleBasemap() {
  const next = currentBasemap === "esri" ? "osm" : "esri";
  map.removeLayer(basemaps[currentBasemap]);
  basemaps[next].addTo(map);
  currentBasemap = next;
  setPref("basemap", next);
  announce(next === "osm" ? "OpenStreetMap basemap." : "Satellite basemap.");
}

function parseCoordInput(text) {
  if (!text) return null;
  const t = String(text).trim();
  const ok = (a, b) => (Number.isFinite(a) && Number.isFinite(b) && Math.abs(a) <= 90 && Math.abs(b) <= 180) ? [a, b] : null;
  const N = "(-?\\d+(?:\\.\\d+)?)";
  let m;
  if ((m = t.match(new RegExp(`!3d${N}!4d${N}`)))) return ok(+m[1], +m[2]);
  if ((m = t.match(new RegExp(`@${N},${N}`)))) return ok(+m[1], +m[2]);
  if ((m = t.match(new RegExp(`[?&](?:q|ll|query|center)=${N}(?:,|%2C)${N}`, "i")))) return ok(+m[1], +m[2]);
  if ((m = t.match(new RegExp(`mlat=${N}.*?mlon=${N}`)))) return ok(+m[1], +m[2]);
  if ((m = t.match(new RegExp(`#map=\\d+/${N}/${N}`)))) return ok(+m[1], +m[2]);
  // decimal degrees, degrees with N/S/E/W letters, or degrees minutes seconds
  const re = /([NSEW])?\s*(-?\d+(?:\.\d+)?)\s*(?:°|º|d)?\s*(?:(\d+(?:\.\d+)?)\s*['′]\s*)?(?:(\d+(?:\.\d+)?)\s*(?:"|″|'')\s*)?([NSEW])?/gi;
  const tok = [];
  for (const x of t.matchAll(re)) {
    if (!x[2]) continue;
    const letter = (x[1] || x[5] || "").toUpperCase();
    let v = Math.abs(+x[2]) + (x[3] ? +x[3] / 60 : 0) + (x[4] ? +x[4] / 3600 : 0);
    if (+x[2] < 0 || letter === "S" || letter === "W") v = -v;
    tok.push({ v, letter });
  }
  if (tok.length !== 2) return null;
  let [a, b] = tok;
  if (a.letter === "E" || a.letter === "W" || b.letter === "N" || b.letter === "S") [a, b] = [b, a];
  return ok(a.v, b.v);
}

function gotoCoords(lat, lon) {
  ensureLayers();
  gotoPoint = [lat, lon];
  gotoLayer.clearLayers();
  L.marker([lat, lon], { keyboard: false, title: "Jumped-to point" }).addTo(gotoLayer);
  map.flyTo([lat, lon], Math.max(map.getZoom(), 14), { animate: !motionReduced() });
  $("goto-move").hidden = mode !== "edit";
  announce(`Jumped to ${lat.toFixed(5)}, ${lon.toFixed(5)}.`);
}

function onGotoSubmit(e) {
  e.preventDefault();
  const c = parseCoordInput($("goto-input").value);
  if (!c) { showToast("Could not read coordinates. Try 27.05, 49.56 or a Google Maps link.", "err"); return; }
  gotoCoords(c[0], c[1]);
}

// ---------------------------------------------------------------------
// dialogs: help, tour, settings, export, import
// ---------------------------------------------------------------------

function openDialog(id) {
  const d = $(id);
  if (!d.open) d.showModal();
  return d;
}

const TOUR = [
  ["Welcome", "The tool has three columns: the site list on the left, the map in the middle and the details of the open site on the right. For each candidate you check the box over the satellite map, fix its centre and size, then keep or reject it. The progress bar above the map shows how far you are."],
  ["Fold the bars away", "Press [ to fold the site list and ] to fold the details bar, or use the arrow buttons on each bar. A folded bar leaves a slim rail; click it to open the bar again. Drag the edge of a bar to resize it. Press F for focus mode, which hides both bars and extra controls so only the map is left. Press F again to bring them back."],
  ["Work from the keyboard", "Press N to open the next unreviewed site. Drag the pin and corner squares, use the arrow keys to nudge, or press - and + to change the size. Press V to keep, X to reject, S to skip. Moving to another site saves your edits, and Ctrl+Z undoes the last decision."],
  ["Quick edit", "Press E to open the quick edit strip over the map. It holds the essentials: name, role, centre, box size with presets, verified, keep and reject, and your comment. It works even when the details bar is folded. Press Enter to save and Esc to fold it away."],
  ["Sections and information", "Every section in both bars folds with its chevron, and the double arrow button opens or closes them all. The details bar keeps the editing fields open and the long information (screening numbers, quality flags, neighbours within 150 km) collapsed, with a one-line summary on each. Your choices are remembered."],
  ["Look at the imagery", "Open the Imagery section in the details bar. Choose where the pictures come from (Demo works with no account), then Fetch image. Switch between colour views and index views, stretch the brightness, fill empty pixels, read the statistics, and let the tool outline candidate areas. Every picture says where it came from, and demo pictures are marked synthetic."],
  ["Check the split, forecast and coordinates", "Open Tools, then Studies. Split safety finds sites that overlap, near-duplicate pictures and the shift between train and test, and builds one certificate. Forecast predicts how many usable samples each site will give. Coordinates compares your positions with public lists. Placement shows what a misplaced box costs. Each tab has a demo button, so you can try it before using your own files."],
  ["Ask for help anywhere", "Press the small ? beside any control to see what it is, why it matters, how to use it and what it cannot do. The Guide button in the top bar searches every feature. If the shortcut keys get in the way of a screen reader or voice control, switch them off in Settings."],
  ["Finish", "Open Export and pick Kept sites to download the cleaned file. The same dialog makes a provenance record and a datasheet of the roster. Settings has the theme, text size and defaults. Press ? for the shortcut list at any time."],
];let tourStep = 0;
function openTour(step = 0) {
  tourStep = step;
  setPref("tourSeen", true);
  renderTour();
  openDialog("tour-dialog");
}
function renderTour() {
  const [title, body] = TOUR[tourStep];
  $("tour-step").innerHTML = `<h3>${esc(title)}</h3><p>${esc(body)}</p>`;
  $("tour-count").textContent = `${tourStep + 1} of ${TOUR.length}`;
  $("tour-back").disabled = tourStep === 0;
  $("tour-next").textContent = tourStep === TOUR.length - 1 ? "Done" : "Next";
}

function syncSettingsUI() {
  document.querySelectorAll('input[name="pref-theme"]').forEach((r) => { r.checked = r.value === prefs.theme; });
  $("pref-font").value = prefs.fontScale; $("pref-font-out").textContent = prefs.fontScale + "%";
  $("pref-basemap").value = prefs.basemap; $("pref-defbox").value = prefs.defaultBox;
  $("pref-handle").value = String(prefs.handle); $("pref-zoom").value = prefs.zoom;
  $("pref-snap").checked = prefs.snap; $("pref-advance").checked = prefs.advance;
  $("pref-autosave").checked = prefs.autosave; $("pref-compact").checked = prefs.compact;
  $("pref-motion").value = prefs.motion;
  $("pref-shortcuts").checked = prefs.shortcuts !== false;
  $("pref-helpbtn").checked = prefs.helpButtons !== false;
  const lay = loadLayout();
  $("pref-wl").value = lay.leftW || BARS.left.def; $("pref-wl-out").textContent = $("pref-wl").value + " px";
  $("pref-wr").value = lay.rightW || BARS.right.def; $("pref-wr-out").textContent = $("pref-wr").value + " px";
}
function syncOverlayUI() {
  for (const k of ["label", "ring", "split", "pilot", "others", "filtered"]) $("ov-" + k).checked = !!prefs.overlays[k];
}
function setOverlay(k, on) {
  prefs.overlays[k] = on; savePrefs(); syncOverlayUI();
  if (k === "pilot") renderPilotLayer();
  else if (k === "others" || k === "filtered") renderAllMarkers();
  else updateOverlays();
}

function exportUrl() {
  const scope = document.querySelector('input[name="exp-scope"]:checked').value;
  const fmt = document.querySelector('input[name="exp-format"]:checked').value;
  const com = $("exp-comments").checked ? 1 : 0;
  return `/api/sites/export?scope=${scope}&format=${fmt}&comments=${com}`;
}
async function openExport() {
  if (mode === "edit" && dirty[activeId]) await saveActive({ quiet: true });
  const c = counts(), total = sitesDoc.sites.length;
  const ver = sitesDoc.sites.filter((s) => s.verified && !s.rejected).length;
  $("exp-kept-label").textContent = `Kept sites: everything not rejected (${total - c.rejected})`;
  $("exp-verified-label").textContent = `Verified sites only (${ver})`;
  $("exp-all-label").textContent = `Everything in the file (${total})`;
  $("exp-rejected-label").textContent = `Rejected sites only (${c.rejected})`;
  $("exp-download").href = exportUrl();
  if (c.pending) $("exp-note").textContent = `${c.pending} sites are still pending. "Kept" includes them; choose "Verified sites only" to export just the ones you have verified.`;
  openDialog("export-dialog");
}

let importDoc = null;
async function importPreview(apply = false) {
  if (!importDoc) return;
  const policy = $("imp-policy").value;
  const rep = $("imp-report");
  try {
    const r = await (await api("/api/sites/import", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sites: importDoc, policy, apply }) })).json();
    const c = r.counts;
    let h = `<table class="imp-table"><tbody>
      <tr><th scope="row">New sites</th><td>${c.new}</td></tr>
      <tr><th scope="row">Skipped (id exists)</th><td>${c.skipped}</td></tr>
      <tr><th scope="row">Renamed</th><td>${c.renamed}</td></tr>
      <tr><th scope="row">Replaced</th><td>${c.overwritten}</td></tr>
      <tr><th scope="row">Invalid</th><td>${c.invalid}</td></tr>
      <tr><th scope="row">Box size clamped</th><td>${c.clamped}</td></tr>
      <tr><th scope="row">Within 2 km of an existing site</th><td>${c.near}</td></tr></tbody></table>`;
    const list = (title, items, fmt) => items.length ? `<p><b>${title}</b></p><ul>${items.slice(0, 12).map((x) => `<li>${esc(fmt(x))}</li>`).join("")}${items.length > 12 ? `<li>and ${items.length - 12} more</li>` : ""}</ul>` : "";
    h += list("Invalid rows", r.invalid, (x) => `row ${x.index + 1}${x.id ? " (" + x.id + ")" : ""}: ${x.reason}`);
    h += list("Near-duplicate positions", r.near, (x) => `${x.id} is ${x.distance_km} km from ${x.other}`);
    h += list("Renamed", r.renamed, (x) => `${x.from} becomes ${x.to}`);
    if (r.applied) h = `<p class="callout info">Merge applied. A backup of the previous file was saved.</p>` + h;
    rep.innerHTML = h;
    $("imp-apply").disabled = r.applied || !(c.new || c.overwritten);
    if (r.applied) {
      await refreshSitesDoc();
      showToast(`Imported ${c.new + c.overwritten} sites.`, "ok");
    }
  } catch (e) {
    rep.innerHTML = `<p class="callout critical">${esc(e.message)}</p>`;
    $("imp-apply").disabled = true;
  }
}

function openHelp() { openDialog("help-dialog"); }

// ---------------------------------------------------------------------
// shortcuts
// ---------------------------------------------------------------------

function closeFloatingPanels() {
  let closed = false;
  if (quickIsOpen()) { closeQuick(); return true; }
  if (isNarrow() && (barOpen("left") || barOpen("right"))) {
    setBarOpen("left", false, { noSave: true }); setBarOpen("right", false, { noSave: true }); return true;
  }
  if (focusMode) { setFocusMode(false); return true; }
  for (const id of ["tools-menu", "warnings-panel", "backups-panel", "compare-panel"]) {
    const el = $(id);
    if (el.style.display !== "none") {
      el.style.display = "none"; closed = true;
      if (id === "tools-menu") toggleToolsMenu(false);
      if (id === "warnings-panel") $("btn-warnings").setAttribute("aria-expanded", "false");
    }
  }
  return closed;
}

function handleShortcut(e, typing) {
  if (document.querySelector("dialog[open]")) return false;     // dialogs handle their own keys
  if (e.ctrlKey || e.metaKey || e.altKey) return false;
  if (prefs.shortcuts === false) return false;                   // single-key shortcuts can be switched off in Settings
  if (e.key === "?" && !typing) { e.preventDefault(); openHelp(); return true; }
  if (typing) return false;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const done = () => { e.preventDefault(); return true; };
  switch (k) {
    case "j": moveSelection(1); return done();
    case "k": moveSelection(-1); return done();
    case "n": goNextPending(e.shiftKey ? -1 : 1); return done();
    case "v": reviewAction("keep"); return done();
    case "x": reviewAction("reject"); return done();
    case "s": reviewAction("skip"); return done();
    case "u": reviewAction("pending"); return done();
    case "[": toggleBar("left"); return done();
    case "]": toggleBar("right"); return done();
    case "-": stepBox(-1); return done();
    case "+": case "=": stepBox(1); return done();
    case "e": toggleQuick(); return done();
    case "f": setFocusMode(!focusMode); return done();
    case "z": fitViewToBox(); return done();
    case "h": if (mode === "edit") { $("f-exact-grid").click(); } return done();
    case "t": { const b = document.querySelector('[data-act="apply-typical"]'); if (b) b.click(); else announce("No typical size for this facility type."); return done(); }
    case "g": $("goto-input").focus(); return done();
    case "/": $("f-search").focus(); return done();
    case "l": setOverlay("label", !prefs.overlays.label); return done();
    case "b": setOverlay("ring", !prefs.overlays.ring); return done();
    case "r": setOverlay("split", !prefs.overlays.split); return done();
    case "p": setOverlay("pilot", !prefs.overlays.pilot); return done();
    case "o": setOverlay("others", !prefs.overlays.others); return done();
    case "m": toggleBasemap(); return done();
  }
  return false;
}

// ---------------------------------------------------------------------
// wiring
// ---------------------------------------------------------------------

function wireReviewEvents() {
  // filters
  const bind = (key, id, ev) => $(id).addEventListener(ev, () => {
    filters[key] = $(id).value; persistFilters(); renderSidebar(); renderAllMarkers(); updateFilterSummary();
  });
  bind("q", "f-search", "input");
  for (const [k, id] of Object.entries(FILTER_CONTROLS)) if (k !== "q") bind(k, id, "change");
  $("btn-clear-filters").addEventListener("click", clearFilters);

  // review bar
  $("rb-prev").addEventListener("click", () => moveSelection(-1));
  $("rb-next").addEventListener("click", () => moveSelection(1));
  $("rb-next-pending").addEventListener("click", () => goNextPending(1));
  document.querySelectorAll("[data-review]").forEach((b) =>
    b.addEventListener("click", () => reviewAction(b.dataset.review)));
  wireQuickEdit();
  $("btn-focus").addEventListener("click", () => setFocusMode(!focusMode));
  $("focus-exit").addEventListener("click", () => setFocusMode(false));
  $("info-card").addEventListener("toggle", onAccToggle, true);
  document.querySelectorAll("#sidebar-inner details[data-acc], #panel-inner > #panel-scroll details[data-acc], #layers-box").forEach((d) =>
    d.addEventListener("toggle", onAccToggle));
  $("btn-left-acc").addEventListener("click", () => toggleAllAcc("sidebar-inner", "btn-left-acc"));
  $("btn-right-acc").addEventListener("click", () => toggleAllAcc("panel-inner", "btn-right-acc"));

  // layers
  for (const k of ["label", "ring", "split", "pilot", "others", "filtered"])
    $("ov-" + k).addEventListener("change", () => setOverlay(k, $("ov-" + k).checked));
  $("f-exact-grid").addEventListener("change", () => { prefs.overlays.exact = $("f-exact-grid").checked; savePrefs(); });
  $("btn-fit-context").addEventListener("click", () => {
    if (mode !== "edit") { announce("Open a site first."); return; }
    const km = statusInfo.bg_outer_km;
    map.fitBounds(L.circle([editEditor.lat, editEditor.lon], { radius: km * 1000 }).getBounds(), { padding: [20, 20], animate: !motionReduced() });
  });

  // goto
  $("goto-form").addEventListener("submit", onGotoSubmit);
  $("goto-move").addEventListener("click", () => {
    if (mode !== "edit" || !gotoPoint) return;
    editEditor.setBox(gotoPoint[0], gotoPoint[1], editEditor.boxKm);
    gotoLayer.clearLayers(); $("goto-move").hidden = true;
    announce("Box centre moved. Save to keep it.");
  });
  document.addEventListener("paste", (e) => {
    const tag = document.activeElement && document.activeElement.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    const c = parseCoordInput((e.clipboardData || window.clipboardData).getData("text"));
    if (c) { e.preventDefault(); gotoCoords(c[0], c[1]); }
  });

  // info card
  $("info-card").addEventListener("click", onInfoClick);

  // top bar and dialogs
  $("btn-export").addEventListener("click", openExport);
  $("btn-settings").addEventListener("click", () => { syncSettingsUI(); openDialog("settings-dialog"); });
  $("btn-help").addEventListener("click", openHelp);
  $("tool-tour").addEventListener("click", () => { toggleToolsMenu(false); openTour(0); });
  $("help-tour").addEventListener("click", () => { $("help-dialog").close(); openTour(0); });
  $("tool-import").addEventListener("click", () => {
    toggleToolsMenu(false); importDoc = null; $("imp-report").innerHTML = ""; $("imp-file").value = "";
    $("imp-apply").disabled = true; openDialog("import-dialog");
  });
  document.querySelectorAll("dialog [data-close]").forEach((b) =>
    b.addEventListener("click", () => b.closest("dialog").close()));
  $("tour-back").addEventListener("click", () => { if (tourStep > 0) { tourStep--; renderTour(); } });
  $("tour-next").addEventListener("click", () => {
    if (tourStep < TOUR.length - 1) { tourStep++; renderTour(); } else $("tour-dialog").close();
  });
  $("tour-skip").addEventListener("click", () => $("tour-dialog").close());

  // settings
  document.querySelectorAll('input[name="pref-theme"]').forEach((r) =>
    r.addEventListener("change", () => { setPref("theme", r.value); applyTheme(); }));
  const font = (v) => { v = Math.min(160, Math.max(80, v)); setPref("fontScale", v); applyFont(); $("pref-font").value = v; $("pref-font-out").textContent = v + "%"; };
  $("pref-font").addEventListener("input", () => font(+$("pref-font").value));
  $("pref-font-down").addEventListener("click", () => font(prefs.fontScale - 10));
  $("pref-font-up").addEventListener("click", () => font(prefs.fontScale + 10));
  $("pref-basemap").addEventListener("change", () => {
    setPref("basemap", $("pref-basemap").value);
    if ($("pref-basemap").value !== currentBasemap) toggleBasemap();
  });
  $("pref-defbox").addEventListener("change", () => setPref("defaultBox", Math.min(8, Math.max(1, +$("pref-defbox").value || 3))));
  $("pref-handle").addEventListener("change", () => { setPref("handle", +$("pref-handle").value); applyHandle(); });
  $("pref-zoom").addEventListener("change", () => setPref("zoom", $("pref-zoom").value));
  for (const [id, key] of [["pref-snap", "snap"], ["pref-advance", "advance"], ["pref-autosave", "autosave"]])
    $(id).addEventListener("change", () => setPref(key, $(id).checked));
  $("pref-compact").addEventListener("change", () => { setPref("compact", $("pref-compact").checked); renderSidebar(); });
  $("pref-motion").addEventListener("change", () => { setPref("motion", $("pref-motion").value); applyMotion(); });
  for (const [side, id] of [["left", "pref-wl"], ["right", "pref-wr"]])
    $(id).addEventListener("input", () => { const w = setBarWidth(side, +$(id).value); $(id + "-out").textContent = w + " px"; if (map) map.invalidateSize(); });
  $("pref-shortcuts").addEventListener("change", () => { setPref("shortcuts", $("pref-shortcuts").checked); announce($("pref-shortcuts").checked ? "Single-key shortcuts are on." : "Single-key shortcuts are off."); });
  $("pref-helpbtn").addEventListener("change", () => { setPref("helpButtons", $("pref-helpbtn").checked); applyHelpButtons(); });
  $("pref-reset").addEventListener("click", async () => {
    const ok = await confirmDialog("Reset all preferences (theme, text size, filters, overlays, skipped sites) to their defaults?", "Reset");
    if (!ok) return;
    prefs = JSON.parse(JSON.stringify(DEFAULT_PREFS));
    try { localStorage.removeItem(PREF_KEY); localStorage.removeItem(LAYOUT_KEY); } catch (e) { /* ignore */ }
    filters = { ...BLANK_FILTERS };
    applyLayout();
    applyTheme(); applyMotion(); applyFont(); applyHandle(); applyHelpButtons();
    syncSettingsUI(); syncOverlayUI(); syncFilterUI(); syncImageryUI();
    renderSidebar(); renderAllMarkers(); updateOverlays(); renderPilotLayer();
    showToast("Preferences reset.", "ok");
  });

  // export
  document.querySelectorAll('input[name="exp-scope"], input[name="exp-format"], #exp-comments').forEach((el) =>
    el.addEventListener("change", () => { $("exp-download").href = exportUrl(); }));

  // import
  $("imp-file").addEventListener("change", async () => {
    const f = $("imp-file").files[0];
    if (!f) return;
    try {
      const j = JSON.parse(await f.text());
      importDoc = Array.isArray(j) ? j : j.sites;
      if (!Array.isArray(importDoc)) throw new Error("no sites list found in this file");
      await importPreview(false);
    } catch (e) {
      importDoc = null; $("imp-apply").disabled = true;
      $("imp-report").innerHTML = `<p class="callout critical">${esc(e.message)}</p>`;
    }
  });
  $("imp-policy").addEventListener("change", () => importPreview(false));
  $("imp-apply").addEventListener("click", () => importPreview(true));

  window.addEventListener("beforeunload", (e) => {
    if (Object.keys(dirty).length) { e.preventDefault(); e.returnValue = ""; }
  });
}

async function afterSitesLoaded() {
  uiReady = true;
  if (mapMissing) showBanner("The map library could not be loaded (offline?). The list, review buttons, filters and information card still work; map features are off.");
  $("ov-label-text").textContent = `${statusInfo.label_box_km} km label window`;
  $("ov-ring-text").textContent = `${statusInfo.bg_inner_km} to ${statusInfo.bg_outer_km} km background ring`;
  $("ov-split-text").textContent = `${statusInfo.split_radius_km || 150} km split radius`;
  syncOverlayUI(); syncSettingsUI(); applyHandle(); initAccordions();
  populateFilterOptions();
  renderProgress(); renderChip();
  await Promise.all([loadReference(), loadAnalysis()]);
  renderAllMarkers();
  if (!sitesDoc.sites.length) $("empty-text").textContent = "This file has no sites yet. Use + Add site, or Tools, then Import or merge a sites file.";
  const last = prefs.lastSite[fileKey()];
  if (last && sitesDocHasId(last)) selectSite(last);
  if (!prefs.tourSeen) openTour(0);
}

// ---------------------------------------------------------------------
// quick edit strip and focus mode
// ---------------------------------------------------------------------

function quickIsOpen() { return !$("quick-edit").hidden; }

function openQuick(focus = true) {
  if (mode !== "edit" || !activeId) {
    announce("Select a site first.");
    showToast("Select a site first. Press N for the next unreviewed one.", "info");
    return;
  }
  $("quick-edit").hidden = false;
  $("rb-quick").setAttribute("aria-expanded", "true");
  lastQBox = null;
  syncQuick();
  if (focus) $("q-name").focus();
}
function closeQuick(returnFocus = true) {
  if (!quickIsOpen()) return false;
  $("quick-edit").hidden = true;
  $("rb-quick").setAttribute("aria-expanded", "false");
  if (returnFocus) { const t = $("rb-quick"); if (t.offsetParent) t.focus(); }
  return true;
}
function toggleQuick() { if (quickIsOpen()) closeQuick(); else openQuick(); }

let lastQBox = null;
function setUnlessFocused(id, v) { const el = $(id); if (document.activeElement !== el && el.value !== String(v)) el.value = v; }

// Copies the current state of the open site into the strip. The strip has no
// state of its own: it reads and writes the same fields and box editor as the details bar.
function syncQuick() {
  if (!quickIsOpen()) return;
  if (mode !== "edit" || !activeId || !sitesDocHasId(activeId)) { closeQuick(false); return; }
  $("qe-title").textContent = "Quick edit: " + (currentSite().name || activeId);
  setUnlessFocused("q-name", $("f-name").value);
  setUnlessFocused("q-role", $("f-role").value);
  setUnlessFocused("q-lat", editEditor.lat.toFixed(6));
  setUnlessFocused("q-lon", editEditor.lon.toFixed(6));
  setUnlessFocused("q-box", editEditor.boxKm);
  setUnlessFocused("q-comment", $("f-comment").value);
  $("q-verified").checked = $("f-verified").checked;
  if (lastQBox !== editEditor.boxKm) {
    lastQBox = editEditor.boxKm;
    renderPresetButtons($("q-presets"), editEditor.boxKm, pickEditPreset);
  }
}

function wireQuickEdit() {
  $("rb-quick").addEventListener("click", toggleQuick);
  $("btn-quick-open").addEventListener("click", () => openQuick());
  $("rail-quick").addEventListener("click", () => openQuick());
  $("qe-close").addEventListener("click", () => closeQuick());
  const num = (id) => parseFloat($(id).value);
  const move = () => {
    const lat = num("q-lat"), lon = num("q-lon");
    if (Number.isNaN(lat) || Number.isNaN(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return;
    if (Math.abs(lat - editEditor.lat) < 1e-7 && Math.abs(lon - editEditor.lon) < 1e-7) return;   // unchanged: stay clean
    editEditor.setBox(lat, lon, editEditor.boxKm);
  };
  $("q-lat").addEventListener("change", move);
  $("q-lon").addEventListener("change", move);
  $("q-box").addEventListener("change", () => {
    const v = num("q-box");
    if (Number.isNaN(v)) return;
    const nv = Math.min(8, Math.max(1, v));
    if (Math.abs(nv - editEditor.boxKm) < 1e-7) return;
    editEditor.setBox(editEditor.lat, editEditor.lon, nv);
  });
  $("q-name").addEventListener("input", () => { $("f-name").value = $("q-name").value; markDirty(); });
  $("q-role").addEventListener("change", () => { $("f-role").value = $("q-role").value; markDirty(); });
  $("q-comment").addEventListener("input", () => { $("f-comment").value = $("q-comment").value; markDirty(); });
  $("q-verified").addEventListener("change", () => {
    $("f-verified").checked = $("q-verified").checked;
    if ($("q-verified").checked) reviewRejected = false;
    markDirty(); renderChip();
  });
  const save = async () => {
    // commit a field that still has focus before saving
    if (document.activeElement && document.activeElement.dispatchEvent) document.activeElement.dispatchEvent(new Event("change", { bubbles: true }));
    const ok = await saveActive({ quiet: true });
    $("q-status").textContent = ok ? "saved" : "save failed";
    if (ok) announce("Saved.");
  };
  $("q-save").addEventListener("click", save);
  $("quick-edit").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.tagName !== "BUTTON") { e.preventDefault(); save(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closeQuick(); }
  });
}

let focusMode = false;
function setFocusMode(on) {
  focusMode = on;
  document.body.classList.toggle("focus-mode", on);
  $("btn-focus").setAttribute("aria-pressed", String(on));
  $("focus-exit").hidden = !on;
  announce(on ? "Focus mode on. Both bars are hidden. Press F to leave." : "Focus mode off. Bars restored.");
  if (map) setTimeout(() => map.invalidateSize(), 220);
}
