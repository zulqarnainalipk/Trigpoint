// TrigPoint frontend. No build step — vanilla JS + Leaflet.
//
// NOTE on the rectangle math: the interactive box (drag pin to move, drag a
// corner to resize) uses a simple equirectangular offset (good to well
// under 1% error at the <8km box sizes we use). The "exact pixel grid"
// overlay instead calls the backend, which reuses core.py's UTM
// math — so what you see there is byte-for-byte what a real build will
// export. This tool only decides WHERE (center) and HOW BIG (box_km); the
// authoritative pixel geometry always comes from core.py.

const BOX_PRESETS = [1, 1.5, 2, 3, 4, 5, 6, 8];
let sitesDoc = null;
let statusInfo = null;
let activeId = null;
let mode = "idle";           // idle | edit | add
let topView = "map";         // map | gallery | stats
let dirty = {};
let map, exactGridLayer, allMarkersLayer;
let editEditor, addEditor;
let filters = defaultFilters();   // defaultFilters() and the review helpers live in review.js
let selectedIds = new Set();
let measureActive = false, measurePoints = [], measureLayer = null;
let basemaps = null, currentBasemap = "esri";

// ---------------------------------------------------------------------
// small utilities: geometry, api, toast, confirm
// ---------------------------------------------------------------------

function kmToDeg(lat, km) {
  const dLat = km / 111.32;
  const dLon = km / (111.32 * Math.cos(lat * Math.PI / 180));
  return { dLat, dLon };
}

function rectBounds(lat, lon, boxKm) {
  const half = boxKm / 2;
  const { dLat, dLon } = kmToDeg(lat, half);
  return [[lat - dLat, lon - dLon], [lat + dLat, lon + dLon]];
}

function gsdFor(boxKm, chipPx) {
  return (boxKm * 1000) / chipPx;
}

async function api(path, opts) {
  // every request carries a header that pages on other sites cannot send; the server refuses writes without it
  opts = { ...(opts || {}), headers: { "X-Site-Curator": "1", ...((opts || {}).headers || {}) } };
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.error || msg; } catch (e) {}
    throw new Error(msg);
  }
  return res;
}

// showToast(), announce(), $ and the preference store are defined in review.js.

// ---------------------------------------------------------------------
// layout: left site list | map | right details bar
// Both bars fold to a slim rail, resize by dragging (or with the arrow keys
// on the edge handle), and remember their state in localStorage.
// ---------------------------------------------------------------------

const LAYOUT_KEY = "site-curator-layout";

function loadLayout() {
  try { return JSON.parse(localStorage.getItem(LAYOUT_KEY)) || {}; }
  catch (e) { return {}; }
}
function saveLayout(patch) {
  try {
    const cur = loadLayout();
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({ ...cur, ...patch }));
  } catch (e) { /* storage blocked: the layout just will not persist */ }
}

const BARS = {
  left: { el: "sidebar", open: "leftOpen", width: "leftW", cssVar: "--sidebar-w", def: 320, min: 230, max: 560,
          expand: "btn-expand-sidebar", collapse: "btn-collapse-sidebar", handle: "sidebar-resize", name: "site list" },
  right: { el: "panel", open: "rightOpen", width: "rightW", cssVar: "--panel-w", def: 400, min: 300, max: 760,
           expand: "btn-expand-panel", collapse: "btn-collapse-panel", handle: "panel-resize-handle", name: "details bar" },
};

function barOpen(side) { return !$(BARS[side].el).classList.contains("collapsed"); }

function setBarOpen(side, open, opts = {}) {
  const b = BARS[side];
  $(b.el).classList.toggle("collapsed", !open);
  $(b.expand).setAttribute("aria-expanded", String(open));
  $(b.collapse).setAttribute("aria-expanded", String(open));
  if (!isNarrow() && !opts.noSave) saveLayout({ [b.open]: open });
  if (opts.focus) (open ? $(b.collapse) : $(b.expand)).focus();
  const nt = side === "left" ? $("btn-sidebar-toggle") : $("btn-panel-toggle");
  nt.setAttribute("aria-expanded", String(open));
  if (map) setTimeout(() => map.invalidateSize(), 220);
}

function toggleBar(side) {
  const open = !barOpen(side);
  // on a narrow window only one slide-over is open at a time
  if (open && isNarrow()) setBarOpen(side === "left" ? "right" : "left", false, { noSave: true });
  setBarOpen(side, open, { focus: true });
  announce(`${BARS[side].name} ${open ? "opened" : "folded"}.`);
}

function setBarWidth(side, px, save = true) {
  const b = BARS[side];
  const cap = Math.max(b.min, Math.min(b.max, Math.round(window.innerWidth * 0.38)));
  const w = Math.round(Math.min(Math.max(px, b.min), cap));
  document.documentElement.style.setProperty(b.cssVar, w + "px");
  const h = $(b.handle);
  h.setAttribute("aria-valuemin", String(b.min)); h.setAttribute("aria-valuemax", String(cap));
  h.setAttribute("aria-valuenow", String(w));
  if (save) saveLayout({ [b.width]: w });
  return w;
}

// compatibility names used elsewhere
function setSidebarCollapsed(collapsed) { setBarOpen("left", !collapsed); }
function setPanelCollapsed(collapsed) { setBarOpen("right", !collapsed); }

function applyLayout() {
  const layout = loadLayout();
  setBarWidth("left", layout.leftW || BARS.left.def, false);
  setBarWidth("right", layout.rightW || BARS.right.def, false);
  if (isNarrow()) {
    setBarOpen("left", false, { noSave: true });
    setBarOpen("right", false, { noSave: true });
  } else {
    setBarOpen("left", layout.leftOpen !== false, { noSave: true });
    // with no saved choice, a medium window starts with the details bar folded so the map keeps its room
    setBarOpen("right", layout.rightOpen !== undefined ? layout.rightOpen : window.innerWidth >= 1180, { noSave: true });
  }
}

function initResizer(side) {
  const b = BARS[side], handle = $(b.handle);
  let dragging = false;
  const widthFromPointer = (e) => {
    const r = $("main").getBoundingClientRect();
    return side === "left" ? e.clientX - $(b.el).getBoundingClientRect().left
                           : $(b.el).getBoundingClientRect().right - e.clientX;
  };
  handle.addEventListener("pointerdown", (e) => {
    dragging = true; handle.setPointerCapture(e.pointerId); e.preventDefault();
    document.body.classList.add("resizing");
  });
  handle.addEventListener("pointermove", (e) => { if (dragging) setBarWidth(side, widthFromPointer(e), false); });
  const stop = (e) => {
    if (!dragging) return;
    dragging = false; document.body.classList.remove("resizing");
    setBarWidth(side, $(b.el).getBoundingClientRect().width);
  };
  handle.addEventListener("pointerup", stop);
  handle.addEventListener("pointercancel", stop);
  handle.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight" && e.key !== "Home") return;
    e.preventDefault();
    const cur = $(b.el).getBoundingClientRect().width, step = e.shiftKey ? 72 : 24;
    const grow = (side === "left") === (e.key === "ArrowRight");
    setBarWidth(side, e.key === "Home" ? b.def : cur + (grow ? step : -step));
  });
  handle.addEventListener("dblclick", () => setBarWidth(side, b.def));
}

function initLayout() {
  for (const side of ["left", "right"]) {
    const b = BARS[side];
    $(b.expand).addEventListener("click", () => toggleBar(side));
    $(b.collapse).addEventListener("click", () => toggleBar(side));
    initResizer(side);
  }
  $("btn-sidebar-toggle").addEventListener("click", () => toggleBar("left"));
  $("btn-panel-toggle").addEventListener("click", () => toggleBar("right"));
  applyLayout();
  const mq = window.matchMedia("(max-width: 860px)");
  mq.addEventListener("change", applyLayout);
  window.addEventListener("resize", () => {
    for (const side of ["left", "right"]) {
      const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue(BARS[side].cssVar), 10);
      setBarWidth(side, cur || BARS[side].def, false);
    }
  });
  // keep the map sized whenever its box changes (bars folding, resizing, window size)
  if (window.ResizeObserver) new ResizeObserver(() => map && map.invalidateSize()).observe($("map"));
}

// Native <dialog>: focus is trapped inside, Esc cancels and focus returns to
// whatever opened it. "Cancel" has focus first, so Enter never confirms by accident.
function confirmDialog(message, yesLabel = "Yes") {
  return new Promise((resolve) => {
    const dlg = $("confirm-overlay");
    const yesBtn = $("confirm-yes"), noBtn = $("confirm-no");
    $("confirm-msg").textContent = message;
    yesBtn.textContent = yesLabel;
    const opener = document.activeElement;
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      yesBtn.onclick = null; noBtn.onclick = null; dlg.oncancel = null; dlg.onclose = null;
      if (dlg.open) dlg.close();
      if (opener && opener.focus) opener.focus();
      resolve(result);
    };
    yesBtn.onclick = () => finish(true);
    noBtn.onclick = () => finish(false);
    dlg.oncancel = (e) => { e.preventDefault(); finish(false); };
    dlg.onclose = () => finish(false);
    dlg.showModal();
    noBtn.focus();
  });
}

