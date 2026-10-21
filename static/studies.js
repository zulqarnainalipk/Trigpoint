// TrigPoint studies: split safety (overlap groups, near-duplicates, domain shift, certificate), forecast,
// coordinate grounding and the placement study. Loaded after imagery.js and before app.js.
// Everything shown comes from the server and is inserted with textContent, never as markup.

"use strict";

const ST = { cert: null, groupsLevel: null, pred: null, last: {}, outcomes: null };

function stBusy(btn, label, fn) {
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = label;
  return Promise.resolve(fn()).finally(() => { btn.disabled = false; btn.textContent = old; });
}

function stPost(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }).then((r) => r.json());
}

function stTable(caption, headers, rows, cls) {
  const t = mk("table", null, "st-table" + (cls ? " " + cls : ""));
  t.appendChild(mk("caption", caption));
  const hr = mk("tr");
  headers.forEach((h) => hr.appendChild(mk("th", h, null, { scope: "col" })));
  t.appendChild(mk("thead")).appendChild(hr);
  const tb = mk("tbody");
  for (const r of rows) {
    const tr = mk("tr");
    r.forEach((c, i) => {
      if (c instanceof Node) { const td = mk("td"); td.appendChild(c); tr.appendChild(td); }
      else tr.appendChild(mk(i === 0 ? "th" : "td", c == null ? "n/a" : String(c), null, i === 0 ? { scope: "row" } : null));
    });
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  const wrap = mk("div", null, "st-table-wrap");
  wrap.appendChild(t);
  return wrap;
}

const ST_GLYPH = { pass: "✓", agree: "✓", fail: "✕", disagree: "✕", warn: "!", differ: "!", conditional: "!", not_run: "–", not_found: "–" };
const ST_WORD = { pass: "Passed", fail: "Failed", warn: "Look at this", not_run: "Not run", conditional: "Conditional",
                  agree: "Agree", differ: "Differ a little", disagree: "Disagree", not_found: "Not found" };

function stBadge(status) {
  const b = mk("span", null, "st-badge st-" + status);
  b.appendChild(mk("span", ST_GLYPH[status] || "?", "st-glyph", { "aria-hidden": "true" }));
  b.appendChild(document.createTextNode(" " + (ST_WORD[status] || status)));
  return b;
}

function stShowSites(ids) {
  // select the first site and fit the map to all of them, so the sites that clash can be seen together
  const sites = (sitesDoc ? sitesDoc.sites : []).filter((s) => ids.includes(s.id));
  $("studies-dialog").close();
  if (!sites.length) return;
  selectSite(sites[0].id);
  if (sites.length > 1 && typeof map !== "undefined" && map && window.L) {
    map.fitBounds(L.latLngBounds(sites.map((s) => s.center)).pad(0.3), { animate: !motionReduced(), maxZoom: 9 });
  }
  announce(`Showing ${sites.length} site${sites.length === 1 ? "" : "s"} on the map.`);
}

function stGroupTable(caption, groups) {
  return stTable(caption, ["Group", "Sites", "Roles", ""], groups.slice(0, 30).map((g) => {
    const b = mk("button", "Show on map", null, { type: "button", "aria-label": `Show group ${g.id} on the map` });
    b.addEventListener("click", () => stShowSites(g.members));
    return [g.id, g.members.join(", "), g.roles.join(" + "), b];
  }));
}

function stFail(out, e) {
  out.textContent = "";
  out.appendChild(mk("p", friendlyError(e.message || String(e)), "callout bad", { role: "alert" }));
}

function stNote(out, text, cls) {
  out.appendChild(mk("p", text, cls || "hint-small"));
}

function stLoadText(fileInput, textArea) {
  const f = fileInput.files && fileInput.files[0];
  if (!f) return Promise.resolve(textArea.value);
  if (f.size > 4 * 1024 * 1024) return Promise.reject(new Error("The file is larger than 4 MB."));
  return f.text();
}

// ------------------------------------------------------------------ tabs

function stSelectTab(id, focus) {
  document.querySelectorAll("#st-tabs [role=tab]").forEach((t) => {
    const on = t.id === id;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")).hidden = !on;
    if (on && focus) t.focus();
  });
  if (id === "st-t-place") stRefreshPlacementSite();
  if (id === "st-t-forecast") stRefreshOutcomes();
  if (id === "st-t-coords") stRefreshRegistries();
}

function stWireTabs() {
  const tabs = [...document.querySelectorAll("#st-tabs [role=tab]")];
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => stSelectTab(t.id, false));
    t.addEventListener("keydown", (e) => {
      let j = null;
      if (e.key === "ArrowRight") j = (i + 1) % tabs.length;
      else if (e.key === "ArrowLeft") j = (i + tabs.length - 1) % tabs.length;
      else if (e.key === "Home") j = 0;
      else if (e.key === "End") j = tabs.length - 1;
      if (j != null) { e.preventDefault(); stSelectTab(tabs[j].id, true); }
    });
  });
}

