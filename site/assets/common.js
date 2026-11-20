/* Shared helpers for every Ripple page. Data comes from data/data.js (window.RIPPLE_DATA). */
(function () {
  "use strict";
  const D = window.RIPPLE_DATA || { nodes: {}, links: [], events: [] };
  // Once real links exist, maps and company pages show only real links. SAMPLE links then only
  // appear inside SAMPLE event pages (which need them for their ripple).
  const realLinks = (D.links || []).filter((l) => !l.is_sample);
  D.mapLinks = realLinks.length ? realLinks : (D.links || []);

  const LAYER_LABEL = { memory: "Memory", packaging: "Packaging & chipmaking", power: "Power & cooling", materials: "Materials", buyers: "Buyers" };
  const KIND_LABEL = { company: "Company", place: "Place", material: "Material", part: "Part" };
  const TYPE_LABEL = { disruption: "Disruption", shortage: "Shortage", new_contract: "New contract", policy: "Policy", price_spike: "Price spike", capacity_change: "Capacity change" };
  const LINK_VERB = { supplies: "supplies", makes_in: "makes in", uses: "uses", produces: "produces" };
  const STALE_DAYS = 365;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const qs = (sel, root) => (root || document).querySelector(sel);
  const param = (name) => new URLSearchParams(location.search).get(name);
  const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function layerVar(n) {
    if (!n) return "--layer-place";
    if (n.kind === "company") return "--layer-" + (n.layer || "buyers");
    return n.kind === "place" ? "--layer-place" : "--layer-materials";
  }
  function dirVar(dir) { return "--" + (dir === "helped" ? "helped" : dir === "unclear" ? "unclear" : "hurt"); }

  const ICONS = {
    hurt: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3v9M4 8.5L8 12.5 12 8.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    helped: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 13V4M4 7.5L8 3.5 12 7.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    unclear: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M5.5 8h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  };
  const DIR_WORD = { hurt: "Hurt", helped: "Helped", unclear: "Unclear" };

  function dirMark(dir) {
    const d = DIR_WORD[dir] ? dir : "unclear";
    return `<span class="dir dir-${d}">${ICONS[d]}${DIR_WORD[d]}</span>`;
  }
  function node(id) { return D.nodes[id] || { id, name: id, kind: "place" }; }
  function nodeUrl(id) { return "company.html?id=" + encodeURIComponent(id); }
  function badge(id) {
    const n = node(id);
    const label = n.ticker || n.name;
    return `<span class="badge kind-${esc(n.kind)}" style="--layer-color: var(${layerVar(n)})" title="${esc(n.name)}">${esc(label)}</span>`;
  }
  function severityBar(sev) {
    const color = sev >= 4 ? "var(--hurt)" : sev === 3 ? "var(--unclear)" : "var(--accent)";
    let cells = "";
    for (let i = 1; i <= 5; i++) cells += `<i class="${i <= sev ? "on" : ""}"></i>`;
    return `<span class="sev" style="--sev-color:${color}" aria-label="Severity ${sev} of 5"><span class="sev-bar">${cells}</span>${sev}/5</span>`;
  }
  function fmtDate(s) {
    if (!s) return "—";
    const d = new Date(s.length === 7 ? s + "-01" : s);
    if (isNaN(d)) return s;
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
  }
  function daysSince(s) { const d = new Date(s); return isNaN(d) ? null : Math.floor((Date.now() - d) / 864e5); }
  function isStale(s) { const n = daysSince(s); return n != null && n > STALE_DAYS; }
  function pct(v) { return v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(1) + "%"; }

  /* Sparkline of the stock move after an event, from the follow-up log (0 → 1d → 1w → 1m). */
  function sparkline(followups) {
    const keys = ["1d", "1w", "1m"].filter((k) => followups && followups[k] != null);
    if (!keys.length) return "";
    const vals = [0].concat(keys.map((k) => followups[k]));
    const w = 90, h = 26, max = Math.max(1, ...vals.map(Math.abs));
    const pts = vals.map((v, i) => [(i / (vals.length - 1)) * w, h / 2 - (v / max) * (h / 2 - 2)]);
    const last = vals[vals.length - 1];
    const color = last >= 0 ? "var(--helped)" : "var(--hurt)";
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    return `<span class="spark" title="Stock move vs its sector since the event"><svg viewBox="0 0 ${w} ${h}" aria-hidden="true">
      <line x1="0" x2="${w}" y1="${h / 2}" y2="${h / 2}" stroke="var(--border-strong)" stroke-dasharray="2 3"/>
      <path d="${d}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round"/>
      <circle cx="${pts[pts.length - 1][0]}" cy="${pts[pts.length - 1][1]}" r="2.5" fill="${color}"/></svg>
      <span class="${last >= 0 ? "up" : "down"}">${pct(last)}</span><span class="muted">${keys[keys.length - 1]}</span></span>`;
  }

  function linkById(id) { return D.links.find((l) => l.id === id); }
  function linkSentence(l) {
    return `${esc(node(l.from).name)} ${LINK_VERB[l.type] || l.type} ${esc(node(l.to).name)}${l.what ? " · " + esc(l.what) : ""}`;
  }

  /* Popover: shows a link's source quote.
     Mouse: appears while hovering a line. Touch: tap a line to open it; it has a close button and
     closes when you tap anywhere else or scroll, so it never gets stuck over the page. */
  let pop, pinned = false;
  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement("div"); pop.className = "popover"; pop.setAttribute("role", "dialog");
    document.body.appendChild(pop);
    document.addEventListener("pointerdown", (e) => { if (pinned && !pop.contains(e.target) && !e.target.closest(".link-hit")) hidePopover(true); }, true);
    window.addEventListener("scroll", () => hidePopover(true), { passive: true });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") hidePopover(true); });
    return pop;
  }
  function showPopover(html, x, y, pin) {
    ensurePop();
    pinned = !!pin;
    pop.innerHTML = (pin ? '<button class="pop-close" type="button" aria-label="Close">×</button>' : "") + html;
    pop.classList.toggle("pinned", pinned);
    const pad = 14, w = Math.min(340, window.innerWidth - 16);
    pop.style.maxWidth = w + "px";
    const r = pop.getBoundingClientRect();
    let left = x + pad, top = y + pad;
    if (left + w > window.innerWidth - 8) left = Math.max(8, x - w - pad);
    if (left < 8) left = 8;
    if (top + r.height > window.innerHeight - 8) top = Math.max(8, y - r.height - pad);
    pop.style.left = left + "px"; pop.style.top = top + "px";
    pop.classList.add("show");
    if (pin) pop.querySelector(".pop-close").addEventListener("click", () => hidePopover(true));
  }
  function hidePopover(force) {
    if (!pop || (pinned && force !== true)) return;
    pinned = false;
    pop.classList.remove("show", "pinned");
  }
  /* Attach the quote popover to a line in a diagram. */
  function bindLinkPopover(hit, link, onTap) {
    hit.classList.add("link-hit");
    hit.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse") showPopover(linkPopoverHtml(link), e.clientX, e.clientY); });
    hit.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") hidePopover(); });
    hit.addEventListener("click", (e) => {
      if (onTap) return onTap(e);
      showPopover(linkPopoverHtml(link), e.clientX, e.clientY, true);
    });
  }
  function linkPopoverHtml(l) {
    const s = (l.sources || [])[0];
    const quote = s ? `<q>${esc(s.quote)}</q>` : "<em>No source stored.</em>";
    const src = s ? `${esc(s.doc_type || "")} ${s.published_at ? "· " + esc(s.published_at) : ""} ${s.verified ? "· quote verified" : ""}` : "";
    return `<div><b>${linkSentence(l)}</b> ${l.is_sample ? '<span class="sample-tag">SAMPLE</span>' : ""}</div>${quote}
      <div class="meta">${esc(l.confidence)} confidence · last confirmed ${esc(fmtDate(l.last_confirmed))}${src ? "<br>" + src : ""}</div>`;
  }

  /* Header, sample banner, footer — the same on every page. */
  function chrome(active) {
    const theme = (() => { try { return localStorage.getItem("ripple-theme"); } catch (e) { return null; } })();
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    const header = document.createElement("header");
    header.innerHTML = `${D.contains_sample_data ? '<div class="sample-banner">Showing <b>SAMPLE</b> data — hand-made for testing the design. Not real evidence.</div>' : ""}
      <div class="site-header"><div class="wrap">
        <a class="brand" href="index.html" aria-label="Ripple home">
          <svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="3.5" fill="var(--accent)"/><circle cx="16" cy="16" r="8.5" fill="none" stroke="var(--accent)" stroke-opacity=".6" stroke-width="1.5"/><circle cx="16" cy="16" r="14" fill="none" stroke="var(--accent)" stroke-opacity=".28" stroke-width="1.5"/></svg>
          Ripple <small class="hide-sm">AI hardware supply chain</small></a>
        <nav class="nav" aria-label="Main">
          <a href="index.html" ${active === "home" ? 'aria-current="page"' : ""}>Events</a>
          <a href="map.html" ${active === "map" ? 'aria-current="page"' : ""}>Map</a>
          <a class="hide-sm" href="brief.html" ${active === "brief" ? 'aria-current="page"' : ""}>Monday brief</a>
          <a class="hide-sm" href="index.html#companies">Companies</a>
          <button class="theme-toggle" type="button" id="theme-toggle">Light</button>
        </nav></div></div>`;
    document.body.prepend(header);
    const btn = qs("#theme-toggle");
    const sync = () => { btn.textContent = document.documentElement.getAttribute("data-theme") === "light" ? "Dark" : "Light"; };
    sync();
    btn.addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("ripple-theme", next); } catch (e) { /* private mode */ }
      sync();
      document.dispatchEvent(new CustomEvent("ripple:theme"));
    });
    const footer = document.createElement("footer");
    footer.className = "site-footer";
    footer.innerHTML = `<div class="wrap"><span class="disclaimer">Research and information only. Not investment advice.</span>
      <span class="mono">Data updated ${esc(D.generated_at || "—")} · every link shows its source and the date it was last confirmed</span></div>`;
    document.body.appendChild(footer);
  }

  window.Ripple = Object.assign(window.Ripple || {}, {
    D, esc, qs, param, reducedMotion, cssVar, layerVar, dirVar, dirMark, node, nodeUrl, badge, severityBar,
    fmtDate, isStale, pct, sparkline, linkById, linkSentence, showPopover, hidePopover, bindLinkPopover, linkPopoverHtml, chrome,
    LAYER_LABEL, KIND_LABEL, TYPE_LABEL, LINK_VERB, DIR_WORD,
  });
})();
