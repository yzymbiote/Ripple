/* Home page: ticker strip, pulsing map hero, event feed, company list. */
(function () {
  "use strict";
  const R = window.Ripple, D = R.D, esc = R.esc;
  R.chrome("home");

  const events = (D.events || []).slice().sort((a, b) => (b.started_at || "").localeCompare(a.started_at || ""));

  // Ticker strip (content doubled so the scroll loops seamlessly)
  const tick = events.map((e) => `<span class="ticker-item"><span class="ticker-dot"></span><time>${esc(e.started_at)}</time>
      <a href="event.html?id=${encodeURIComponent(e.id)}">${esc(e.title)}</a><span>SEV ${e.severity}</span>${e.is_sample ? '<span class="sample-tag">SAMPLE</span>' : ""}</span>`).join("");
  R.qs("#ticker").innerHTML = tick + tick;

  // Stats
  const companies = Object.values(D.nodes).filter((n) => n.kind === "company");
  R.qs("#stats").innerHTML = [
    [companies.length, "companies"], [Object.keys(D.nodes).length - companies.length, "places & materials"],
    [D.mapLinks.length, "sourced links"], [events.length, "events traced"],
  ].map(([n, l]) => `<div class="stat"><b>${n}</b><span>${l}</span></div>`).join("");

  // Hero map
  const mapBox = R.qs("#hero-map");
  const drawMap = () => R.renderHeroMap(mapBox, { labels: window.innerWidth > 640 });
  drawMap();
  let lastW = window.innerWidth;
  window.addEventListener("resize", () => { if ((lastW > 640) !== (window.innerWidth > 640)) { lastW = window.innerWidth; drawMap(); } });
  R.qs("#legend").innerHTML = Object.entries(R.LAYER_LABEL).map(([k, v]) => `<span><i style="background:var(--layer-${k})"></i>${v}</span>`).join("") +
    `<span><i style="background:var(--layer-place)"></i>Places</span><span><i class="solid"></i>Stated in a filing</span><span><i class="dash"></i>Low confidence</span>`;

  // Event feed
  R.qs("#event-count").textContent = `${events.length} event${events.length === 1 ? "" : "s"}`;
  const grid = R.qs("#events");
  grid.innerHTML = events.map((e) => {
    const top = (e.impacts || []).slice(0, 3).map((i) => `<div class="top3-row">${R.badge(i.node_id)}<span>${esc(R.node(i.node_id).name)}</span>${R.dirMark(i.direction)}</div>`).join("");
    return `<a class="card event-card" href="event.html?id=${encodeURIComponent(e.id)}">
      <div class="mini" data-event="${esc(e.id)}"></div>
      <div class="body">
        <div class="meta-row"><span class="type-chip">${esc(R.TYPE_LABEL[e.event_type] || e.event_type)}</span><time>${esc(R.fmtDate(e.started_at))}</time>${R.severityBar(e.severity)}${e.is_sample ? '<span class="sample-tag">SAMPLE</span>' : ""}</div>
        <h3>${esc(e.title)}</h3>
        <p>${esc(e.one_line || "")}</p>
        <div class="top3">${top || '<span class="muted">No companies reached yet.</span>'}</div>
      </div></a>`;
  }).join("") || '<p class="empty">No events yet.</p>';

  // Small ripple on each card, played once when it scrolls into view
  const byId = Object.fromEntries(events.map((e) => [e.id, e]));
  const play = (box) => R.renderRipple(box, byId[box.dataset.event], { compact: true });
  const boxes = grid.querySelectorAll(".mini");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => entries.forEach((en) => { if (en.isIntersecting) { play(en.target); io.unobserve(en.target); } }), { threshold: 0.4 });
    boxes.forEach((b) => io.observe(b));
  } else boxes.forEach(play);

  // Places and materials (each has its own page: who produces it, who uses it, events)
  R.qs("#material-list").innerHTML = Object.values(D.nodes).filter((n) => n.kind !== "company").sort((a, b) => a.name.localeCompare(b.name))
    .map((n) => `<a href="${R.nodeUrl(n.id)}" class="card" style="padding:8px 12px;display:inline-flex;gap:8px;align-items:center;color:var(--text)">
      <span class="chip">${esc(R.KIND_LABEL[n.kind])}</span><span style="font-size:14px">${esc(n.name)}</span></a>`).join("");

  // Companies grouped by layer
  R.qs("#company-count").textContent = `${companies.length} companies`;
  R.qs("#company-list").innerHTML = Object.entries(R.LAYER_LABEL).map(([layer, label]) => {
    const list = companies.filter((c) => c.layer === layer).sort((a, b) => a.name.localeCompare(b.name));
    return `<div style="margin-bottom:22px"><h3 class="muted" style="font:500 12px var(--mono);letter-spacing:.1em;text-transform:uppercase">${esc(label)}</h3>
      <div style="display:flex;flex-wrap:wrap;gap:8px">${list.map((c) => `<a href="${R.nodeUrl(c.id)}" class="card" style="padding:8px 12px;display:inline-flex;gap:8px;align-items:center;color:var(--text)">${R.badge(c.id)}<span style="font-size:14px">${esc(c.name)}</span></a>`).join("")}</div></div>`;
  }).join("");
})();