function stFillSelects() {
  const roles = [...new Set((sitesDoc ? sitesDoc.sites : []).map((s) => s.role))].sort();
  const names = roles.length ? roles : ["train", "test"];
  for (const [id, def] of [["st-shift-a", "train"], ["st-shift-b", "test"]]) {
    const sel = $(id);
    const keep = sel.value;
    sel.textContent = "";
    names.forEach((r) => { const o = mk("option", r); o.value = r; sel.appendChild(o); });
    sel.value = names.includes(keep) ? keep : (names.includes(def) ? def : names[0]);
  }
  for (const id of ["st-dup-backend", "st-pl-backend"]) {
    const sel = $(id);
    const keep = sel.value || ip().backend;
    sel.textContent = "";
    for (const b of IMG.backends) { const o = mk("option", b.label); o.value = b.name; sel.appendChild(o); }
    if (!IMG.backends.length) { const o = mk("option", "Demo (synthetic scenes)"); o.value = "demo"; sel.appendChild(o); }
    sel.value = [...sel.options].some((o) => o.value === keep) ? keep : sel.options[0].value;
  }
}

async function openStudies(tab) {
  stFillSelects();
  const d = openDialog("studies-dialog");
  stSelectTab(tab || "st-t-split", false);
  return d;
}

// ------------------------------------------------------------------ overlap groups

const LEVEL_SHORT = { box: "Boxes overlap", label: "Label windows overlap", background: "Background ring reached", ring: "Rings overlap (distance rule)" };

async function stFindGroups() {
  const out = $("st-groups-out");
  out.textContent = "Working…";
  try {
    const level = $("st-level").value;
    const j = await (await api("/api/studies/groups?level=" + encodeURIComponent(level))).json();
    ST.groupsLevel = level;
    out.textContent = "";
    const rows = Object.entries(j.summary.levels).map(([lv, v]) => [LEVEL_SHORT[lv] || lv, v.n_pairs, v.n_groups, v.n_multi_site_groups, v.n_mixed_role_groups]);
    out.appendChild(stTable("Pairs and groups at each level (for the whole roster)", ["Link when", "Pairs", "Groups", "Groups of 2 or more sites", "Groups with mixed roles"], rows));
    const mixed = j.groups.filter((g) => g.mixed_roles);
    out.appendChild(mk("p", `At the chosen level there are ${j.n_groups} group${j.n_groups === 1 ? "" : "s"}; ${mixed.length} of them mix roles, which means those sites would be split between train and test.`,
      mixed.length ? "callout warn" : "callout info", { role: "status" }));
    if (mixed.length) {
      out.appendChild(stGroupTable("Groups that mix roles", mixed));
    }
    $("st-groups-apply").disabled = false;
    announce(`${j.n_groups} groups found, ${mixed.length} with mixed roles.`);
  } catch (e) { stFail(out, e); }
}

async function stApplyGroups() {
  const ok = await confirmDialog(`Write a group id (overlap_group) into every site, using the level "${LEVEL_SHORT[ST.groupsLevel] || ST.groupsLevel}"? You can undo this with Ctrl+Z.`, "Write group ids");
  if (!ok) return;
  const out = $("st-groups-out");
  try {
    const j = await stPost("/api/studies/groups", { level: ST.groupsLevel, apply: true });
    await refreshSitesDoc();
    showToast(`Group ids written for ${j.n_sites} sites.`, "ok");
    announce("Group ids written into the roster.");
  } catch (e) { stFail(out, e); }
}

// ------------------------------------------------------------------ duplicates

async function stRunDuplicates() {
  const out = $("st-dup-out");
  out.textContent = "Working…";
  try {
    const j = await stPost("/api/studies/duplicates", { backend: $("st-dup-backend").value, source: $("st-dup-source").value, fetch: $("st-dup-fetch").checked });
    out.textContent = "";
    out.appendChild(mk("p", `${j.n_images} chip${j.n_images === 1 ? "" : "s"} compared (${j.n_pairs} pairs); ${j.found.length} near-duplicate pair${j.found.length === 1 ? "" : "s"} found.`
      + (j.missing.length ? ` ${j.missing.length} site${j.missing.length === 1 ? " has" : "s have"} no saved picture and were not compared.` : ""),
      j.found.length ? "callout warn" : "callout info", { role: "status" }));
    if (j.synthetic) stNote(out, "These are synthetic demo scenes, so a result here says nothing about real places.", "callout info");
    if (j.found.length) out.appendChild(stTable("Near-duplicate pairs", ["Site A", "Site B", "Found as", "Shift (px)", "Correlation", "Similarity"],
      j.found.slice(0, 40).map((p) => [p.a, p.b, p.transform, p.shift.join(", "), num(p.ncc), num(p.ssim)])));
    if (j.missing.length && !$("st-dup-fetch").checked) stNote(out, "Tick the box above to download the missing pictures.");
    if (Object.keys(j.errors || {}).length) stNote(out, `${Object.keys(j.errors).length} picture(s) could not be downloaded.`, "callout warn");
    announce(`${j.found.length} near-duplicate pairs found.`);
  } catch (e) { stFail(out, e); }
}

