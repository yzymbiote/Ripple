/* The ripple diagram (event pages + home cards) and the softly pulsing home map.
   Plain SVG + CSS transitions; no libraries.

   The signature moment (build plan, "Look and feel"):
   1. the map dims and the event node lights up with a pulse
   2. rings spread out from it like a stone dropped in water
   3. light travels along each link to the next company, ~0.4 s per step
   4. each company glows when reached: red hurt / green helped / amber unclear;
      brighter and bigger = more exposed
   5. when it settles, the ranked impacts appear (onSettled callback)
   With "reduced motion" switched on, the finished ripple is shown straight away. */
(function () {
  "use strict";
  const R = window.Ripple;
  const NS = "http://www.w3.org/2000/svg";
  const STEP = 0.4;          // seconds per step
  const START = 0.9;         // pulse + rings before the light starts travelling

  function el(name, attrs, parent) {
    const e = document.createElementNS(NS, name);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  function defs(svg, id) {
    const d = el("defs", {}, svg);
    const f = el("filter", { id: "glow-" + id, x: "-100%", y: "-100%", width: "300%", height: "300%" }, d);
    el("feGaussianBlur", { stdDeviation: "4", result: "b" }, f);
    const m = el("feMerge", {}, f);
    el("feMergeNode", { in: "b" }, m);
    el("feMergeNode", { in: "SourceGraphic" }, m);
    const g = el("radialGradient", { id: "core-" + id }, d);
    el("stop", { offset: "0%", "stop-color": "var(--accent)", "stop-opacity": "1" }, g);
    el("stop", { offset: "100%", "stop-color": "var(--accent)", "stop-opacity": "0" }, g);
  }

  /* ---------- Ripple layout: event in the middle, rings by number of steps ---------- */
  function layoutRipple(event) {
    const D = R.D;
    const sources = event.affected_nodes.slice();
    const impacts = event.impacts || [];
    const impactBy = Object.fromEntries(impacts.map((i) => [i.node_id, i]));
    const edges = new Map(); // "a>b" -> {from, to, link}
    const addEdge = (a, b, linkId) => { const k = a + ">" + b; if (!edges.has(k) && a !== b) edges.set(k, { from: a, to: b, link: R.linkById(linkId) }); };
    impacts.forEach((imp) => { for (let i = 1; i < imp.path.length; i++) addEdge(imp.path[i - 1], imp.path[i], imp.path_links[i - 1]); });

    // Breadth-first distance from the affected nodes.
    const level = {};
    sources.forEach((s) => (level[s] = 0));
    const adj = {};
    edges.forEach((e) => { (adj[e.from] = adj[e.from] || []).push(e.to); });
    let frontier = sources.slice();
    while (frontier.length) {
      const next = [];
      frontier.forEach((n) => (adj[n] || []).forEach((m) => { if (level[m] == null) { level[m] = level[n] + 1; next.push(m); } }));
      frontier = next;
    }
    // Nodes not reachable from the sources (e.g. "possible winners" via a material one step away):
    // hook them up through a real map link if there is one.
    const placed = () => Object.keys(level);
    let changed = true;
    while (changed) {
      changed = false;
      edges.forEach((e) => {
        if (level[e.from] != null && level[e.to] == null) { level[e.to] = level[e.from] + 1; changed = true; }
        if (level[e.from] == null) {
          const bridge = D.links.find((l) => (l.to === e.from && level[l.from] != null) || (l.from === e.from && level[l.to] != null));
          if (bridge) {
            const anchor = level[bridge.from] != null ? bridge.from : bridge.to;
            addEdge(anchor, e.from, bridge.id);
            level[e.from] = level[anchor] + 1; changed = true;
          }
        }
      });
    }
    edges.forEach((e) => { if (level[e.from] == null) level[e.from] = 1; if (level[e.to] == null) level[e.to] = level[e.from] + 1; });
    impacts.forEach((i) => { if (level[i.node_id] == null) level[i.node_id] = 1; });

    // Parent = first node one level up that links to it (for angle placement).
    const parent = {};
    edges.forEach((e) => { if (level[e.to] === level[e.from] + 1 && !parent[e.to]) parent[e.to] = e.from; });

    const maxLevel = Math.max(1, ...Object.values(level));
    const ids = placed();
    const singleSource = sources.length === 1;
    const radiusFor = (lv) => {
      const base = singleSource ? 0 : 0.17;
      return lv === 0 ? base : base + ((0.9 - base) * lv) / maxLevel;
    };
    // Radial tree layout: every node gets a wedge of the circle sized by how many
    // end-points sit beyond it, so branches don't cross.
    const children = {};
    ids.forEach((nid) => { if (level[nid] === 0) return; const par = parent[nid]; (children[par || "__root"] = children[par || "__root"] || []).push(nid); });
    children.__root = (children.__root || []).concat(ids.filter((nid) => level[nid] === 0));
    const leaves = {};
    const countLeaves = (nid, seen) => {
      if (leaves[nid] != null) return leaves[nid];
      seen.add(nid);
      const kids = (children[nid] || []).filter((k) => !seen.has(k));
      leaves[nid] = kids.length ? kids.reduce((a, k) => a + countLeaves(k, seen), 0) : 1;
      return leaves[nid];
    };
    const angle = {};
    const assign = (nid, from, to, seen) => {
      const kids = (children[nid] || []).filter((k) => !seen.has(k)).sort((a, b) => (impactBy[b] ? impactBy[b].exposure_score : 0) - (impactBy[a] ? impactBy[a].exposure_score : 0));
      kids.forEach((k) => seen.add(k));
      const total = kids.reduce((a, k) => a + countLeaves(k, new Set()), 0) || 1;
      let cur = from;
      kids.forEach((k) => {
        const span = ((to - from) * countLeaves(k, new Set())) / total;
        angle[k] = cur + span / 2;
        assign(k, cur, cur + span, seen);
        cur += span;
      });
    };
    assign("__root", -Math.PI / 2, (3 * Math.PI) / 2, new Set());
    ids.forEach((nid) => { if (angle[nid] == null) angle[nid] = 0; });
    if (singleSource) angle[sources[0]] = -Math.PI / 2;
    const pos = {};
    ids.forEach((id) => { const r = radiusFor(level[id]); pos[id] = [Math.cos(angle[id]) * r, Math.sin(angle[id]) * r]; });
    return { edges: Array.from(edges.values()), level, pos, angle, maxLevel, impactBy, sources };
  }

  /* ---------- Render one ripple ---------- */
  let uid = 0;
  function renderRipple(container, event, opts) {
    opts = Object.assign({ compact: false, animate: true, onSettled: null, labels: true }, opts || {});
    const id = "r" + uid++;
    container.innerHTML = "";
    const size = opts.compact ? 400 : 1000;
    const half = size / 2;
    const narrow = (container.clientWidth || 1000) < 520;
    const scale = half * (opts.compact ? 0.86 : narrow ? 0.56 : 0.68);
    const svg = el("svg", { viewBox: `${-half} ${-half * (opts.compact ? 0.62 : 1)} ${size} ${size * (opts.compact ? 0.62 : 1)}`, role: "img",
      "aria-label": `Ripple diagram for ${event.title}: ${event.impacts.length} companies reached` }, container);
    if (opts.compact) svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    defs(svg, id);
    const L = layoutRipple(event);
    const yScale = opts.compact ? 0.56 : 1;
    const P = (n) => [L.pos[n][0] * scale * (opts.compact ? 1.25 : 1), L.pos[n][1] * scale * yScale];
    const animate = opts.animate && !R.reducedMotion();
    // Keep labels readable on phones: about 11px on screen whatever the diagram's width.
    const fs = Math.max(19, 11000 / Math.max(300, container.clientWidth || 1000));
    const t0 = animate ? START : 0;
    const stepT = animate ? STEP : 0;

    // Faint guide rings
    const guides = el("g", { opacity: "0.5" }, svg);
    for (let lv = 1; lv <= L.maxLevel; lv++) {
      const anyAt = Object.keys(L.level).find((n) => L.level[n] === lv);
      if (!anyAt) continue;
      const r = Math.hypot(L.pos[anyAt][0], L.pos[anyAt][1]) * scale;
      el("ellipse", { rx: (r * (opts.compact ? 1.25 : 1)).toFixed(1), ry: (r * yScale).toFixed(1), fill: "none", stroke: "var(--border)", "stroke-dasharray": "2 6" }, guides);
    }

    // Spreading rings (the stone in the water)
    const rings = el("g", {}, svg);
    if (animate) {
      for (let i = 0; i < 3; i++) {
        const c = el("circle", { r: (scale * 1.05).toFixed(0), fill: "none", stroke: "var(--accent)", "stroke-width": opts.compact ? 1.5 : 2 }, rings);
        c.style.transformBox = "fill-box"; c.style.transformOrigin = "center";
        c.style.transform = "scale(0.02)"; c.style.opacity = "0.9";
        c.style.transition = `transform 1.6s cubic-bezier(.2,.7,.3,1) ${0.15 + i * 0.28}s, opacity 1.6s ease-out ${0.15 + i * 0.28}s`;
        requestAnimationFrame(() => requestAnimationFrame(() => { c.style.transform = "scale(1)"; c.style.opacity = "0"; }));
      }
    }

    // Links
    const edgeLayer = el("g", {}, svg);
    L.edges.forEach((e) => {
      const [x1, y1] = P(e.from), [x2, y2] = P(e.to);
      const low = e.link && e.link.confidence === "low";
      const len = Math.hypot(x2 - x1, y2 - y1);
      const g = el("g", {}, edgeLayer);
      el("line", { x1, y1, x2, y2, stroke: "var(--map-dim)", "stroke-width": opts.compact ? 1 : 1.5, "stroke-dasharray": low ? "5 6" : "none" }, g);
      const trail = el("line", { x1, y1, x2, y2, stroke: "var(--accent)", "stroke-opacity": low ? "0.45" : "0.6", "stroke-width": opts.compact ? 1.4 : 2, "stroke-linecap": "round" }, g);
      const spark = el("line", { x1, y1, x2, y2, stroke: "var(--accent)", "stroke-width": opts.compact ? 2.5 : 4, "stroke-linecap": "round", filter: `url(#glow-${id})` }, g);
      const delay = t0 + Math.max(0, L.level[e.from]) * stepT;
      if (low) trail.setAttribute("stroke-dasharray", "5 6");
      if (animate) {
        if (low) { trail.style.opacity = "0"; trail.style.transition = `opacity ${STEP}s linear ${delay}s`; }
        else { trail.style.strokeDasharray = `${len} ${len}`; trail.style.strokeDashoffset = len; trail.style.transition = `stroke-dashoffset ${STEP}s linear ${delay}s`; }
        spark.style.strokeDasharray = `14 ${len + 20}`; spark.style.strokeDashoffset = "14";
        spark.style.transition = `stroke-dashoffset ${STEP}s linear ${delay}s, opacity 0.3s ease ${delay + STEP}s`;
        requestAnimationFrame(() => requestAnimationFrame(() => {
          if (low) trail.style.opacity = "1"; else trail.style.strokeDashoffset = "0";
          spark.style.strokeDashoffset = String(-len); spark.style.opacity = "0";
        }));
      } else {
        spark.remove();
      }
      if (e.link && !opts.compact) {
        const hit = el("line", { x1, y1, x2, y2, stroke: "transparent", "stroke-width": 16, class: "map-edge", tabindex: "0" }, g);
        hit.style.cursor = "help";
        const show = (ev) => {
          const r = ev.clientX != null ? [ev.clientX, ev.clientY] : (() => { const b = hit.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; })();
          R.showPopover(R.linkPopoverHtml(e.link), r[0], r[1]);
        };
        hit.addEventListener("mousemove", show); hit.addEventListener("focus", show);
        hit.addEventListener("mouseleave", R.hidePopover); hit.addEventListener("blur", R.hidePopover);
      }
    });

    // Event core (the stone)
    const core = el("g", {}, svg);
    el("circle", { r: opts.compact ? 28 : 60, fill: `url(#core-${id})`, opacity: "0.55" }, core);
    if (L.sources.length > 1 || !L.pos[L.sources[0]] || L.pos[L.sources[0]][0] !== 0 || L.pos[L.sources[0]][1] !== 0) {
      el("circle", { r: opts.compact ? 6 : 11, fill: "var(--accent)", filter: `url(#glow-${id})` }, core);
      L.sources.forEach((s) => {
        if (!L.pos[s]) return;
        const [x, y] = P(s);
        el("line", { x1: 0, y1: 0, x2: x, y2: y, stroke: "var(--accent)", "stroke-opacity": "0.5", "stroke-width": 1.5 }, edgeLayer);
      });
    }

    // Nodes
    const nodeLayer = el("g", {}, svg);
    const ids = Object.keys(L.pos);
    ids.forEach((nid) => {
      const n = R.node(nid);
      const imp = L.impactBy[nid];
      const isSource = L.sources.includes(nid);
      const [x, y] = P(nid);
      const exposure = imp ? imp.exposure_score : 0;
      const rad = isSource ? (opts.compact ? 7 : 13) : (opts.compact ? 3.5 : 6) + (exposure / 100) * (opts.compact ? 9 : 18);
      const color = isSource ? "var(--accent)" : imp ? `var(${R.dirVar(imp.direction)})` : "var(--text-2)";
      const g = el("g", { class: "map-node", transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})` }, nodeLayer);
      const halo = el("circle", { r: (rad * 2.1).toFixed(1), fill: color, opacity: "0" }, g);
      const dot = el("circle", { r: rad.toFixed(1), fill: "var(--map-dim)", stroke: "var(--bg)", "stroke-width": opts.compact ? 1 : 2 }, g);
      const brightness = isSource ? 1 : 0.45 + 0.55 * Math.min(1, exposure / 60);
      const lit = () => { dot.setAttribute("fill", color); dot.setAttribute("fill-opacity", brightness.toFixed(2)); halo.setAttribute("opacity", (0.1 + 0.25 * brightness).toFixed(2)); if (imp || isSource) dot.setAttribute("filter", `url(#glow-${id})`); };
      const when = isSource ? 0.1 : t0 + L.level[nid] * stepT;
      if (animate) {
        halo.style.transition = dot.style.transition = "fill 0.25s ease, opacity 0.35s ease";
        setTimeout(lit, when * 1000);
      } else lit();
      if (opts.labels && !opts.compact) {
        const ang = L.angle[nid] || 0;
        const right = Math.cos(ang) >= -0.15;
        const label = el("text", { x: right ? rad + 8 : -rad - 8, y: 5, "text-anchor": right ? "start" : "end", "font-size": (isSource ? fs * 1.15 : fs).toFixed(0) }, g);
        label.textContent = narrow ? n.name.replace(/\s*\(.*\)\s*$/, "") : n.name;
        if (isSource) label.setAttribute("fill", "var(--text)");
        if (isSource && L.pos[nid][0] === 0 && L.pos[nid][1] === 0) { label.setAttribute("x", 0); label.setAttribute("y", rad + 28); label.setAttribute("text-anchor", "middle"); }
      }
      const title = el("title", {}, g);
      title.textContent = imp ? `${n.name}: ${R.DIR_WORD[imp.direction]}, exposure ${imp.exposure_score}` : n.name;
      if (!opts.compact) g.addEventListener("click", () => (location.href = R.nodeUrl(nid)));
    });

    const settleAt = (t0 + L.maxLevel * stepT + (animate ? 0.4 : 0)) * 1000;
    if (opts.onSettled) setTimeout(opts.onSettled, settleAt);
    return { svg, settleAt };
  }

  /* ---------- Whole-map layout for the home hero (small deterministic force layout) ---------- */
  const LAYER_ANCHOR = { materials: [-0.66, 0.2], memory: [-0.1, -0.5], packaging: [0.08, 0.05], power: [-0.05, 0.32], buyers: [0.66, -0.1] };
  function anchorFor(n) {
    if (n.kind === "company") return LAYER_ANCHOR[n.layer] || [0, 0];
    if (n.kind === "place") return [-0.55, -0.45];
    return [-0.4, 0.05];
  }
  function layoutMap(nodes, links, w, h) {
    const ids = Object.keys(nodes);
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const p = {};
    ids.forEach((id) => { const a = anchorFor(nodes[id]); p[id] = [a[0] * w * 0.5 + (rnd() - 0.5) * 60, a[1] * h * 0.5 + (rnd() - 0.5) * 60]; });
    const k = Math.sqrt((w * h) / Math.max(1, ids.length)) * 0.32;
    for (let it = 0; it < 260; it++) {
      const disp = {};
      ids.forEach((id) => (disp[id] = [0, 0]));
      for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
        const a = p[ids[i]], b = p[ids[j]];
        let dx = a[0] - b[0], dy = a[1] - b[1]; const d = Math.max(1, Math.hypot(dx, dy));
        const f = (k * k) / d; dx /= d; dy /= d;
        disp[ids[i]][0] += dx * f; disp[ids[i]][1] += dy * f; disp[ids[j]][0] -= dx * f; disp[ids[j]][1] -= dy * f;
      }
      links.forEach((l) => {
        const a = p[l.from], b = p[l.to]; if (!a || !b) return;
        let dx = a[0] - b[0], dy = a[1] - b[1]; const d = Math.max(1, Math.hypot(dx, dy));
        const f = (d * d) / k * 0.6; dx /= d; dy /= d;
        disp[l.from][0] -= dx * f; disp[l.from][1] -= dy * f; disp[l.to][0] += dx * f; disp[l.to][1] += dy * f;
      });
      const temp = 30 * (1 - it / 260) + 1;
      ids.forEach((id) => {
        const a = anchorFor(nodes[id]);
        disp[id][0] += (a[0] * w * 0.5 - p[id][0]) * 0.9; disp[id][1] += (a[1] * h * 0.5 - p[id][1]) * 0.9;
        const d = Math.max(1, Math.hypot(...disp[id]));
        p[id][0] += (disp[id][0] / d) * Math.min(d, temp); p[id][1] += (disp[id][1] / d) * Math.min(d, temp);
        p[id][0] = Math.max(-w / 2 + 30, Math.min(w / 2 - 30, p[id][0])); p[id][1] = Math.max(-h / 2 + 20, Math.min(h / 2 - 20, p[id][1]));
      });
    }
    return p;
  }

  function renderHeroMap(container, opts) {
    opts = opts || {};
    const D = R.D;
    const w = 1000, h = 690;
    container.innerHTML = "";
    const svg = el("svg", { viewBox: `${-w / 2} ${-h / 2} ${w} ${h}`, role: "img", class: "hero-map", "aria-label": `Map of ${Object.keys(D.nodes).length} companies, places and materials` }, container);
    defs(svg, "hero");
    const p = layoutMap(D.nodes, D.mapLinks, w, h);
    const latest = (D.events || [])[0];
    const hot = new Set(latest ? latest.affected_nodes : []);
    const eg = el("g", {}, svg);
    D.mapLinks.forEach((l) => {
      if (!p[l.from] || !p[l.to]) return;
      const touchesHot = hot.has(l.from) || hot.has(l.to);
      const line = el("line", { x1: p[l.from][0], y1: p[l.from][1], x2: p[l.to][0], y2: p[l.to][1],
        stroke: touchesHot ? "var(--accent)" : "var(--map-dim)", "stroke-opacity": touchesHot ? "0.55" : "1", "stroke-width": 1.2,
        "stroke-dasharray": l.confidence === "low" ? "4 5" : "none" }, eg);
      const hit = el("line", { x1: p[l.from][0], y1: p[l.from][1], x2: p[l.to][0], y2: p[l.to][1], stroke: "transparent", "stroke-width": 12 }, eg);
      hit.style.cursor = "help";
      hit.addEventListener("mousemove", (ev) => R.showPopover(R.linkPopoverHtml(l), ev.clientX, ev.clientY));
      hit.addEventListener("mouseleave", R.hidePopover);
      void line;
    });
    const ng = el("g", {}, svg);
    const degree = {};
    D.mapLinks.forEach((l) => { degree[l.from] = (degree[l.from] || 0) + 1; degree[l.to] = (degree[l.to] || 0) + 1; });
    Object.keys(D.nodes).forEach((id, i) => {
      const n = D.nodes[id];
      const [x, y] = p[id];
      const g = el("g", { class: "map-node", transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})` }, ng);
      const r = 4 + Math.min(7, (degree[id] || 0) * 0.8);
      if (hot.has(id)) el("circle", { class: "beacon", r: 6 }, g);
      const c = el("circle", { r, fill: `var(${R.layerVar(n)})`, class: "pulse-node", filter: hot.has(id) ? "url(#glow-hero)" : "" }, g);
      if (n.kind !== "company") { c.setAttribute("fill-opacity", "0.55"); c.setAttribute("stroke", `var(${R.layerVar(n)})`); }
      c.style.animationDelay = ((i * 0.37) % 4).toFixed(2) + "s";
      if (opts.labels !== false && (n.kind === "company" || hot.has(id))) {
        const t = el("text", { x: r + 5, y: 4, "font-size": 15, fill: hot.has(id) ? "var(--text)" : "var(--text-2)" }, g);
        t.textContent = n.kind === "company" ? (n.ticker && !/\d/.test(n.ticker) ? n.ticker : n.name) : n.name;
      }
      const title = el("title", {}, g); title.textContent = `${n.name} — ${R.KIND_LABEL[n.kind]}`;
      g.addEventListener("click", () => (location.href = R.nodeUrl(id)));
    });
    return svg;
  }

  R.renderRipple = renderRipple;
  R.renderHeroMap = renderHeroMap;
  R.layoutRipple = layoutRipple;
  R.layoutMap = layoutMap;
  R.svgEl = el;
  R.svgDefs = defs;
})();