// ---------------------------------------------------------------------
// BoxEditor — the core "fix the site scale" interaction.
//   • drag the center pin  -> move the box (size unchanged)
//   • drag a corner square -> resize the box (center unchanged)
//   • a live "X.XX km" label sits on the box's top edge at all times
// Used identically for editing an existing site and for placing a new one.
// ---------------------------------------------------------------------

class BoxEditor {
  constructor({ color, minKm, maxKm, onChange }) {
    this.color = color;
    this.minKm = minKm;
    this.maxKm = maxKm;
    this.onChange = onChange;
    this.lat = 0; this.lon = 0; this.boxKm = 3;

    this.addMode = color !== "#58a6ff";
    this.rect = L.rectangle([[0, 0], [0, 0]], { color, weight: 3, fillOpacity: 0.12 });
    this.label = L.marker([0, 0], {
      icon: L.divIcon({ className: "box-label", iconSize: [90, 22] }),
      interactive: false, keyboard: false,
    });
    this.centerMarker = L.marker([0, 0], { draggable: true, keyboard: false, title: "Drag to move the box" });
    this.corners = [0, 1, 2, 3].map(() =>
      L.marker([0, 0], { icon: this.handleIcon(), draggable: true, keyboard: false, title: "Drag to resize the box" }));

    this.group = L.layerGroup([this.rect, this.label, this.centerMarker, ...this.corners]);

    this.centerMarker.on("drag", () => {
      const p = this.centerMarker.getLatLng();
      this.setBox(p.lat, p.lng, this.boxKm, { silent: false });
    });
    this.corners.forEach((m) => {
      m.on("drag", () => {
        const p = m.getLatLng();
        const dLatKm = Math.abs(p.lat - this.lat) * 111.32;
        const dLonKm = Math.abs(p.lng - this.lon) * 111.32 * Math.cos(this.lat * Math.PI / 180);
        const halfKm = Math.max(dLatKm, dLonKm, 0.05);
        let newBox = Math.min(Math.max(halfKm * 2, this.minKm), this.maxKm);
        if (prefs.snap) newBox = Math.min(Math.max(Math.round(newBox * 4) / 4, this.minKm), this.maxKm);
        this.setBox(this.lat, this.lon, newBox, { silent: false });
      });
    });
  }

  // Handle size comes from the "drag handle size" setting.
  handleIcon() {
    const px = prefs.handle || 20;
    return L.divIcon({ className: "corner-handle" + (this.addMode ? " add-mode" : ""), iconSize: [px, px] });
  }
  refreshHandles() { this.corners.forEach((m) => m.setIcon(this.handleIcon())); }

  addTo(map) { this.group.addTo(map); return this; }
  remove() { this.group.remove(); }

  setBox(lat, lon, boxKm, opts = {}) {
    this.lat = lat; this.lon = lon; this.boxKm = boxKm;
    const b = rectBounds(lat, lon, boxKm);
    this.rect.setBounds(b);
    const positions = [
      [b[0][0], b[0][1]], [b[0][0], b[1][1]], [b[1][0], b[1][1]], [b[1][0], b[0][1]],
    ];
    this.corners.forEach((m, i) => m.setLatLng(positions[i]));
    this.centerMarker.setLatLng([lat, lon]);
    this.label.setLatLng([b[1][0], lon]);
    this.label.setIcon(L.divIcon({
      className: "box-label" + (this.addMode ? " add-mode" : ""),
      html: `${boxKm.toFixed(2)} km`, iconSize: [90, 22],
    }));
    if (!opts.silent && this.onChange) this.onChange(lat, lon, boxKm);
  }

  bounds() { return rectBounds(this.lat, this.lon, this.boxKm); }
}

function renderPresetButtons(container, current, onPick) {
  container.innerHTML = "";
  for (const km of BOX_PRESETS) {
    const b = document.createElement("button");
    const on = Math.abs(km - current) < 0.01;
    b.className = "preset-btn" + (on ? " active" : "");
    b.textContent = `${km} km`;
    b.setAttribute("aria-pressed", String(on));
    b.onclick = () => onPick(km);
    container.appendChild(b);
  }
}

// ---------------------------------------------------------------------
// map setup
// ---------------------------------------------------------------------

function initMap() {
  map = L.map("map", { zoomControl: true, zoomAnimation: !motionReduced(), fadeAnimation: !motionReduced(),
                       markerZoomAnimation: !motionReduced() }).setView([24, 45], 4);
  const mapEl = map.getContainer();
  mapEl.setAttribute("role", "region");
  mapEl.setAttribute("aria-label", "Satellite map. Use the site list and the information card for keyboard access to sites.");

  const esri = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, attribution: "Tiles &copy; Esri, World Imagery (reference basemap; not the actual Sentinel-2 data)" }
  );
  const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
  });
  basemaps = { esri, osm };
  currentBasemap = prefs.basemap === "osm" ? "osm" : "esri";
  basemaps[currentBasemap].addTo(map);
  L.control.layers({ "Esri World Imagery": esri, "OpenStreetMap": osm }, null,
                   { position: "topright", collapsed: true }).addTo(map);
  map.on("baselayerchange", (e) => {
    currentBasemap = e.layer === osm ? "osm" : "esri";
    setPref("basemap", currentBasemap);
  });
  L.control.scale({ imperial: false, maxWidth: 160 }).addTo(map);

  // Marker clustering degrades gracefully at 19 sites (mostly no-ops) and
  // matters once the roster grows large enough for dots to overlap at low zoom.
  allMarkersLayer = L.markerClusterGroup
    ? L.markerClusterGroup({ maxClusterRadius: 40, spiderfyOnMaxZoom: true })
    : L.layerGroup();
  allMarkersLayer.addTo(map);
  exactGridLayer = L.layerGroup().addTo(map);
  measureLayer = L.layerGroup().addTo(map);

  const bounds = () => [statusInfo ? statusInfo.min_box_km : 1, statusInfo ? statusInfo.max_box_km : 8];

  editEditor = new BoxEditor({
    color: "#58a6ff", minKm: 1, maxKm: 8,
    onChange: (lat, lon, boxKm) => {
      setLatLonFields(lat, lon);
      $("f-box").value = boxKm.toFixed(2);
      $("f-box-range").value = boxKm;
      updateGsdHint(boxKm);
      renderPresetButtons($("panel-body").querySelector(".presets"), boxKm, pickEditPreset);
      if ($("f-exact-grid").checked) loadExactGrid(lat, lon, boxKm);
      markDirty();
      onEditorMoved(lat, lon, boxKm);   // overlays, neighbours (review.js)
    },
  });

  addEditor = new BoxEditor({
    color: "#eda100", minKm: 1, maxKm: 8,
    onChange: (lat, lon, boxKm) => {
      $("a-lat").value = lat.toFixed(6);
      $("a-lon").value = lon.toFixed(6);
      $("a-box").value = boxKm.toFixed(2);
      $("a-box-range").value = boxKm;
      renderPresetButtons($("panel-add").querySelector(".presets"), boxKm, pickAddPreset);
    },
  });

  map.on("click", (e) => {
    if (measureActive) return handleMeasureClick(e.latlng);
    if (mode === "add") {
      // read the field first: it's the source of truth for a box size the
      // user picked (via preset/typing) before placing the box on the map.
      const box = parseFloat($("a-box").value) || addEditor.boxKm || 3.0;
      if (!addEditor.group._map) addEditor.addTo(map);
      addEditor.setBox(e.latlng.lat, e.latlng.lng, box);
    }
  });
}

function pickEditPreset(km) {
  editEditor.setBox(editEditor.lat, editEditor.lon, km);
}
function pickAddPreset(km) {
  if (addEditor.group._map) {
    addEditor.setBox(addEditor.lat, addEditor.lon, km);
  } else {
    // not placed on the map yet — just remember the chosen size, don't
    // populate lat/lon with 0,0 (that would look like a placed site).
    $("a-box").value = km;
    $("a-box-range").value = km;
    renderPresetButtons($("panel-add").querySelector(".presets"), km, pickAddPreset);
  }
}

function updateGsdHint(boxKm) {
  const chipPx = statusInfo ? statusInfo.chip_px : 384;
  const gsd = gsdFor(boxKm, chipPx);
  $("gsd-hint").textContent = `${chipPx}×${chipPx} px  →  ${gsd.toFixed(1)} m/px`;
}