async function stRunBenchmark() {
  const out = $("st-dup-out");
  out.textContent = "Running the self-test…";
  try {
    const j = await (await api("/api/studies/duplicates/benchmark?n_base=30&seed=0")).json();
    out.textContent = "";
    out.appendChild(mk("p", `Of ${Object.values(j.per_kind).reduce((a, v) => a + v.copies, 0)} made-up copies, ${pct(j.overall_detection_rate)} were found. Among ${j.unrelated_pairs_checked} pairs of unrelated pictures there were ${j.false_alarms} false alarm${j.false_alarms === 1 ? "" : "s"}.`, "callout info", { role: "status" }));
    out.appendChild(stTable("Detection by kind of copy (all pictures are generated, seed " + j.seed + ")", ["Kind of copy", "Copies", "Found", "Rate", "False alarms"],
      Object.entries(j.per_kind).map(([k, v]) => [k, v.copies, v.detected, pct(v.rate), v.false_alarms])));
  } catch (e) { stFail(out, e); }
}

// ------------------------------------------------------------------ domain shift

async function stRunShift() {
  const out = $("st-shift-out");
  out.textContent = "Working…";
  try {
    const a = $("st-shift-a").value, b = $("st-shift-b").value;
    if (a === b) throw new Error("Choose two different roles.");
    const j = await stPost("/api/studies/shift", { role_a: a, role_b: b });
    out.textContent = "";
    const r = j.against_random || {};
    if (r.observed_median_psi != null) {
      const bigger = r.observed_median_psi > r.random_split_median_psi_p95;
      out.appendChild(mk("p", `The typical shift between ${a} (${j.n_a} sites) and ${b} (${j.n_b} sites) is ${num(r.observed_median_psi, 3)}. Random splits of the same sizes give ${num(r.random_split_median_psi_mean, 3)} on average (95% under ${num(r.random_split_median_psi_p95, 3)}). `
        + (bigger ? "The two roles differ more than chance would explain." : "That is no more than chance would give."), bigger ? "callout warn" : "callout info", { role: "status" }));
    } else stNote(out, "Not enough sites with values to compare.", "callout warn");
    out.appendChild(stTable("Shift per feature, largest first", ["Feature", `Mean (${a})`, `Mean (${b})`, "PSI", "Reading", "KS statistic", "p value"],
      j.features.map((f) => [f.feature, num(f.mean_a, 3), num(f.mean_b, 3), num(f.psi, 3), f.psi_level, num(f.ks, 3), num(f.p_value, 4)])));
    stNote(out, "PSI under 0.1 is small, 0.1 to 0.25 moderate, above 0.25 large. With few sites, PSI is biased upwards, so read it against the random-split numbers.");
    announce("Shift comparison finished.");
  } catch (e) { stFail(out, e); }
}

// ------------------------------------------------------------------ certificate

async function stBuildCertificate() {
  const out = $("st-cert-out");
  out.textContent = "Working…";
  try {
    const end = $("st-cert-end").value, start = $("st-cert-start").value;
    const body = { target_column: $("st-cert-target").value || null, include_shift: true };
    if (end && start) body.time_info = { train_end: end, test_start: start };
    const j = await stPost("/api/studies/certificate", body);
    ST.cert = body;
    out.textContent = "";
    out.appendChild(mk("p", `Verdict: ${ST_WORD[j.verdict] || j.verdict}. ${j.checks.filter((c) => c.status === "pass").length} checks passed, ${j.checks.filter((c) => c.status === "fail").length} failed, ${j.not_run.length} not run.`,
      "callout " + (j.verdict === "pass" ? "info" : j.verdict === "fail" ? "bad" : "warn"), { role: "status" }));
    out.appendChild(stTable("Checks", ["Check", "Result", "What it found"], j.checks.map((c) => [c.title, stBadge(c.status), c.detail])));
    const mixed = (j.overlap_groups && j.overlap_groups.mixed_role_groups) || [];
    if (mixed.length) out.appendChild(stGroupTable("Groups of overlapping sites that are split between roles (fix these first)", mixed));
    stNote(out, "A pass means the checks that were run found nothing. A check that was not run says nothing either way. Roster fingerprint: " + j.roster_sha256.slice(0, 16) + "…");
    $("st-cert-dl").disabled = false;
    announce("Certificate built. Verdict: " + (ST_WORD[j.verdict] || j.verdict) + ".");
  } catch (e) { stFail(out, e); }
}

