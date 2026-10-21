// In-page accessibility audit for TrigPoint. Paste into the browser console (or run it with the browser tool).
// It reports: interactive elements without an accessible name, targets smaller than 24 by 24 CSS pixels,
// text with too little colour contrast in the current theme, duplicate ids, and form controls without a label.
// Run it once per theme:  auditPage("dark"), auditPage("light"), auditPage("hc").
// It cannot judge reading order, what a screen reader says, or contrast over images (the map is skipped).

(function () {
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return { r: 0, g: 0, b: 0, a: 0 };
    const p = m[1].split(/[,\s/]+/).filter(Boolean).map(parseFloat); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const blend = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

  function bgOf(el) {
    const stack = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage !== "none") return null;                  // gradient or image: cannot judge
      const c = parse(cs.backgroundColor);
      if (c.a > 0) { stack.push(c); if (c.a >= 1) break; }
    }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = stack.length - 1; i >= 0; i--) base = blend(stack[i], base);
    return base;
  }
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
  const skip = (el) => el.closest("#map, .leaflet-container, .sr-only, [hidden]") || (el.closest("details:not([open])") && !el.matches("summary") && !el.closest("summary"));

  function nameOf(el) {
    const al = el.getAttribute("aria-label"); if (al && al.trim()) return al.trim();
    const lb = el.getAttribute("aria-labelledby");
    if (lb) { const t = lb.split(/\s+/).map((i) => (document.getElementById(i) || {}).textContent || "").join(" ").trim(); if (t) return t; }
    if (el.labels && el.labels.length) { const t = [...el.labels].map((l) => l.textContent).join(" ").trim(); if (t) return t; }
    if (el.tagName === "IMG") return (el.getAttribute("alt") || "").trim();
    const t = (el.textContent || "").replace(/\s+/g, " ").trim(); if (t) return t;
    return (el.getAttribute("title") || "").trim();
  }

  window.auditPage = function (theme) {
    // colours are read as they will settle, so switch transitions off and force a style recalculation first
    if (!document.getElementById("audit-no-motion")) {
      const st = document.createElement("style");
      st.id = "audit-no-motion";
      st.textContent = "*, *::before, *::after { transition: none !important; animation: none !important; }";
      document.head.appendChild(st);
    }
    if (theme) document.documentElement.dataset.theme = theme;
    void document.body.offsetHeight;
    const out = { theme: document.documentElement.dataset.theme, noName: [], small: [], lowContrast: [], dupIds: [], noLabel: [], checked: 0 };
    const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], [role=checkbox], [tabindex]:not([tabindex="-1"])';
    document.querySelectorAll(sel).forEach((el) => {
      if (!visible(el) || skip(el) || el.disabled) return;
      out.checked++;
      if (!nameOf(el)) out.noName.push(el.outerHTML.slice(0, 90));
      let r = el.getBoundingClientRect();
      if ((el.type === "checkbox" || el.type === "radio") && el.labels && el.labels[0]) {      // the label is part of the target
        const lr = el.labels[0].getBoundingClientRect();
        r = { width: Math.max(r.width, lr.width), height: Math.max(r.height, lr.height) };
      }
      const inline = el.tagName === "A" && getComputedStyle(el).display === "inline";
      if (!inline && (r.width < 23.5 || r.height < 23.5) && !(el.type === "range")) out.small.push(`${el.tagName}#${el.id || ""} ${Math.round(r.width)}x${Math.round(r.height)} "${(nameOf(el) || "").slice(0, 30)}"`);
    });
    document.querySelectorAll("input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea").forEach((el) => {
      if (!visible(el) || skip(el)) return;
      if (!nameOf(el)) out.noLabel.push(el.id || el.outerHTML.slice(0, 60));
    });
    const ids = {};
    document.querySelectorAll("[id]").forEach((e) => { ids[e.id] = (ids[e.id] || 0) + 1; });
    out.dupIds = Object.entries(ids).filter(([, n]) => n > 1).map(([k]) => k);
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const seen = new Set();
    let n;
    while ((n = walker.nextNode())) {
      const el = n.parentElement;
      if (!el || seen.has(el) || !n.textContent.trim() || !visible(el) || skip(el) || el.closest("script, style, option, dialog:not([open])")) continue;
      if (el.closest("button, input, select, textarea")?.disabled) continue;
      seen.add(el);
      const cs = getComputedStyle(el);
      const bg = bgOf(el); if (!bg) continue;
      let fg = parse(cs.color);
      fg = blend({ ...fg, a: fg.a * parseFloat(cs.opacity || 1) }, bg);
      const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700;
      const need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
      const cr = ratio(fg, bg);
      if (cr < need) out.lowContrast.push(`${cr.toFixed(2)} (need ${need}) ${el.tagName}.${(el.className || "").toString().slice(0, 25)} "${n.textContent.trim().slice(0, 30)}"`);
    }
    return out;
  };
})();