function setLatLonFields(lat, lon) {
  $("f-lat").value = lat.toFixed(6);
  $("f-lon").value = lon.toFixed(6);
}

async function loadExactGrid(lat, lon, boxKm) {
  exactGridLayer.clearLayers();
  try {
    const res = await api(`/api/geom?lat=${lat}&lon=${lon}&box_km=${boxKm}`);
    const j = await res.json();
    L.polygon(j.corners, { color: cssVar("--good"), weight: 2, fill: false, dashArray: "2 4", interactive: false }).addTo(exactGridLayer);
  } catch (e) { /* silent — the interactive box is still shown */ }
}

// ---------------------------------------------------------------------
// all-sites overview markers
// ---------------------------------------------------------------------

// Shape carries the review state (circle kept, diamond pending, cross
// rejected); colour only reinforces it. See candidateMarkerIcon() in review.js.
function renderAllMarkers() {
  allMarkersLayer.clearLayers();
  if (!sitesDoc) return;
  if (!prefs.overlays.others) return;
  const visible = prefs.overlays.filtered ? new Set(filteredSites().map((s) => s.id)) : null;
  for (const s of sitesDoc.sites) {
    if (s.id === activeId && mode === "edit") continue; // shown via the box editor instead
    if (visible && !visible.has(s.id)) continue;
    // A plain L.marker with a divIcon (not L.circleMarker, a vector layer):
    // Leaflet.markercluster only clusters real L.Marker instances.
    const m = L.marker(s.center, { icon: candidateMarkerIcon(s), keyboard: false });
    m.bindTooltip(`${s.name || s.id} (${stateLabel(s)}, ${s.role}, ${s.box_km} km)`, { direction: "top" });
    m.on("click", () => selectSite(s.id));
    allMarkersLayer.addLayer(m);
  }
}

// ---------------------------------------------------------------------
// sidebar / filtering / stats
// ---------------------------------------------------------------------

// The filter and sort rules live in review.js (filterAndSortSites).
function filteredSites() {
  return filterAndSortSites(sitesDoc.sites);
}

function renderSidebar() {
  const list = $("site-list");
  const hadFocus = list.contains(document.activeElement);
  const focusId = hadFocus && document.activeElement.dataset ? document.activeElement.dataset.id : null;
  const prevScroll = list.scrollTop;
  list.innerHTML = "";
  const sites = filteredSites();
  const visibleIds = new Set(sites.map((s) => s.id));
  // drop selections that scrolled out of the current filter's result set
  for (const id of [...selectedIds]) if (!visibleIds.has(id)) selectedIds.delete(id);
  list.classList.toggle("compact", !!prefs.compact);

  if (!sitesDoc.sites.length) {
    list.innerHTML = `<li class="empty-list">This file has no sites yet.<br>` +
      `Use "+ Add site", or Tools, then "Import or merge a sites file".</li>`;
  } else if (sites.length === 0) {
    list.innerHTML = `<li class="empty-list">No sites match these filters.<br>` +
      `<button type="button" id="empty-clear-filters">Clear filters</button></li>`;
    $("empty-clear-filters").addEventListener("click", clearFilters);
  }

  const showGroups = (filters.sort === "file" || filters.sort === "region") && regionCount(sites) > 1;
  let lastRegion = null;
  const roving = rovingTargetId(sites);
  for (const s of sites) {
    if (showGroups && (s.region || "") !== lastRegion) {
      lastRegion = s.region || "";
      const inGroup = sites.filter((x) => (x.region || "") === lastRegion);
      const pend = inGroup.filter((x) => stateOf(x) === "pending").length;
      const head = document.createElement("li");
      head.className = "group-head";
      head.textContent = `${regionLabel(lastRegion)} (${inGroup.length} sites, ${pend} pending)`;
      list.appendChild(head);
    }
    list.appendChild(siteListItem(s, roving));
  }
  renderStats();
  renderBulkBar();
  renderListMeta(sites);
  if (focusId) {
    const again = list.querySelector(`.site-btn[data-id="${cssEscape(focusId)}"]`);
    if (again) again.focus({ preventScroll: true });
  }
  list.scrollTop = prevScroll;
}

function renderBulkBar() {
  const bar = $("bulk-bar");
  const n = selectedIds.size;
  bar.style.display = n > 0 ? "block" : "none";
  if (n === 0) return;
  $("bulk-count").textContent = `${n} selected`;
  const visible = filteredSites().map((s) => s.id);
  $("bulk-select-all").checked = visible.length > 0 && visible.every((id) => selectedIds.has(id));
  $("bulk-compare").disabled = n < 2;
}

async function bulkAction(action, extra = {}) {
  const ids = [...selectedIds];
  if (ids.length === 0) return;
  try {
    const res = await api("/api/sites/bulk", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, ids, ...extra }),
    });
    await res.json();
    const doc = await (await api("/api/sites")).json();
    sitesDoc = doc;
    if (mode === "edit" && activeId && sitesDocHasId(activeId) && ids.includes(activeId)) {
      const cs = currentSite();
      reviewRejected = !!cs.rejected;
      $("f-verified").checked = !!cs.verified && !cs.rejected;
      renderChip();
    }
    renderSidebar();
    renderAllMarkers();
    refreshWarnings();
    showToast(`${action} applied to ${ids.length} site(s). Ctrl+Z undoes it.`, "ok");
  } catch (e) {
    showToast(`Bulk ${action} failed: ` + e.message, "err");
  }
}