async function stDownloadCertificate() {
  try {
    const res = await api("/api/studies/certificate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...(ST.cert || {}), download: true }) });
    downloadText("split_certificate.json", await res.text(), "application/json");
    showToast("Certificate saved.", "ok");
  } catch (e) { showToast("Could not save the certificate: " + e.message, "err"); }
}

// ------------------------------------------------------------------ outcomes and forecast

async function stRefreshOutcomes() {
  try {
    const j = await (await api("/api/studies/outcomes")).json();
    ST.outcomes = j;
    $("st-out-summary").textContent = j.n_rows ? `${j.n_rows} rows loaded with ${Object.keys(j.numeric_columns).length} numeric columns: ${Object.keys(j.numeric_columns).join(", ")}.` : "No table loaded yet. Screening numbers in the site notes are still used.";
    const targets = Object.keys(j.numeric_columns).filter((c) => c === "yield" || c.startsWith("avail_") || c.startsWith("mean_"));
    if (j.numeric_columns.windows && j.numeric_columns.ok_windows && !targets.includes("yield")) targets.unshift("yield");
    const sel = $("st-fc-target");
    const keep = sel.value;
    sel.textContent = "";
    (targets.length ? targets : ["yield"]).forEach((t) => { const o = mk("option", t); o.value = t; sel.appendChild(o); });
    if (targets.includes(keep)) sel.value = keep;
    const cert = $("st-cert-target");
    const ck = cert.value;
    cert.textContent = "";
    const none = mk("option", "None"); none.value = ""; cert.appendChild(none);
    Object.keys(j.numeric_columns).filter((c) => c.startsWith("mean_") || c.startsWith("avail_") || c === "yield").forEach((c) => { const o = mk("option", c); o.value = c; cert.appendChild(o); });
    cert.value = [...cert.options].some((o) => o.value === ck) ? ck : "";
    const fs = $("st-fc-features");
    const feats = ["land_frac", "clear_frac", "fire_days", "aai_site", "no2_contrast", "co_contrast"];
    const checked = new Set([...fs.querySelectorAll("input:checked")].map((i) => i.value));
    const first = !fs.querySelector("input");
    fs.textContent = "";
    fs.appendChild(mk("legend", "Numbers to use"));
    feats.forEach((f) => {
      const l = mk("label", null, "chk");
      const i = mk("input", null, null, { type: "checkbox", value: f });
      i.checked = first ? true : checked.has(f);
      l.appendChild(i);
      l.appendChild(document.createTextNode(" " + f.replace(/_/g, " ")));
      fs.appendChild(l);
    });
  } catch (e) { $("st-out-summary").textContent = "Could not read the table state: " + e.message; }
}

async function stLoadOutcomes() {
  try {
    const text = await stLoadText($("st-out-file"), $("st-out-text"));
    const j = await stPost("/api/studies/outcomes", { csv: text });
    await stRefreshOutcomes();
    showToast(`Table loaded: ${j.n_rows} rows.`, "ok");
    announce(`Table loaded with ${j.n_rows} rows.`);
  } catch (e) { $("st-out-summary").textContent = ""; $("st-out-summary").appendChild(mk("span", friendlyError(e.message), "warn-text")); }
}

function stForecastBody(action) {
  return { action, target: $("st-fc-target").value || "yield", region_correction: $("st-fc-region").checked,
           features: [...$("st-fc-features").querySelectorAll("input:checked")].map((i) => i.value) };
}

function stScatter(sites, target) {
  const W = 360, H = 300, P = 40;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "st-chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Chart of the forecast against the observed ${target.replace(/_/g, " ")} for each site. Points near the diagonal line are good forecasts. The table below has the same numbers.`);
  const sx = (v) => P + v * (W - 2 * P), sy = (v) => H - P - v * (H - 2 * P);
  const add = (tag, attrs) => { const n = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); svg.appendChild(n); return n; };
  add("line", { x1: P, y1: sy(0), x2: W - P, y2: sy(0), class: "axis" });
  add("line", { x1: P, y1: sy(0), x2: P, y2: sy(1), class: "axis" });
  add("line", { x1: sx(0), y1: sy(0), x2: sx(1), y2: sy(1), class: "diag" });
  for (const t of [0, 0.5, 1]) {
    const a = add("text", { x: sx(t), y: H - P + 16, "text-anchor": "middle", class: "tick" }); a.textContent = t;
    const b = add("text", { x: P - 6, y: sy(t) + 4, "text-anchor": "end", class: "tick" }); b.textContent = t;
  }
  const lx = add("text", { x: W / 2, y: H - 6, "text-anchor": "middle", class: "lab" }); lx.textContent = "Forecast";
  const ly = add("text", { x: 12, y: H / 2, "text-anchor": "middle", class: "lab", transform: `rotate(-90 12 ${H / 2})` }); ly.textContent = "Observed";
  for (const s of sites) {
    add("line", { x1: sx(s.low), x2: sx(s.high), y1: sy(s.observed), y2: sy(s.observed), class: "ival" });
    add("circle", { cx: sx(s.forecast), cy: sy(s.observed), r: 3, class: "pt" });
  }
  return svg;
}

