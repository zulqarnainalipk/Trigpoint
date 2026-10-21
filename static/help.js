// TrigPoint help layer: a "?" button beside every feature opens a short, plain-language explanation.
// All text comes from /api/help (help_content.json), so the tool and the written guide cannot disagree.
// Text is always inserted with textContent, never as HTML.

"use strict";

const HelpCenter = (() => {
  const state = { data: null, views: null, ready: null, opener: null, current: null };

  function load() {
    if (!state.ready) {
      state.ready = Promise.all([
        fetch("/api/help").then((r) => r.json()),
        fetch("/api/views").then((r) => r.json()).catch(() => null),
      ]).then(([h, v]) => { state.data = h; state.views = v; refreshLabels(); return state; })
        .catch(() => { state.ready = null; return state; });
    }
    return state.ready;
  }

  function entry(key) {
    if (!state.data) return null;
    if (state.data.features[key]) return { key, ...state.data.features[key] };
    const v = state.views;
    if (v && key.startsWith("index:") && v.indices[key.slice(6)]) {
      const name = key.slice(6), i = v.indices[name];
      return { key, area: "Imagery", title: `Index ${name.toUpperCase()}`, short: i.description,
               what: i.description, why: "Look at this view when you need to tell this kind of surface from the rest of the box.",
               how: ["Choose it in the Index list. The picture updates at once."],
               works: "One number per pixel from the band values, limited to a fixed range, then drawn on a blue scale between the 2nd and 98th percentile.",
               limits: "The scale is relative to the picture. Values differ between places and days.",
               expert: { formula: i.formula } };
    }
    if (v && key.startsWith("composite:") && v.composites[key.slice(10)]) {
      const name = key.slice(10), c = v.composites[name];
      return { key, area: "Imagery", title: `View: ${name.replace(/_/g, " ")}`, short: c.description, what: c.description,
               why: "Different band combinations show different things. Switch views to place the centre and box with confidence.",
               how: ["Press the view button. The picture updates at once."],
               works: `Bands ${c.bands.join(", ")} are shown as red, green and blue and stretched for display.`,
               limits: "The colours are display colours, not measurements.", expert: { bands: c.bands.join(", ") } };
    }
    return null;
  }

  function title(key) {
    const e = entry(key);
    return e ? e.title : "this feature";
  }

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // HTML for a help button (the key is escaped; the label is filled in once the help text has loaded)
  function button(key, extraClass = "") {
    return `<button type="button" class="help-btn ${extraClass}" data-help="${esc(key)}" aria-haspopup="dialog" ` +
      `aria-label="Explain this feature" title="What is this?"><span aria-hidden="true">?</span></button>`;
  }

  function refreshLabels(root = document) {
    root.querySelectorAll("[data-help]").forEach((b) => {
      const e = entry(b.dataset.help);
      if (e) { b.setAttribute("aria-label", `Explain: ${e.title}`); b.title = `What is this? ${e.title}`; }
    });
  }

  function el(tag, text, cls) {
    const n = document.createElement(tag);
    if (text != null) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }

  function section(parent, heading, body) {
    if (!body || (Array.isArray(body) && !body.length)) return;
    parent.appendChild(el("h3", heading));
    if (Array.isArray(body)) {
      const ol = el("ol", null, "help-steps");
      body.forEach((s) => ol.appendChild(el("li", s)));
      parent.appendChild(ol);
    } else {
      parent.appendChild(el("p", body));
    }
  }

  function render(key) {
    const e = entry(key);
    const body = document.getElementById("fh-body");
    body.textContent = "";
    if (!e) {
      body.appendChild(el("p", "There is no explanation for this item yet."));
      document.getElementById("fh-title").textContent = "Help";
      return;
    }
    document.getElementById("fh-title").textContent = e.title;
    document.getElementById("fh-area").textContent = e.area || "";
    body.appendChild(el("p", e.short, "help-lead"));
    section(body, "What it is", e.what);
    section(body, "Why it matters", e.why);
    section(body, "How to use it", e.how);
    section(body, "How it works", e.works);
    section(body, "What it cannot do", e.limits);
    if (e.expert) {
      const d = el("details", null, "help-expert");
      d.appendChild(el("summary", "Expert details"));
      const dl = el("dl");
      Object.entries(e.expert).forEach(([k, v]) => { dl.appendChild(el("dt", k)); const dd = el("dd"); dd.appendChild(el("code", String(v))); dl.appendChild(dd); });
      d.appendChild(dl);
      body.appendChild(d);
    }
    const same = Object.entries(state.data.features).filter(([k, f]) => f.area === e.area && k !== key).slice(0, 5);
    if (same.length) {
      const more = el("div", null, "help-more");
      more.appendChild(el("h3", `More in "${e.area}"`));
      const ul = el("ul");
      same.forEach(([k, f]) => {
        const li = el("li"), b = el("button", f.title, "link-btn");
        b.type = "button";
        b.addEventListener("click", () => { state.current = k; render(k); document.getElementById("fh-title").focus(); });
        li.appendChild(b);
        ul.appendChild(li);
      });
      more.appendChild(ul);
      body.appendChild(more);
    }
  }

  async function open(key, opener) {
    await load();
    const d = document.getElementById("feature-help");
    state.opener = opener || document.activeElement;
    state.current = key;
    render(key);
    if (!d.open) d.showModal();
    const t = document.getElementById("fh-title");
    t.setAttribute("tabindex", "-1");
    t.focus();
  }

  function closeHelp() {
    const d = document.getElementById("feature-help");
    if (d.open) d.close();
  }

  // ---- feature guide: a searchable list of everything ----
  function guideItems(q) {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    const out = [];
    for (const [key, f] of Object.entries(state.data.features)) {
      const hay = [f.title, f.short, f.what, f.why, f.area, ...(f.how || [])].join(" ").toLowerCase();
      if (words.every((w) => hay.includes(w))) out.push([key, f]);
    }
    return out;
  }

  function renderGuide() {
    const q = document.getElementById("guide-q").value;
    const list = document.getElementById("guide-list");
    list.textContent = "";
    const items = guideItems(q);
    document.getElementById("guide-count").textContent = q
      ? `${items.length} result${items.length === 1 ? "" : "s"} for "${q}"` : `${items.length} features`;
    if (!items.length) {
      list.appendChild(el("p", "Nothing matches. Try a shorter word, for example flare, grid or export.", "muted"));
      return;
    }
    for (const area of state.data.areas) {
      const inArea = items.filter(([, f]) => f.area === area);
      if (!inArea.length) continue;
      list.appendChild(el("h3", area));
      const ul = el("ul", null, "guide-ul");
      inArea.forEach(([key, f]) => {
        const li = el("li"), b = el("button", null, "guide-item");
        b.type = "button";
        b.appendChild(el("b", f.title));
        b.appendChild(el("span", f.short, "muted"));
        b.addEventListener("click", () => open(key, b));
        li.appendChild(b);
        ul.appendChild(li);
      });
      list.appendChild(ul);
    }
  }

  async function openGuide() {
    await load();
    if (!state.data) { showToast("The help text could not be loaded.", "err"); return; }
    const d = document.getElementById("guide-dialog");
    renderGuide();
    if (!d.open) d.showModal();
    document.getElementById("guide-q").focus();
  }

  function wire() {
    document.addEventListener("click", (e) => {
      const b = e.target.closest("[data-help]");
      if (!b) return;
      e.preventDefault();
      e.stopPropagation();                      // a "?" inside a section title must not fold the section
      open(b.dataset.help, b);
    }, true);
    document.getElementById("feature-help").addEventListener("close", () => {
      const o = state.opener;
      if (o && document.contains(o) && typeof o.focus === "function") o.focus();
    });
    document.getElementById("guide-q").addEventListener("input", renderGuide);
    const g = document.getElementById("btn-guide");
    if (g) g.addEventListener("click", openGuide);
    const g2 = document.getElementById("help-guide");
    if (g2) g2.addEventListener("click", () => { document.getElementById("help-dialog").close(); openGuide(); });
    load();
  }

  return { load, entry, button, refreshLabels, open, openGuide, wire, closeHelp, state };
})();

function helpBtnHtml(key, extraClass) { return HelpCenter.button(key, extraClass); }