async function bulkDeleteSelected() {
  const ids = [...selectedIds];
  if (ids.length === 0) return;
  const ok = await confirmDialog(`Delete ${ids.length} selected site(s)? A backup is kept, but this cannot be undone from the UI (bulk actions are not on the undo stack).`);
  if (!ok) return;
  try {
    await api("/api/sites/bulk_delete", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    sitesDoc.sites = sitesDoc.sites.filter((s) => !selectedIds.has(s.id));
    if (selectedIds.has(activeId)) deselect();
    selectedIds.clear();
    renderSidebar();
    renderAllMarkers();
    refreshWarnings();
    showToast(`Deleted ${ids.length} site(s)`, "ok");
  } catch (e) {
    showToast("Bulk delete failed: " + e.message, "err");
  }
}

function renderStats() {
  const s = sitesDoc.sites;
  const n = (pred) => s.filter(pred).length;
  $("stats-bar").textContent =
    `${s.length} sites · ${n((x) => x.role === "train")} train · ` +
    `${n((x) => x.role === "test")} test · ${n((x) => x.role === "decoy")} decoy · ` +
    `${n((x) => !x.verified)} unverified · ${n((x) => x.rejected)} rejected`;
  renderProgress();
}

async function refreshWarnings() {
  try {
    const res = await api("/api/warnings");
    const j = await res.json();
    const btn = $("btn-warnings");
    const critical = j.warnings.filter((w) => w.severity === "critical").length;
    const total = j.warnings.length;
    // "info" items (auto-mitigated background-annulus overlap) shouldn't
    // read as alarming — only an unresolved "critical" (direct label-window
    // overlap) should trigger the amber/warning styling.
    $("warn-count").textContent = total;
    btn.classList.toggle("zero", critical === 0);
    btn.firstChild.textContent = critical > 0 ? "⚠ " : total > 0 ? "ℹ " : "✓ ";
    renderWarningsPanel(j.warnings);
    scheduleAnalysis();     // refresh priority, neighbours and quality flags (review.js)
    return j;
  } catch (e) { return null; }
}

function warnItemEl(w) {
  const el = document.createElement("div");
  el.className = "warn-item";
  el.innerHTML = `<span class="sev ${esc(w.severity)}">${esc(w.severity)}</span>${esc(w.message)} ` +
    `<br><a data-id="${esc(w.a)}">→ ${esc(w.a)}</a> &nbsp; <a data-id="${esc(w.b)}">→ ${esc(w.b)}</a>`;
  return el;
}

function renderWarningsPanel(warnings) {
  const list = $("warnings-list");
  list.innerHTML = "";
  if (warnings.length === 0) {
    list.innerHTML = `<div class="empty-list">No geometry conflicts detected.</div>`;
    return;
  }

  const critical = warnings.filter((w) => w.severity === "critical");
  const info = warnings.filter((w) => w.severity !== "critical");

  // Critical items need real action (move or drop a site) — always shown
  // individually and first.
  critical.forEach((w) => list.appendChild(warnItemEl(w)));

  // Info items (auto-mitigated background-annulus overlap) are a permanent
  // geographic fact for a clustered roster, not something to act on — a
  // wall of N identical-shaped notices every time you open this panel is
  // just noise, so they're collapsed behind one summary line by default.
  if (info.length > 0) {
    const summary = document.createElement("div");
    summary.className = "warn-item";
    summary.innerHTML = `<span class="sev info">info</span>` +
      `${info.length} site pair(s) share part of a background ring. ` +
      `This is only worth knowing, not a problem to fix. ` +
      `<a class="warn-expand">show details ▾</a>`;
    const detail = document.createElement("div");
    detail.style.display = "none";
    info.forEach((w) => detail.appendChild(warnItemEl(w)));
    summary.querySelector(".warn-expand").addEventListener("click", (e) => {
      const open = detail.style.display !== "none";
      detail.style.display = open ? "none" : "block";
      e.target.textContent = open ? "show details ▾" : "hide details ▴";
    });
    list.appendChild(summary);
    list.appendChild(detail);
  }

  list.querySelectorAll("a[data-id]").forEach((a) =>
    a.addEventListener("click", () => selectSite(a.dataset.id)));
}

// ---------------------------------------------------------------------
// edit mode
// ---------------------------------------------------------------------

function currentSite() {
  return sitesDoc.sites.find((s) => s.id === activeId);
}

// Moving to another site first saves unsaved edits (setting "Save unsaved
// edits when moving to another site"), so j/k/n never discard work.
let navChain = Promise.resolve();
function selectSite(id, opts = {}) {
  navChain = navChain.then(async () => {
    if (mode === "edit" && activeId && activeId !== id && dirty[activeId] && prefs.autosave) {
      await saveActive({ quiet: true });
    }
    if (!sitesDocHasId(id)) return;
    selectSiteNow(id, opts);
  }).catch((e) => console.error(e));
  return navChain;
}

function selectSiteNow(id, opts = {}) {
  if (mode === "add") exitAddMode();
  disableMeasure();
  mode = "edit";
  activeId = id;
  const s = currentSite();
  reviewRejected = !!s.rejected;

  $("panel-empty").style.display = "none";
  $("panel-add").style.display = "none";
  $("panel-body").style.display = "block";

  $("site-name").textContent = s.name || s.id;
  $("site-id").textContent = s.id;
  $("f-verified").checked = !!s.verified && !s.rejected;
  $("f-name").value = s.name || "";
  $("f-role").value = s.role || "train";
  $("panel-title").textContent = "Site details";
  $("f-notes").value = s.notes || "";
  $("f-comment").value = s.comment || "";
  $("f-exact-grid").checked = !!prefs.overlays.exact;
  exactGridLayer.clearLayers();

  editEditor.addTo(map);
  editEditor.setBox(s.center[0], s.center[1], s.box_km, { silent: true });
  setLatLonFields(s.center[0], s.center[1]);
  $("f-box").value = s.box_km;
  $("f-box-range").value = s.box_km;
  updateGsdHint(s.box_km);
  renderPresetButtons($("panel-body").querySelector(".presets"), s.box_km, pickEditPreset);

  flyToSite(s);

  imageryReset();    // imagery.js: clears the picture, statistics and candidate outlines of the previous site
  $("save-status").textContent = "";
  setSaveIndicator("saved");
  renderSidebar();
  renderAllMarkers();
  onSiteSelected(s, opts);   // info card, overlays, chip, last-site memory (review.js)
}

function deselect() {
  mode = "idle";
  activeId = null;
  reviewRejected = false;
  editEditor.remove();
  exactGridLayer.clearLayers();
  $("panel-empty").style.display = "block";
  $("panel-title").textContent = "Details";
  $("panel-add").style.display = "none";
  $("panel-body").style.display = "none";
  renderSidebar();
  renderAllMarkers();
  onSiteDeselected();
}

function markDirty() {
  if (mode !== "edit") return;
  dirty[activeId] = true;
  $("save-status").textContent = "unsaved changes";
  setSaveIndicator("dirty");
}

function clearDirty() {
  delete dirty[activeId];
  $("save-status").textContent = "saved";
  setSaveIndicator("saved");
}

// Saves the open site. opts.quiet skips the toast; opts.status is one of
// "keep", "reject" or "pending" and is saved in the same request. Returns true on success.
async function saveActive(opts = {}) {
  if (mode !== "edit" || !activeId) return false;
  const id = activeId;
  let verified = $("f-verified").checked, rejected = reviewRejected;
  if (opts.status === "keep") { verified = true; rejected = false; }
  else if (opts.status === "reject") { verified = false; rejected = true; }
  else if (opts.status === "pending") { verified = false; rejected = false; }
  else if (verified) rejected = false;      // ticking verified keeps the site
  const patch = {
    center: [editEditor.lat, editEditor.lon],
    box_km: editEditor.boxKm,
    verified, rejected,
    name: $("f-name").value.trim() || undefined,
    role: $("f-role").value,
    notes: $("f-notes").value,
    comment: $("f-comment").value,
  };
  $("btn-save").disabled = true;
  $("save-status").textContent = "saving…";
  setSaveIndicator("saving");
  try {
    const res = await api(`/api/sites/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    const j = await res.json();
    const cur = sitesDoc.sites.find((s) => s.id === id);
    for (const k of Object.keys(cur)) if (!(k in j.site)) delete cur[k];   // a cleared flag disappears
    Object.assign(cur, j.site);
    if (activeId === id) {
      $("site-name").textContent = cur.name || cur.id;
      reviewRejected = !!cur.rejected;
      $("f-verified").checked = !!cur.verified && !cur.rejected;
      clearDirty();
    } else {
      delete dirty[id];
    }
    renderSidebar();
    renderAllMarkers();
    refreshWarnings();
    if (activeId === id) onSiteSaved(cur);
    if (!opts.quiet) showToast(`Saved ${id}`, "ok");
    return true;
  } catch (e) {
    $("save-status").textContent = "save failed: " + e.message;
    setSaveIndicator("failed");
    showToast("Save failed: " + e.message, "err");
    return false;
  } finally {
    $("btn-save").disabled = false;
  }
}

async function deleteActive() {
  if (mode !== "edit" || !activeId) return;
  const id = activeId;
  const ok = await confirmDialog(
    `Delete site "${currentSite().name || id}" for good?\n\nThis removes it from the sites file ` +
    `(a backup is kept, and Undo can bring it back this session). ` +
    `To drop it reversibly instead, use Reject.`, "Delete site");
  if (!ok) return;
  try {
    const nextId = pickNextAfter(id);
    await api(`/api/sites/${id}`, { method: "DELETE" });
    sitesDoc.sites = sitesDoc.sites.filter((s) => s.id !== id);
    delete dirty[id];
    deselect();
    refreshWarnings();
    showToast(`Deleted ${id}`, "ok");
    if (nextId && prefs.advance) selectSite(nextId);
  } catch (e) {
    showToast("Delete failed: " + e.message, "err");
  }
}

function fitViewToBox() {
  if (mode === "edit") map.fitBounds(editEditor.bounds(), { padding: [60, 60] });
  else if (mode === "add" && addEditor.group._map) map.fitBounds(addEditor.bounds(), { padding: [60, 60] });
}

// ---------------------------------------------------------------------
// add-site mode
// ---------------------------------------------------------------------

function enterAddMode() {
  if (mode === "edit") deselect();
  disableMeasure();
  mode = "add";
  $("panel-empty").style.display = "none";
  $("panel-body").style.display = "none";
  $("panel-add").style.display = "block";

  $("a-name").value = "";
  $("a-role").value = "train";
  $("a-lat").value = "";
  $("a-lon").value = "";
  $("a-box").value = prefs.defaultBox;
  $("a-box-range").value = prefs.defaultBox;
  $("a-geocode").value = "";
  $("a-geocode-results").innerHTML = "";
  $("add-status").textContent = "";
  renderPresetButtons($("panel-add").querySelector(".presets"), prefs.defaultBox, pickAddPreset);
  setBarOpen("right", true);
  $("panel-title").textContent = "Add a site";
  $("a-name").focus();

  setAddMode(false);
  $("bulk-paste").value = "";
  $("bulk-preview").innerHTML = "";
  $("bulk-parse-status").textContent = "";
  $("bulk-create-status").textContent = "";
  bulkParsedRows = [];

  addEditor.remove();
  renderAllMarkers();
}

function exitAddMode() {
  addEditor.remove();
  mode = "idle";
  $("panel-add").style.display = "none";
  $("panel-empty").style.display = "block";
  $("panel-title").textContent = "Details";
  renderAllMarkers();
}

async function runGeocode() {
  const q = $("a-geocode").value.trim();
  if (!q) return;
  $("a-geocode-results").textContent = "searching…";
  try {
    const res = await api(`/api/geocode?q=${encodeURIComponent(q)}`);
    const j = await res.json();
    const box = $("a-geocode-results");
    box.innerHTML = "";
    if (!j.results.length) { box.textContent = "no results"; return; }
    for (const r of j.results) {
      const el = document.createElement("div");
      el.className = "geo-result";
      el.textContent = r.display_name;
      el.onclick = () => {
        map.flyTo([r.lat, r.lon], 13);
        if (!addEditor.group._map) addEditor.addTo(map);
        addEditor.setBox(r.lat, r.lon, parseFloat($("a-box").value) || 3.0);
      };
      box.appendChild(el);
    }
  } catch (e) {
    $("a-geocode-results").textContent = "search failed: " + e.message;
  }
}

async function createSite() {
  const name = $("a-name").value.trim();
  if (!name) return ($("add-status").textContent = "name is required");
  if (!addEditor.group._map) return ($("add-status").textContent = "place the site on the map first (click the map or search a place name)");
  const fields = {
    name, role: $("a-role").value,
    center: [addEditor.lat, addEditor.lon],
    box_km: addEditor.boxKm,
  };
  $("btn-add-create").disabled = true;
  $("add-status").textContent = "creating…";
  try {
    const res = await api("/api/sites", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    });
    const j = await res.json();
    sitesDoc.sites.push(j.site);
    exitAddMode();
    renderSidebar();
    refreshWarnings();
    showToast(`Created ${j.site.id}`, "ok");
    selectSite(j.site.id);
  } catch (e) {
    $("add-status").textContent = "failed: " + e.message;
    showToast("Create failed: " + e.message, "err");
  } finally {
    $("btn-add-create").disabled = false;
  }
}

// ---------------------------------------------------------------------
// undo / redo
// ---------------------------------------------------------------------

async function refreshSitesDoc() {
  sitesDoc = await (await api("/api/sites")).json();
  renderSidebar();
  renderAllMarkers();
  refreshWarnings();
}

async function afterUndoRedo(kind, id) {
  // Must check against sitesDoc AFTER refreshing it — the client's copy is
  // stale (pre-mutation) until refreshSitesDoc() completes, so checking
  // "does the active site still exist" before the refresh would answer the
  // question about the OLD state, not what the undo/redo actually left
  // behind. Also applies to redo: redoing a delete can remove the site
  // that's currently open in the edit panel.
  await refreshSitesDoc();
  const activeStillEditing = mode === "edit" && activeId;
  if (activeStillEditing) delete dirty[activeId];     // the undo replaced the saved state
  if (id && id !== activeId && sitesDocHasId(id)) selectSite(id);   // show the site that changed
  else if (activeStillEditing && !sitesDocHasId(activeId)) deselect();
  else if (activeStillEditing) selectSiteNow(activeId);
}

async function doUndo() {
  try {
    const j = await (await api("/api/undo", { method: "POST" })).json();
    await afterUndoRedo("undo", j.undone.site_id);
    showToast(`Undid ${j.undone.type} (${j.undone.site_id || "bulk"})`, "ok");
  } catch (e) {
    showToast(e.message || "Nothing to undo", "info");
  }
}

async function doRedo() {
  try {
    const j = await (await api("/api/redo", { method: "POST" })).json();
    await afterUndoRedo("redo", j.redone.site_id);
    showToast(`Redid ${j.redone.type} (${j.redone.site_id || "bulk"})`, "ok");
  } catch (e) {
    showToast(e.message || "Nothing to redo", "info");
  }
}

function sitesDocHasId(id) {
  return sitesDoc && sitesDoc.sites.some((s) => s.id === id);
}

// ---------------------------------------------------------------------
// duplicate / copy-as-JSON
// ---------------------------------------------------------------------

async function duplicateActive() {
  if (mode !== "edit" || !activeId) return;
  try {
    const j = await (await api(`/api/sites/${activeId}/duplicate`, { method: "POST" })).json();
    sitesDoc.sites.push(j.site);
    renderSidebar();
    refreshWarnings();
    showToast(`Duplicated as ${j.site.id}`, "ok");
    selectSite(j.site.id);
  } catch (e) {
    showToast("Duplicate failed: " + e.message, "err");
  }
}

async function copyActiveAsJson() {
  if (mode !== "edit" || !activeId) return;
  const text = JSON.stringify(currentSite(), null, 2);
  try {
    await navigator.clipboard.writeText(text);
    showToast("Copied site JSON to clipboard", "ok");
  } catch (e) {
    showToast("Clipboard unavailable — select and copy manually", "err");
  }
}

// ---------------------------------------------------------------------
// tools menu: quick jump, backups browser, preflight
// ---------------------------------------------------------------------

function toggleToolsMenu(show) {
  $("tools-menu").style.display = show ? "block" : "none";
  $("btn-tools").setAttribute("aria-expanded", String(show));
  if (show) $("tool-jump").focus(); else if (document.activeElement && $("tools-menu").contains(document.activeElement)) $("btn-tools").focus();
  if (!show) { $("jump-box").style.display = "none"; $("preflight-box").style.display = "none"; }
}

async function jumpToCoords() {
  const lat = parseFloat($("jump-lat").value), lon = parseFloat($("jump-lon").value);
  if (Number.isNaN(lat) || Number.isNaN(lon)) return showToast("Enter both lat and lon", "err");
  map.flyTo([lat, lon], 13);
  toggleToolsMenu(false);
}

async function runPreflightCheck() {
  const box = $("preflight-box");
  box.style.display = "block";
  box.textContent = "Checking data availability… (a few seconds, longer if Earth Engine is degraded)";
  try {
    const res = await api("/api/preflight");
    const j = await res.json();
    box.innerHTML = Object.entries(j).map(([name, status]) =>
      `<div style="color:${status === "AVAILABLE" ? "var(--good)" : "var(--danger)"}">${status === "AVAILABLE" ? "✓" : "✕"} ${esc(name)}: ${esc(status)}</div>`
    ).join("");
  } catch (e) {
    box.textContent = "Preflight failed: " + e.message;
  }
}

async function estimateCoverageForActive() {
  if (mode !== "edit" || !activeId) return;
  const el = $("coverage-result");
  el.textContent = "estimating… (a few seconds)";
  try {
    const j = await (await api(`/api/coverage?lat=${editEditor.lat}&lon=${editEditor.lon}&box_km=${editEditor.boxKm}`)).json();
    el.textContent = `~${j.s2_scenes_lt_cloud_gate} S2 scenes, ${j.s5p_granules} S5P granules over the full range ` +
      `(${j.possible_windows} possible windows) — approximate, not a real pass rate`;
    el.title = j.note;
  } catch (e) {
    el.textContent = "coverage estimate failed: " + e.message;
  }
}

async function loadBackups() {
  const list = $("backups-list");
  list.innerHTML = "loading…";
  try {
    const backups = await (await api("/api/backups")).json();
    if (backups.length === 0) { list.innerHTML = `<div class="empty-list">No backups yet — one is made on every save.</div>`; return; }
    list.innerHTML = "";
    for (const b of backups.slice(0, 30)) {
      const el = document.createElement("div");
      el.className = "warn-item";
      const when = new Date(b.modified).toLocaleString();
      el.innerHTML = `<b>${esc(when)}</b> <span class="mono muted">(${(b.size / 1024).toFixed(1)} KB)</span><br>
        <a data-act="diff" data-fn="${esc(b.filename)}">show diff vs current</a> &nbsp;
        <a data-act="restore" data-fn="${esc(b.filename)}">restore this</a>
        <div class="diff-out mono" style="display:none; margin-top:6px"></div>`;
      list.appendChild(el);
    }
    list.querySelectorAll('a[data-act="diff"]').forEach((a) => a.addEventListener("click", async () => {
      const out = a.parentElement.querySelector(".diff-out");
      out.style.display = "block";
      out.textContent = "computing diff…";
      out.innerHTML = renderBackupDiff(await (await api(`/api/backups/${encodeURIComponent(a.dataset.fn)}`)).json());
    }));
    list.querySelectorAll('a[data-act="restore"]').forEach((a) => a.addEventListener("click", async () => {
      const ok = await confirmDialog(`Restore sites.json from this backup? Your current state is itself backed up first, so this is reversible.`);
      if (!ok) return;
      try {
        await api(`/api/backups/${a.dataset.fn}/restore`, { method: "POST" });
        await refreshSitesDoc();
        showToast("Restored from backup", "ok");
        toggleToolsMenu(false);
        $("backups-panel").style.display = "none";
      } catch (e) {
        showToast("Restore failed: " + e.message, "err");
      }
    }));
  } catch (e) {
    list.innerHTML = "failed to load backups: " + esc(e.message);
  }
}

function renderBackupDiff(oldDoc) {
  const oldById = Object.fromEntries(oldDoc.sites.map((s) => [s.id, s]));
  const newById = Object.fromEntries(sitesDoc.sites.map((s) => [s.id, s]));
  const lines = [];
  for (const id of Object.keys(newById)) {
    if (!oldById[id]) { lines.push(`<div class="diff-add">+ added ${esc(id)}</div>`); continue; }
    const a = oldById[id], b = newById[id];
    const changed = ["name", "role", "box_km", "verified", "rejected", "notes", "comment"].filter((k) => a[k] !== b[k])
      .concat(a.center[0] !== b.center[0] || a.center[1] !== b.center[1] ? ["center"] : []);
    if (changed.length) lines.push(`<div class="diff-chg">~ ${esc(id)}: ${changed.join(", ")} changed</div>`);
  }
  for (const id of Object.keys(oldById)) {
    if (!newById[id]) lines.push(`<div class="diff-del">- removed ${esc(id)}</div>`);
  }
  return lines.length ? lines.join("") : "<div>Identical to current.</div>";
}

// ---------------------------------------------------------------------
// bulk import (paste CSV or JSON)
// ---------------------------------------------------------------------

let bulkParsedRows = [];

function setAddMode(bulkMode) {
  document.querySelectorAll(".add-mode-btn").forEach((b) => b.classList.toggle("active", (b.dataset.mode === "bulk") === bulkMode));
  $("add-single").style.display = bulkMode ? "none" : "block";
  $("add-bulk").style.display = bulkMode ? "block" : "none";
}

function parseBulkPaste(text) {
  text = text.trim();
  if (!text) return { rows: [], errors: ["nothing pasted"] };
  const errors = [];
  let rows = [];
  if (text.startsWith("[")) {
    try {
      const arr = JSON.parse(text);
      rows = arr.map((r, i) => {
        if (r.lat == null || r.lon == null) { errors.push(`row ${i + 1}: missing lat/lon`); return null; }
        return { name: r.name || `site_${i + 1}`, role: r.role || "train", lat: +r.lat, lon: +r.lon, box_km: r.box_km != null ? +r.box_km : 3.0 };
      }).filter(Boolean);
    } catch (e) { errors.push("invalid JSON: " + e.message); }
  } else {
    const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
    for (let i = 0; i < lines.length; i++) {
      const parts = lines[i].split(",").map((p) => p.trim());
      if (i === 0 && isNaN(parseFloat(parts[2]))) continue; // header row
      const [name, role, lat, lon, box] = parts;
      if (!name || lat == null || lon == null || isNaN(parseFloat(lat)) || isNaN(parseFloat(lon))) {
        errors.push(`line ${i + 1}: expected name,role,lat,lon[,box_km]`); continue;
      }
      rows.push({ name, role: role || "train", lat: +lat, lon: +lon, box_km: box ? +box : 3.0 });
    }
  }
  return { rows, errors };
}

function renderBulkPreview(rows, errors) {
  const box = $("bulk-preview");
  box.innerHTML = "";
  errors.forEach((e) => { const d = document.createElement("div"); d.className = "bulk-row err"; d.textContent = "⚠ " + e; box.appendChild(d); });
  rows.forEach((r, i) => {
    const d = document.createElement("div");
    d.className = "bulk-row";
    d.innerHTML = `<span class="idx">${i + 1}</span><span>${esc(r.name)}</span><span class="mono muted">${esc(r.role)} · ${r.lat.toFixed(4)},${r.lon.toFixed(4)} · ${r.box_km}km</span>`;
    box.appendChild(d);
  });
  $("bulk-parse-status").textContent = `${rows.length} valid row(s)${errors.length ? `, ${errors.length} error(s)` : ""}`;
  $("btn-bulk-create").disabled = rows.length === 0;
}

async function createBulkSites() {
  if (bulkParsedRows.length === 0) return;
  $("btn-bulk-create").disabled = true;
  $("bulk-create-status").textContent = "creating…";
  try {
    const res = await api("/api/sites/bulk_create", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: bulkParsedRows }),
    });
    const j = await res.json();
    sitesDoc.sites.push(...j.created);
    exitAddMode();
    renderSidebar();
    refreshWarnings();
    showToast(`Created ${j.count} sites`, "ok");
  } catch (e) {
    $("bulk-create-status").textContent = "failed: " + e.message;
    showToast("Bulk import failed: " + e.message, "err");
  } finally {
    $("btn-bulk-create").disabled = false;
  }
}

// ---------------------------------------------------------------------
// top-level view switch: Map / Gallery / Stats
// ---------------------------------------------------------------------

function switchTopView(view) {
  topView = view;
  document.querySelectorAll(".view-switch-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
    b.setAttribute("aria-pressed", String(b.dataset.view === view));
  });
  $("view-map").style.display = view === "map" ? "flex" : "none";
  $("view-gallery").style.display = view === "gallery" ? "flex" : "none";
  $("view-stats").style.display = view === "stats" ? "flex" : "none";
  if (view === "map") setTimeout(() => map && map.invalidateSize(), 50);
  if (view === "gallery") renderGallery();
  if (view === "stats") renderStatsCharts();
}

// ---------------------------------------------------------------------
// gallery view (contact sheet of all sites)
// ---------------------------------------------------------------------

async function renderGallery() {
  const grid = $("gallery-grid");
  grid.innerHTML = "";
  if (!sitesDoc) return;
  const sites = filteredSites();
  $("gallery-summary").textContent = `${sites.length} site(s) shown (filtered same as sidebar)`;
  for (const s of sites) {
    const card = document.createElement("div");
    card.className = "gallery-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `Open ${s.name || s.id} (${stateLabel(s)})`);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target === card) { switchTopView("map"); selectSite(s.id); }
    });
    card.innerHTML = `<div class="ph">loading…</div>
      <div class="meta"><div class="n">${esc(s.name || s.id)}</div>
      <div class="mono muted">${esc(s.role)} · ${s.box_km}km</div></div>`;
    card.onclick = () => { switchTopView("map"); selectSite(s.id); };
    grid.appendChild(card);
    checkAndRenderThumb(s, card);
  }
}

async function checkAndRenderThumb(s, card) {
  try {
    const check = await (await api(`/api/preview/${s.id}?box_km=${s.box_km}&lat=${s.center[0]}&lon=${s.center[1]}&view=true_color&check_only=1`)).json();
    const ph = card.querySelector(".ph");
    if (check.cached) {
      const img = document.createElement("img");
      img.src = `/api/preview/${s.id}?box_km=${s.box_km}&lat=${s.center[0]}&lon=${s.center[1]}&view=true_color`;
      ph.replaceWith(img);
    } else {
      ph.innerHTML = "no preview cached";
      const btn = document.createElement("button");
      btn.className = "fetch-one";
      btn.textContent = "Fetch";
      btn.onclick = async (e) => { e.stopPropagation(); await fetchOneGalleryThumb(s, card); };
      ph.appendChild(document.createElement("br"));
      ph.appendChild(btn);
    }
  } catch (e) { /* leave placeholder */ }
}

async function fetchOneGalleryThumb(s, card) {
  const ph = card.querySelector(".ph") || card.querySelector("img");
  try {
    const url = `/api/preview/${s.id}?box_km=${s.box_km}&lat=${s.center[0]}&lon=${s.center[1]}&view=true_color&force=1`;
    const res = await api(url);
    const blob = await res.blob();
    const img = document.createElement("img");
    img.src = URL.createObjectURL(blob);
    ph.replaceWith(img);
  } catch (e) {
    showToast(`Fetch failed for ${s.id}: ` + e.message, "err");
  }
}

async function fetchAllMissing() {
  const sites = filteredSites();
  const btn = $("gallery-fetch-missing");
  btn.disabled = true;
  let done = 0;
  for (const s of sites) {
    $("gallery-progress").textContent = `${done}/${sites.length}…`;
    try {
      const check = await (await api(`/api/preview/${s.id}?box_km=${s.box_km}&lat=${s.center[0]}&lon=${s.center[1]}&view=true_color&check_only=1`)).json();
      if (!check.cached) {
        await api(`/api/preview/${s.id}?box_km=${s.box_km}&lat=${s.center[0]}&lon=${s.center[1]}&view=true_color&force=1`);
      }
    } catch (e) { /* keep going */ }
    done++;
  }
  $("gallery-progress").textContent = "done";
  btn.disabled = false;
  renderGallery();
}

// ---------------------------------------------------------------------
// roster visualizations (validated categorical/sequential colors — see
// dataviz skill; direct labels ship alongside color per its CVD-floor rule)
// ---------------------------------------------------------------------

function statBar(label, value, max, color) {
  const pct = max > 0 ? Math.max((value / max) * 100, value > 0 ? 3 : 0) : 0;
  return `<div class="stat-bar-row">
    <span class="stat-bar-label">${label}</span>
    <div class="stat-bar-track"><div class="stat-bar-fill" style="width:${pct}%;background:${color}"></div>
      <span class="stat-bar-value">${value}</span></div>
  </div>`;
}

function renderStatsCharts() {
  const grid = $("stats-grid");
  if (!sitesDoc) return;
  const sites = sitesDoc.sites;
  const n = (pred) => sites.filter(pred).length;

  // train/test/decoy — validated dark-mode categorical slots (blue/green/violet)
  const roleMax = Math.max(n((s) => s.role === "train"), n((s) => s.role === "test"), n((s) => s.role === "decoy"), 1);
  const roleCard = `<div class="stat-card"><h3>Sites by role</h3>
    ${statBar("train", n((s) => s.role === "train"), roleMax, "#3987e5")}
    ${statBar("test", n((s) => s.role === "test"), roleMax, "#008300")}
    ${statBar("decoy", n((s) => s.role === "decoy"), roleMax, "#9085e9")}
  </div>`;

  // verified/unverified — status palette (good/warning)
  const nKept = n((s) => s.verified && !s.rejected), nRej = n((s) => s.rejected);
  const nPend = n((s) => !s.verified && !s.rejected);
  const vMax = Math.max(nKept, nRej, nPend, 1);
  const vCard = `<div class="stat-card"><h3>Review status</h3>
    ${statBar("kept", nKept, vMax, "#0ca30c")}
    ${statBar("pending", nPend, vMax, "#fab219")}
    ${statBar("rejected", nRej, vMax, "#e8590c")}
  </div>`;

  // box_km distribution — single sequential hue (magnitude via bar length, not color)
  const boxBuckets = {};
  for (const s of sites) { const k = s.box_km.toFixed(1); boxBuckets[k] = (boxBuckets[k] || 0) + 1; }
  const boxKeys = Object.keys(boxBuckets).sort((a, b) => +a - +b);
  const boxMax = Math.max(...Object.values(boxBuckets), 1);
  const boxCard = `<div class="stat-card"><h3>Box size distribution (km)</h3>
    ${boxKeys.map((k) => statBar(k, boxBuckets[k], boxMax, "#3987e5")).join("")}
  </div>`;

  // pairwise inter-site distance histogram — surfaces clustering before it
  // becomes a geometry warning
  const dists = [];
  for (let i = 0; i < sites.length; i++)
    for (let j = i + 1; j < sites.length; j++)
      dists.push(haversineKm(sites[i].center, sites[j].center));
  const bucketSize = 250;
  const distBuckets = {};
  for (const d of dists) { const k = Math.floor(d / bucketSize) * bucketSize; distBuckets[k] = (distBuckets[k] || 0) + 1; }
  const distKeys = Object.keys(distBuckets).map(Number).sort((a, b) => a - b);
  const distMax = Math.max(...Object.values(distBuckets), 1);
  const distCard = `<div class="stat-card"><h3>Pairwise site distances (km)</h3>
    ${distKeys.map((k) => statBar(`${k}-${k + bucketSize}`, distBuckets[k], distMax, "#3987e5")).join("")}
    <div class="hint-small" style="margin-top:10px">Pairs under ${statusInfo ? statusInfo.bg_outer_km : 150} km trigger a
      geometry warning (see the ⚠ panel); it only means their background rings share ground.</div>
  </div>`;

  grid.innerHTML = roleCard + vCard + boxCard + distCard;
}

function haversineKm(a, b) {
  const toRad = (d) => (d * Math.PI) / 180;
  const [lat1, lon1] = a, [lat2, lon2] = b;
  const dLat = toRad(lat2 - lat1), dLon = toRad(lon2 - lon1);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

// ---------------------------------------------------------------------
// compare panel
// ---------------------------------------------------------------------

async function openCompare() {
  const ids = [...selectedIds];
  if (ids.length < 2) return;
  const panel = $("compare-panel");
  panel.style.display = "flex";
  const body = $("compare-body");
  body.innerHTML = ids.map((id) => `<div class="compare-card" data-id="${esc(id)}">loading…</div>`).join("");
  for (const id of ids) {
    const s = sitesDoc.sites.find((x) => x.id === id);
    const card = body.querySelector(`[data-id="${id}"]`);
    card.innerHTML = `
      <div class="ph" style="">no preview cached</div>
      <table>
        <tr><td>id</td><td class="mono">${esc(s.id)}</td></tr>
        <tr><td>role</td><td>${esc(s.role)}</td></tr>
        <tr><td>box_km</td><td>${s.box_km}</td></tr>
        <tr><td>verified</td><td>${s.verified ? "yes" : "no"}</td></tr>
        <tr><td>center</td><td class="mono">${s.center[0].toFixed(5)}, ${s.center[1].toFixed(5)}</td></tr>
      </table>
      <button class="fetch-compare" data-id="${esc(id)}" style="margin-top:6px;width:100%">Fetch preview</button>`;
    checkCompareThumb(s, card);
  }
  body.querySelectorAll(".fetch-compare").forEach((btn) => btn.addEventListener("click", async () => {
    const id = btn.dataset.id;
    const s = sitesDoc.sites.find((x) => x.id === id);
    const card = body.querySelector(`[data-id="${id}"]`);
    btn.disabled = true; btn.textContent = "fetching (10-30s)…";
    try {
      const url = `/api/preview/${id}?box_km=${s.box_km}&lat=${s.center[0]}&lon=${s.center[1]}&view=true_color&force=1`;
      const blob = await (await api(url)).blob();
      const img = document.createElement("img");
      img.src = URL.createObjectURL(blob);
      card.querySelector(".ph").replaceWith(img);
    } catch (e) {
      showToast("Preview fetch failed: " + e.message, "err");
    } finally {
      btn.disabled = false; btn.textContent = "Re-fetch (live)";
    }
  }));
}

async function checkCompareThumb(s, card) {
  try {
    const check = await (await api(`/api/preview/${s.id}?box_km=${s.box_km}&lat=${s.center[0]}&lon=${s.center[1]}&view=true_color&check_only=1`)).json();
    if (check.cached) {
      const url = `/api/preview/${s.id}?box_km=${s.box_km}&lat=${s.center[0]}&lon=${s.center[1]}&view=true_color`;
      const blob = await (await api(url)).blob();
      const img = document.createElement("img");
      img.src = URL.createObjectURL(blob);
      card.querySelector(".ph").replaceWith(img);
    }
  } catch (e) { /* leave placeholder */ }
}

// ---------------------------------------------------------------------
// measure-distance tool
// ---------------------------------------------------------------------

function toggleMeasure() {
  measureActive = !measureActive;
  measurePoints = [];
  measureLayer.clearLayers();
  map.getContainer().style.cursor = measureActive ? "crosshair" : "";
  showToast(measureActive ? "Measure: click two points on the map" : "Measure tool off",
           measureActive ? "info" : "info", 2500);
  toggleToolsMenu(false);
}

function disableMeasure() {
  // Measure and add/edit-mode map clicks both want ownership of map clicks;
  // switching into add or edit mode always wins.
  if (!measureActive) return;
  measureActive = false;
  measurePoints = [];
  measureLayer.clearLayers();
  map.getContainer().style.cursor = "";
}

function handleMeasureClick(latlng) {
  measurePoints.push(latlng);
  L.circleMarker(latlng, { radius: 4, color: cssVar("--ov-label") }).addTo(measureLayer);
  if (measurePoints.length === 2) {
    const [a, b] = measurePoints;
    const d = haversineKm([a.lat, a.lng], [b.lat, b.lng]);
    L.polyline([a, b], { color: cssVar("--ov-label"), weight: 2, dashArray: "4 4" }).addTo(measureLayer);
    const mid = L.latLng((a.lat + b.lat) / 2, (a.lng + b.lng) / 2);
    L.marker(mid, {
      icon: L.divIcon({ className: "box-label", html: `${d.toFixed(1)} km`, iconSize: [80, 22] }),
      interactive: false,
    }).addTo(measureLayer);
    measurePoints = [];
  }
}

// ---------------------------------------------------------------------
// event wiring
// ---------------------------------------------------------------------

function wireEvents() {
  ["f-lat", "f-lon"].forEach((id) =>
    $(id).addEventListener("change", () => {
      const lat = parseFloat($("f-lat").value), lon = parseFloat($("f-lon").value);
      if (Number.isNaN(lat) || Number.isNaN(lon)) return;
      editEditor.setBox(lat, lon, editEditor.boxKm);
    })
  );
  const syncEditBox = (val) => editEditor.setBox(editEditor.lat, editEditor.lon, parseFloat(val));
  $("f-box").addEventListener("input", () => syncEditBox($("f-box").value));
  $("f-box-range").addEventListener("input", () => syncEditBox($("f-box-range").value));
  $("f-verified").addEventListener("change", () => {
    if ($("f-verified").checked) reviewRejected = false;
    markDirty(); renderChip();
  });
  $("f-notes").addEventListener("input", markDirty);
  $("f-name").addEventListener("input", () => { markDirty(); syncQuick(); });
  $("f-role").addEventListener("change", () => { markDirty(); syncQuick(); });
  $("f-comment").addEventListener("input", markDirty);
  $("f-exact-grid").addEventListener("change", () => {
    if ($("f-exact-grid").checked) loadExactGrid(editEditor.lat, editEditor.lon, editEditor.boxKm);
    else exactGridLayer.clearLayers();
  });
  $("btn-fit-view").addEventListener("click", fitViewToBox);

  $("btn-revert").addEventListener("click", () => { if (activeId) selectSite(activeId); });
  $("btn-save").addEventListener("click", () => saveActive());
  $("btn-delete").addEventListener("click", deleteActive);

  $("btn-add").addEventListener("click", enterAddMode);
  $("btn-add-cancel").addEventListener("click", exitAddMode);
  $("btn-add-create").addEventListener("click", createSite);
  $("a-geocode-btn").addEventListener("click", runGeocode);
  $("a-geocode").addEventListener("keydown", (e) => { if (e.key === "Enter") runGeocode(); });
  const syncAddBox = (val) => addEditor.setBox(
    addEditor.lat || parseFloat($("a-lat").value) || 0,
    addEditor.lon || parseFloat($("a-lon").value) || 0,
    parseFloat(val));
  $("a-box").addEventListener("input", () => { if (addEditor.group._map) syncAddBox($("a-box").value); else $("a-box-range").value = $("a-box").value; });
  $("a-box-range").addEventListener("input", () => { $("a-box").value = $("a-box-range").value; if (addEditor.group._map) syncAddBox($("a-box-range").value); });
  ["a-lat", "a-lon"].forEach((id) => $(id).addEventListener("change", () => {
    const lat = parseFloat($("a-lat").value), lon = parseFloat($("a-lon").value);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return;
    if (!addEditor.group._map) addEditor.addTo(map);
    addEditor.setBox(lat, lon, parseFloat($("a-box").value) || 3.0);
  }));

  wireReviewEvents();   // filters, review bar, layers, dialogs, preferences (review.js)

  $("btn-warnings").addEventListener("click", () => {
    const p = $("warnings-panel");
    p.style.display = p.style.display === "none" ? "flex" : "none";
    $("btn-warnings").setAttribute("aria-expanded", String(p.style.display !== "none"));
  });
  $("warn-close").addEventListener("click", () => {
    $("warnings-panel").style.display = "none";
    $("btn-warnings").setAttribute("aria-expanded", "false");
    $("btn-warnings").focus();
  });

  // undo / redo
  $("btn-undo").addEventListener("click", doUndo);
  $("btn-redo").addEventListener("click", doRedo);

  // duplicate / copy-json
  $("btn-duplicate").addEventListener("click", duplicateActive);
  $("btn-copy-json").addEventListener("click", copyActiveAsJson);
  $("btn-coverage").addEventListener("click", estimateCoverageForActive);

  // tools menu
  $("btn-tools").addEventListener("click", () => toggleToolsMenu($("tools-menu").style.display === "none"));
  $("tools-close").addEventListener("click", () => toggleToolsMenu(false));
  $("tool-jump").addEventListener("click", () => {
    $("jump-box").style.display = $("jump-box").style.display === "none" ? "block" : "none";
    $("preflight-box").style.display = "none";
  });
  $("jump-go").addEventListener("click", jumpToCoords);
  $("tool-preflight").addEventListener("click", () => {
    $("preflight-box").style.display = "block";
    $("jump-box").style.display = "none";
    runPreflightCheck();
  });
  $("tool-backups").addEventListener("click", () => {
    toggleToolsMenu(false);
    $("backups-panel").style.display = "flex";
    loadBackups();
  });
  $("backups-close").addEventListener("click", () => { $("backups-panel").style.display = "none"; });
  $("tool-measure").addEventListener("click", toggleMeasure);
  $("tool-basemap").addEventListener("click", () => {
    toggleBasemap();
    toggleToolsMenu(false);
  });

  // bulk selection bar
  $("bulk-select-all").addEventListener("change", (e) => {
    const visible = filteredSites().map((s) => s.id);
    if (e.target.checked) visible.forEach((id) => selectedIds.add(id));
    else visible.forEach((id) => selectedIds.delete(id));
    renderSidebar();
  });
  $("bulk-verify").addEventListener("click", () => bulkAction("verify"));
  $("bulk-unverify").addEventListener("click", () => bulkAction("unverify"));
  $("bulk-reject").addEventListener("click", () => bulkAction("reject"));
  $("bulk-pending").addEventListener("click", () => bulkAction("pending"));
  $("bulk-role").addEventListener("change", (e) => {
    if (!e.target.value) return;
    bulkAction("set_role", { role: e.target.value });
    e.target.value = "";
  });
  $("bulk-delete").addEventListener("click", bulkDeleteSelected);
  $("bulk-compare").addEventListener("click", openCompare);
  $("compare-close").addEventListener("click", () => { $("compare-panel").style.display = "none"; });

  // add-site: single/bulk mode switch + bulk import flow
  document.querySelectorAll(".add-mode-btn").forEach((b) =>
    b.addEventListener("click", () => setAddMode(b.dataset.mode === "bulk")));
  $("btn-add-cancel-bulk").addEventListener("click", exitAddMode);
  $("btn-bulk-parse").addEventListener("click", () => {
    const { rows, errors } = parseBulkPaste($("bulk-paste").value);
    bulkParsedRows = rows;
    renderBulkPreview(rows, errors);
  });
  $("btn-bulk-create").addEventListener("click", createBulkSites);

  // top-level view switch
  document.querySelectorAll(".view-switch-btn").forEach((b) =>
    b.addEventListener("click", () => switchTopView(b.dataset.view)));
  $("gallery-fetch-missing").addEventListener("click", fetchAllMissing);

  document.addEventListener("keydown", (e) => {
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

    if (handleShortcut(e, typing)) return;   // review shortcuts and dialogs (review.js)

    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
      e.preventDefault(); doUndo(); return;
    }
    if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === "y" || (e.shiftKey && e.key.toLowerCase() === "z"))) {
      e.preventDefault(); doRedo(); return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      if (mode === "edit") saveActive();
      else if (mode === "add") createSite();
      return;
    }
    if (e.key === "Escape") {
      if (closeFloatingPanels()) return;
      if (measureActive) { toggleMeasure(); return; }
      if (mode === "add") exitAddMode();
      else if (mode === "edit") deselect();
      return;
    }
    if (mode === "edit" && !typing && e.key.startsWith("Arrow")) {
      e.preventDefault();
      const step = e.shiftKey ? 0.003 : 0.0003; // ~330m / ~33m at the equator
      let lat = editEditor.lat, lon = editEditor.lon;
      if (e.key === "ArrowUp") lat += step;
      if (e.key === "ArrowDown") lat -= step;
      if (e.key === "ArrowLeft") lon -= step;
      if (e.key === "ArrowRight") lon += step;
      editEditor.setBox(lat, lon, editEditor.boxKm);
    }
  });
}

// ---------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------

async function refreshEeStatus() {
  const badge = $("ee-status");
  try {
    const res = await api("/api/status");
    statusInfo = await res.json();
    imageryStatus(statusInfo);
    $("file-name").textContent = (statusInfo.sites_path || "").split(/[\\/]/).pop();
    $("file-name").title = statusInfo.sites_path || "";
    if (statusInfo.ee_ready) {
      badge.textContent = "Earth Engine ready";
      badge.className = "badge ok";
      return true;
    }
    badge.textContent = "EE initializing / unavailable";
    badge.className = "badge muted";
    badge.title = statusInfo.ee_error || "";
    return false;
  } catch (e) {
    badge.textContent = "server unreachable";
    badge.className = "badge err";
    return false;
  }
}

async function boot() {
  initMap();
  wireEvents();
  wireImagery();
  wireStudies();
  HelpCenter.wire();
  initLayout();
  loadImageryData().then(() => renderViewTabs());

  let ready = await refreshEeStatus();
  let tries = 0;
  const poll = setInterval(async () => {
    if (ready || ++tries > 10) return clearInterval(poll);
    ready = await refreshEeStatus();
  }, 2000);

  try {
    const res = await api("/api/sites");
    sitesDoc = await res.json();
  } catch (e) {
    showBanner("Could not load the sites file: " + e.message);
    return;
  }
  renderSidebar();
  renderAllMarkers();
  refreshWarnings();
  afterSitesLoaded();   // filters, reference layer, analysis, last site, first-run tour (review.js)
}

boot();