async function stCheckForecast() {
  const out = $("st-fc-out");
  out.textContent = "Working…";
  $("st-fc-chart").textContent = "";
  try {
    const j = await stPost("/api/studies/forecast", stForecastBody("validate"));
    out.textContent = "";
    if (j.warning) out.appendChild(mk("p", j.warning, "callout warn"));
    if (j.dropped_features && j.dropped_features.length) out.appendChild(mk("p", `Left out because fewer than half of the sites have a value: ${j.dropped_features.join(", ")}.`, "hint-small"));
    out.appendChild(mk("p", `Held out clusters of nearby sites, the forecast is off by ${num(j.mae, 3)} on average. Guessing the average would be off by ${num(j.mae_baseline, 3)}. That is ${pct(j.skill)} better. `
      + `${pct(j.interval_coverage)} of sites fell inside their ${pct(j.interval)} interval.`, j.skill > 0.1 ? "callout info" : "callout warn", { role: "status" }));
    out.appendChild(stTable("How well the forecast does on sites it has not seen", ["Measure", "Value"], [
      ["Sites", j.n_sites], ["Groups of nearby sites held out together", j.n_clusters], ["Average error (forecast)", num(j.mae, 4)], ["Average error (guess the average)", num(j.mae_baseline, 4)],
      ["Share of the baseline error removed", pct(j.skill)], ["R squared", num(j.r2, 3)], ["Rank correlation", num(j.spearman, 3)],
      ["Interval coverage", pct(j.interval_coverage)], ["Numbers used", j.features.join(", ")], ["Region correction", j.region_correction ? "on" : "off"]]));
    $("st-fc-chart").appendChild(stScatter(j.sites, j.target));
    const det = mk("details", null, "help-expert");
    det.appendChild(mk("summary", "Show the numbers behind the chart"));
    det.appendChild(stTable("Observed and forecast per site", ["Site", "Observed", "Forecast", "Interval low", "Interval high"], j.sites.map((s) => [s.id, num(s.observed, 3), num(s.forecast, 3), num(s.low, 3), num(s.high, 3)])));
    $("st-fc-chart").appendChild(det);
    if (j.effort_saved) {
      out.appendChild(stTable("What dropping the lowest-forecast sites would have saved", ["Sites dropped", "Share of windows saved", "Share of samples lost"],
        j.effort_saved.rows.map((r) => [`${pct(r.drop_share_of_sites)} (${r.sites_dropped})`, pct(r.windows_saved_share, 1), pct(r.samples_lost_share, 1)])));
      stNote(out, j.effort_saved.note);
    }
    announce(`Forecast checked. ${pct(j.skill)} better than guessing the average.`);
  } catch (e) { stFail(out, e); }
}

async function stCompareModels() {
  const out = $("st-fc-out");
  out.textContent = "Working. This repeats the check once for every number, so it takes longer with many sites…";
  try {
    const j = await stPost("/api/studies/forecast", stForecastBody("compare"));
    out.textContent = "";
    if (j.reading) out.appendChild(mk("p", j.reading + ".", "callout info", { role: "status" }));
    out.appendChild(stTable("Held-out error of simpler and larger models (smaller is better)", ["Model", "Average error", "Share of baseline error removed", "Rank correlation"],
      j.models.map((m) => [m.model, num(m.mae, 4), pct(m.skill), m.spearman == null ? "n/a" : num(m.spearman, 3)])));
    stNote(out, "Every row uses the same held-out check as the forecast itself. If one number does as well as all of them, collect only that one.");
    announce("Model comparison finished.");
  } catch (e) { stFail(out, e); }
}

