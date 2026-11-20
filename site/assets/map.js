/* Map explorer: the whole map, filter by layer, click a node to see its links, click a link to see its sources. */
(function () {
  "use strict";
  const R = window.Ripple, D = R.D, esc = R.esc;
  R.chrome("map");
  const LAYERS = Object.assign({}, R.LAYER_LABEL, { places: "Places & materials" });
  const on = Object.fromEntries(Object.keys(LAYERS).map((k) => [k, true]));
  const groupOf = (n) => (n.kind === "company" ? n.layer : "places");
  let selected = R.param("node");

  const filters = R.qs("#filters");
  filters.innerHTML = Object.entries(LAYERS).map(([k, v]) =>
    `<button class="filter" type="button" data-layer="${k}" aria-pressed="true"><i style="background:var(${k === "places" ? "--layer-place" : "--layer-" + k})"></i>${esc(v)}</button>`).join("");
  filters.addEventListener("click", (e) => {
    const b = e.target.closest(".filter"); if (!b) return;
    on[b.dataset.layer] = !on[b.dataset.layer];
    b.setAttribute("aria-pressed", String(on[b.dataset.layer]));
    draw();
  });

  const linkBlock = (l) => {
    const s = (l.sources || [])[0] || {};
    return `<div class="lk" data-link="${esc(l.id)}"><b>${R.linkSentence(l)}</b> ${l.is_sample ? '<span class="sample-tag">SAMPLE</span>' : ""}
      <div class="conf">${esc(l.confidence)} confidence · confirmed ${esc(R.fmtDate(l.last_confirmed))}${l.share != null ? " · " + l.share + "%" : ""}</div>
      ${s.quote ? `<blockquote>${esc(s.quote)}</blockquote>` : ""}${s.url ? `<a href="${esc(s.url)}" rel="noopener" style="font-size:12px">${esc(s.doc_type || "source")} ↗</a>` : ""}</div>`;
  };

  // Searchable list: the easy way to pick a company on a phone.
  const finder = R.qs("#finder");
  const listBox = R.qs("#finder-list");
  function renderList() {
    const q = (finder.value || "").trim().toLowerCase();
    const items = Object.values(D.nodes).filter((n) => !q || n.name.toLowerCase().includes(q) || (n.ticker || "").toLowerCase().includes(q)
      || (n.aliases || []).some((a) => a.toLowerCase().includes(q)))
      .sort((a, b) => a.name.localeCompare(b.name));
    const count = (id) => D.mapLinks.filter((l) => l.from === id || l.to === id).length;
    listBox.innerHTML = items.map((n) => `<button type="button" class="finder-item${n.id === selected ? " on" : ""}" data-id="${esc(n.id)}">
        ${n.kind === "company" && n.ticker ? R.badge(n.id) : `<span class="chip">${esc(R.KIND_LABEL[n.kind])}</span>`}<span>${esc(n.name)}</span><span class="muted mono">${count(n.id)}</span></button>`).join("");
  }
  finder.addEventListener("input", renderList);
  listBox.addEventListener("click", (e) => {
    const b = e.target.closest(".finder-item"); if (!b) return;
    selected = b.dataset.id; draw();
    R.qs("#side").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  function scrollToLink(id) {
    const el = R.qs(`#side [data-link="${CSS.escape(id)}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function side() {
    const box = R.qs("#side");
    if (!selected || !D.nodes[selected]) {
      box.innerHTML = `<div class="eyebrow">How to use</div><p style="margin:0">Click any dot to see who it supplies, who supplies it, and the filing quote behind each link. Use the buttons above to show or hide a layer.</p>
        <p class="muted" style="margin:0;font-size:13px">${Object.keys(D.nodes).length} nodes · ${D.mapLinks.length} links</p>`;
      return;
    }
    const n = D.nodes[selected];
    const mine = D.mapLinks.filter((l) => l.from === selected || l.to === selected);
    box.innerHTML = `<div class="eyebrow">${esc(n.kind === "company" ? R.LAYER_LABEL[n.layer] : R.KIND_LABEL[n.kind])}</div>
      <h2>${esc(n.name)}</h2><p class="muted" style="margin:0">${esc(n.notes || "")}</p>
      <a href="${R.nodeUrl(selected)}">Open full page →</a>
      ${mine.map(linkBlock).join("") || '<p class="empty">No links on the map yet.</p>'}
      <button class="btn" type="button" id="clear">Show everything</button>`;
    R.qs("#clear").addEventListener("click", () => { selected = null; draw(); });
    box.querySelectorAll(".lk").forEach((el) => el.addEventListener("mouseenter", () => highlight(el.dataset.link)));
  }

  let svg;
  function highlight(linkId) {
    svg.querySelectorAll(".map-edge-line").forEach((ln) => ln.classList.toggle("hl", ln.dataset.link === linkId));
  }

  function draw() {
    const box = R.qs("#map");
    const small = window.innerWidth < 640;
    const visible = Object.fromEntries(Object.entries(D.nodes).filter(([, n]) => on[groupOf(n)]));
    // On phones, a selected node shows only its neighbourhood (the plan: "the map simplifies on small screens").
    let nodes = visible;
    if (small && selected) {
      const keep = new Set([selected]);
      D.mapLinks.forEach((l) => { if (l.from === selected) keep.add(l.to); if (l.to === selected) keep.add(l.from); });
      nodes = Object.fromEntries(Object.entries(visible).filter(([id]) => keep.has(id)));
    }
    const links = D.mapLinks.filter((l) => nodes[l.from] && nodes[l.to]);
    const w = 1000, h = small ? 1000 : 640;
    box.innerHTML = "";
    svg = R.svgEl("svg", { viewBox: `${-w / 2} ${-h / 2} ${w} ${h}`, role: "img", "aria-label": "Supply map" }, box);
    R.svgDefs(svg, "map");
    const p = R.layoutMap(nodes, links, w, h);
    const near = new Set();
    if (selected) { near.add(selected); links.forEach((l) => { if (l.from === selected) near.add(l.to); if (l.to === selected) near.add(l.from); }); }
    const eg = R.svgEl("g", {}, svg);
    links.forEach((l) => {
      const attrs = { x1: p[l.from][0], y1: p[l.from][1], x2: p[l.to][0], y2: p[l.to][1] };
      const touches = selected && (l.from === selected || l.to === selected);
      const line = R.svgEl("line", Object.assign({ stroke: "var(--map-dim)", "stroke-width": 1.3, "stroke-dasharray": l.confidence === "low" ? "4 5" : "none",
        class: "map-edge-line" + (selected && !touches ? " dim" : touches ? " hl" : "") }, attrs), eg);
      line.dataset.link = l.id;
      const hit = R.svgEl("line", Object.assign({ stroke: "transparent", "stroke-width": 14 }, attrs), eg);
      hit.style.cursor = "pointer";
      // Tapping a line selects it and shows its quote in the side panel (no floating popup on phones).
      R.bindLinkPopover(hit, l, () => { R.hidePopover(true); selected = l.from; draw(); setTimeout(() => { highlight(l.id); scrollToLink(l.id); }, 0); });
    });
    const deg = {};
    links.forEach((l) => { deg[l.from] = (deg[l.from] || 0) + 1; deg[l.to] = (deg[l.to] || 0) + 1; });
    const ng = R.svgEl("g", {}, svg);
    Object.entries(nodes).forEach(([id, n]) => {
      const g = R.svgEl("g", { class: "map-node" + (selected && !near.has(id) ? " dim" : ""), transform: `translate(${p[id][0].toFixed(1)} ${p[id][1].toFixed(1)})`, tabindex: "0", role: "button", "aria-label": n.name }, ng);
      const r = (4 + Math.min(8, (deg[id] || 0) * 0.9) + (id === selected ? 3 : 0)) * (small ? 1.8 : 1);
      // Invisible, fingertip-sized tap area around every dot (and its name is tappable too).
      R.svgEl("circle", { r: small ? 46 : 20, fill: "transparent" }, g);
      const c = R.svgEl("circle", { r, fill: `var(${R.layerVar(n)})`, filter: id === selected ? "url(#glow-map)" : "" }, g);
      if (n.kind !== "company") { c.setAttribute("fill-opacity", "0.55"); c.setAttribute("stroke", `var(${R.layerVar(n)})`); }
      const t = R.svgEl("text", { x: r + 5, y: small ? 8 : 4, "font-size": small ? 26 : 14, fill: id === selected ? "var(--text)" : "var(--text-2)", class: "tap-label" }, g);
      t.textContent = n.kind === "company" && n.ticker && !/\d/.test(n.ticker) ? n.ticker : n.name;
      const pick = () => { selected = id; draw(); if (small) R.qs("#side").scrollIntoView({ behavior: "smooth", block: "start" }); };
      g.addEventListener("click", pick);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
    });
    side();
    renderList();
  }
  draw();
})();