async function stFitForecast() {
  const out = $("st-fc-out");
  const box = $("st-fc-pred");
  box.textContent = "Working…";
  try {
    const m = await stPost("/api/studies/forecast", stForecastBody("fit"));
    const j = await (await api("/api/studies/forecast/predictions")).json();
    ST.pred = j;
    box.textContent = "";
    box.appendChild(mk("p", `The forecast is fitted on ${m.n_sites} sites and used for all ${Object.keys(j.predictions).length}. The ones with the lowest forecast are listed first, because those are the sites to look at before spending collection time.`, "callout info", { role: "status" }));
    const rows = Object.entries(j.predictions).sort((a, b) => a[1].forecast - b[1].forecast);
    box.appendChild(stTable("Lowest forecasts (first 25)", ["Site", "Forecast", "Interval", "Missing numbers"],
      rows.slice(0, 25).map(([id, p]) => [id, num(p.forecast, 3), `${num(p.low, 2)} to ${num(p.high, 2)}`, p.missing_features.join(", ") || "none"])));
    const dl = mk("button", "Download all forecasts (CSV)", null, { type: "button" });
    dl.addEventListener("click", () => {
      const lines = ["id,forecast,low,high,region_adjustment,missing"].concat(rows.map(([id, p]) => [id, p.forecast, p.low, p.high, p.region_adjustment, p.missing_features.join(" ")].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")));
      downloadText("forecasts.csv", lines.join("\n"), "text/csv");
    });
    box.appendChild(dl);
    announce("Forecast fitted for every site.");
  } catch (e) { stFail(box, e); }
}

// ------------------------------------------------------------------ registries and grounding

async function stRefreshRegistries() {
  const ul = $("st-reg-list");
  try {
    const j = await (await api("/api/studies/registries")).json();
    ul.textContent = "";
    if (!j.registries.length) ul.appendChild(mk("li", "No registry loaded yet.", "muted"));
    for (const r of j.registries) {
      const li = mk("li", `${r.name}: ${r.n_entries} entries${r.skipped ? ` (${r.skipped} skipped)` : ""}. Licence: ${r.licence || "not written down"}`);
      const b = mk("button", "Remove", null, { type: "button", "aria-label": "Remove registry " + r.name });
      b.addEventListener("click", async () => { await api("/api/studies/registry/" + encodeURIComponent(r.name), { method: "DELETE" }); stRefreshRegistries(); });
      li.appendChild(document.createTextNode(" "));
      li.appendChild(b);
      ul.appendChild(li);
    }
  } catch (e) { ul.textContent = "Could not read the registries: " + e.message; }
}

async function stAddRegistry() {
  try {
    const text = await stLoadText($("st-reg-file"), $("st-reg-text"));
    const name = $("st-reg-name").value.trim() || ($("st-reg-file").files[0] ? $("st-reg-file").files[0].name.replace(/\.[^.]+$/, "") : "registry");
    const j = await stPost("/api/studies/registry", { name, text, format: $("st-reg-format").value || null, licence: $("st-reg-licence").value.trim() });
    showToast(`Registry "${name}" added: ${j.n_entries} entries.`, "ok");
    await stRefreshRegistries();
  } catch (e) { showToast("Could not add the registry: " + e.message, "err"); }
}

async function stFetchWikidata() {
  if (!$("st-wd-confirm").checked) { showToast("Tick the box to confirm that you want to go online.", "warn"); return; }
  const ids = $("st-wd-classes").value.split(/[,\s]+/).filter(Boolean);
  try {
    const j = await stPost("/api/studies/registry/wikidata", { class_ids: ids, country: $("st-wd-country").value.trim() || null, confirm: true, name: "wikidata" });
    showToast(`Wikidata: ${j.n_entries} entries.`, "ok");
    await stRefreshRegistries();
  } catch (e) { showToast("Wikidata lookup failed: " + e.message, "err"); }
}

const GR_ORDER = { disagree: 0, differ: 1, not_found: 2, agree: 3 };

async function stCompareRegistries() {
  const out = $("st-gr-out");
  out.textContent = "Working…";
  try {
    const j = await stPost("/api/studies/grounding", { use_original: $("st-gr-orig").checked });
    out.textContent = "";
    const c = j.counts;
    out.appendChild(mk("p", `${c.agree} site${c.agree === 1 ? "" : "s"} agree with a registry (within 2 km), ${c.differ} differ a little (2 to 5 km), ${c.disagree} disagree (over 5 km) and ${c.not_found} were not found.`,
      c.disagree ? "callout warn" : "callout info", { role: "status" }));
    const rows = j.sites.slice().sort((a, b) => GR_ORDER[a.status] - GR_ORDER[b.status]).slice(0, 60).map((r) => {
      const m = r.matches.find((x) => x.matched);
      const go = mk("button", "Show site", null, { type: "button", "aria-label": "Show site " + r.id });
      go.addEventListener("click", () => { $("studies-dialog").close(); selectSite(r.id); });
      return [r.id, stBadge(r.status), m ? `${m.entry.name} (${m.source})` : "none", m ? num(m.distance_km, 1) + " km" : "n/a", go];
    });
    out.appendChild(stTable("Sites, with the most different first (first 60)", ["Site", "Result", "Registry entry", "Distance", ""], rows));
    stNote(out, "The tool never moves a site from this list. Open the site, look at the picture, and move it yourself if the registry is right.");
    announce(`${c.disagree} sites disagree with the registries.`);
  } catch (e) { stFail(out, e); }
}

async function stEvaluateGrounding() {
  const out = $("st-gr-eval-out");
  out.textContent = "Working…";
  try {
    const j = await stPost("/api/studies/grounding/evaluate", {});
    out.textContent = "";
    const row = (name, s) => [name, s.n, num(s.median_km, 2), pct(s.within_1km), pct(s.within_2km), pct(s.within_5km), num(s.max_km, 1)];
    out.appendChild(stTable(`Error against the verified centres (${j.n_verified_sites} verified sites with a recalled position; ${j.n_with_registry_match} matched a registry)`,
      ["Position used", "Sites", "Median error (km)", "Within 1 km", "Within 2 km", "Within 5 km", "Worst (km)"], [
        row("Recalled position", j.recalled), row("Recalled, matched sites only", j.recalled_on_matched_sites), row("Registry, matched sites only", j.registry_on_matched_sites),
        row("Registry when matched, else recalled", j.combined_policy)]));
    if (j.disagreement_predicts_big_error_auc != null) stNote(out, `When the recalled and registry positions disagree, how well does that predict a recalled error over ${j.big_error_km} km? Area under the curve ${num(j.disagreement_predicts_big_error_auc, 2)} (0.5 means not at all, 1 means perfectly).`);
    stNote(out, "This measures how good the starting coordinates were. If they came from memory of a person or a model, it measures that memory.");
    announce("Error measured against verified centres.");
  } catch (e) { stFail(out, e); }
}

// ------------------------------------------------------------------ placement

function stRefreshPlacementSite() {
  const s = sitesDoc && activeId ? sitesDoc.sites.find((x) => x.id === activeId) : null;
  $("st-pl-site").textContent = s ? `Open site: ${s.name || s.id} (box ${s.box_km} km).` : "Open a site first (choose one in the list).";
  $("st-pl-run").disabled = !s;
}

function stLineChart(title, xs, series) {
  const W = 360, H = 240, P = 42;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "st-chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", title + ". The table above has the same numbers.");
  const add = (tag, attrs, text) => { const n = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (text) n.textContent = text; svg.appendChild(n); return n; };
  const maxX = Math.max(...xs);
  const sx = (v) => P + (v / maxX) * (W - 2 * P), sy = (v) => H - P - Math.min(Math.max(v, 0), 1) * (H - 2 * P);
  add("line", { x1: P, y1: sy(0), x2: W - P, y2: sy(0), class: "axis" });
  add("line", { x1: P, y1: sy(0), x2: P, y2: sy(1), class: "axis" });
  for (const t of [0, 0.5, 1]) add("text", { x: P - 6, y: sy(t) + 4, "text-anchor": "end", class: "tick" }, t);
  xs.forEach((x) => add("text", { x: sx(x), y: H - P + 16, "text-anchor": "middle", class: "tick" }, x));
  add("text", { x: W / 2, y: H - 6, "text-anchor": "middle", class: "lab" }, "Shift (km)");
  series.forEach((s, k) => {
    const pts = xs.map((x, i) => (s.values[i] == null ? null : `${sx(x)},${sy(s.values[i])}`)).filter(Boolean);
    add("polyline", { points: pts.join(" "), class: "line l" + k, fill: "none" });
    xs.forEach((x, i) => { if (s.values[i] != null) add("circle", { cx: sx(x), cy: sy(s.values[i]), r: 3, class: "dot l" + k }); });
    add("text", { x: W - P, y: P - 8 + k * 14, "text-anchor": "end", class: "lab l" + k }, s.name);
  });
  return svg;
}

async function stRunPlacement() {
  const out = $("st-pl-out");
  out.textContent = "Working. Downloading a wider picture can take up to a minute with live imagery…";
  $("st-pl-chart").textContent = "";
  try {
    const distances = [...document.querySelectorAll('input[name="st-pl-d"]:checked')].map((i) => +i.value);
    if (!distances.length) throw new Error("Choose at least one shift distance.");
    const bearings = $("st-pl-dirs").value === "4" ? [0, 90, 180, 270] : [0, 45, 90, 135, 180, 225, 270, 315];
    const targets = [...document.querySelectorAll('input[name="st-pl-t"]:checked')].map((i) => i.value);
    const j = await stPost("/api/studies/sensitivity", { site_id: activeId, backend: $("st-pl-backend").value, distances, bearings, kind: $("st-pl-kind").value, targets });
    out.textContent = "";
    const tol = j.tolerance_km;
    const small = Math.min(...j.by_distance.map((b) => b.distance_km));
    const keep = tol.keeps_facility > 0 ? `shifting it by up to ${tol.keeps_facility} km keeps at least half of the facility-like pixels in view`
      : `even the smallest tested shift (${small} km) loses more than half of the facility-like pixels`;
    const corr = tol.picture_correlation_0_8 > 0 ? `The picture stays well correlated (above 0.8) up to ${tol.picture_correlation_0_8} km.`
      : `The picture is already less than 0.8 correlated at the smallest tested shift (${small} km).`;
    out.appendChild(mk("p", `For this ${j.box_km} km box, ${keep} (median over ${bearings.length} directions). ${corr} The wider picture was ${j.context_km} km across.`, "callout info", { role: "status" }));
    if (j.synthetic) stNote(out, "These are synthetic demo scenes. Use them to learn the tool, not to learn about a place.", "callout info");
    out.appendChild(stTable("Change of the chip when the box is shifted (median over directions)", ["Shift (km)", "Box overlap", "Facility signal kept", "Picture correlation", "Difference (normalised)", "Directions that lose the facility"],
      j.by_distance.map((b) => [b.distance_km, pct(b.median_box_overlap), pct(b.median_retained), num(b.median_ncc, 2), num(b.median_nrmse, 2), pct(b.share_missing_facility)])));
    if (j.tolerance_sweep) {
      const sw = j.tolerance_sweep;
      out.appendChild(stTable("How the tolerance depends on the threshold you choose (largest tested shift, km)", ["Rule", "Loose", "Middle", "Strict"], [
        ["Facility signal kept at least 25%, 50%, 75%", sw.keeps_facility["0.25"], sw.keeps_facility["0.5"], sw.keeps_facility["0.75"]],
        ["Picture correlation at least 0.5, 0.8, 0.9", sw.picture_correlation["0.5"], sw.picture_correlation["0.8"], sw.picture_correlation["0.9"]]]));
    }
    if (j.natural_change) stNote(out, `For comparison, the difference between two dates at the original position is ${num(j.natural_change.nrmse, 2)} (correlation ${num(j.natural_change.ncc, 2)}).`);
    $("st-pl-chart").appendChild(stLineChart("Facility signal kept and picture correlation against shift", j.by_distance.map((b) => b.distance_km),
      [{ name: "Signal kept", values: j.by_distance.map((b) => b.median_retained) }, { name: "Correlation", values: j.by_distance.map((b) => b.median_ncc) }]));
    if (j.targets) {
      for (const [t, v] of Object.entries(j.targets)) {
        if (!v.rows) { stNote(out, `${t}: ${v.note || "no result"}`, "callout warn"); continue; }
        const sw = v.tolerance_sweep ? ` (within 0.1, 0.25, 0.5 of the spread: ${v.tolerance_sweep["0.1"]}, ${v.tolerance_sweep["0.25"]}, ${v.tolerance_sweep["0.5"]} km)` : "";
        out.appendChild(stTable(`${t}: change of the label value when the window moves (tolerance ${v.tolerance_km} km${sw})`, ["Shift (km)", "Median change", "Change / day-to-day spread", "Change / standard error", "Shifts above 2 standard errors"],
          v.rows.map((r) => [r.distance_km, num(r.median_abs_change, 3), num(r.change_over_spread, 2), num(r.change_over_se, 1), pct(r.share_above_2se)])));
      }
      if (j.targets_synthetic) stNote(out, "The gas values are synthetic.", "callout info");
      stNote(out, "The tolerance is the largest tested shift whose typical change stays within a quarter of the day-to-day spread.");
    }
    announce("Placement study finished.");
  } catch (e) { stFail(out, e); }
}

// ------------------------------------------------------------------ wiring

function wireStudies() {
  stWireTabs();
  $("tool-studies").addEventListener("click", () => { toggleToolsMenu(false); openStudies(); });
  $("st-groups-run").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stFindGroups));
  $("st-groups-apply").addEventListener("click", stApplyGroups);
  $("st-dup-run").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stRunDuplicates));
  $("st-dup-bench").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stRunBenchmark));
  $("st-shift-run").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stRunShift));
  $("st-cert-run").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stBuildCertificate));
  $("st-cert-dl").addEventListener("click", stDownloadCertificate);
  $("st-out-load").addEventListener("click", stLoadOutcomes);
  $("st-out-demo").addEventListener("click", async () => {
    try { $("st-out-text").value = await (await api("/api/studies/demo/outcomes")).text(); $("st-out-file").value = ""; await stLoadOutcomes(); }
    catch (e) { showToast("Could not load the demo table: " + e.message, "err"); }
  });
  $("st-reg-demo").addEventListener("click", async () => {
    try { $("st-reg-text").value = await (await api("/api/studies/demo/registry")).text(); $("st-reg-file").value = ""; $("st-reg-name").value = "demo-registry"; $("st-reg-licence").value = "synthetic demo data, no licence needed"; await stAddRegistry(); }
    catch (e) { showToast("Could not load the demo registry: " + e.message, "err"); }
  });
  $("st-out-clear").addEventListener("click", async () => { await api("/api/studies/outcomes", { method: "DELETE" }); stRefreshOutcomes(); });
  $("st-fc-check").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stCheckForecast));
  $("st-fc-compare").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stCompareModels));
  $("st-fc-fit").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stFitForecast));
  $("st-reg-add").addEventListener("click", stAddRegistry);
  $("st-wd-run").addEventListener("click", stFetchWikidata);
  $("st-gr-run").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stCompareRegistries));
  $("st-gr-eval").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stEvaluateGrounding));
  $("st-pl-run").addEventListener("click", (e) => stBusy(e.currentTarget, "Working…", stRunPlacement));
}
