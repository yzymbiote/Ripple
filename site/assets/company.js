/* Company page (also works for places and materials):
   known suppliers and customers with source quote and confidence; places and materials it
   depends on; every event that has touched it. */
(function () {
  "use strict";
  const R = window.Ripple, D = R.D, esc = R.esc;
  R.chrome("company");
  const main = R.qs("#main");
  const id = R.param("id");
  const n = D.nodes[id];
  if (!n) { main.innerHTML = '<div class="wrap"><p class="empty">Not on the map.</p></div>'; return; }
  document.title = `${n.name} — Ripple`;

  const out = D.links.filter((l) => l.from === id), inn = D.links.filter((l) => l.to === id);
  const isCo = n.kind === "company";

  const linkCard = (l, otherId, verb) => {
    const s = (l.sources || [])[0] || {};
    const stale = R.isStale(l.last_confirmed);
    return `<article class="card link-card ${l.confidence === "low" ? "low" : ""} ${stale ? "stale" : ""}">
      <div class="top"><a href="${R.nodeUrl(otherId)}" style="display:flex;gap:8px;align-items:center;color:var(--text);font-weight:600">${R.node(otherId).ticker ? R.badge(otherId) : ""}${esc(R.node(otherId).name)}</a>
        <span class="conf conf-${esc(l.confidence)}">${esc(l.confidence)} confidence</span></div>
      <div style="font-size:13px" class="muted">${esc(verb)}${l.what ? ": <b style='color:var(--text)'>" + esc(l.what) + "</b>" : ""}${l.share != null ? ` · <span class="mono">${l.share}% share</span>` : ""}</div>
      ${s.quote ? `<blockquote>${esc(s.quote)}</blockquote>` : '<p class="muted">No source quote stored.</p>'}
      <div class="foot"><span>${s.url ? `<a href="${esc(s.url)}" rel="noopener">${esc(s.doc_type || "source")} ${esc(s.published_at || "")}</a>` : esc(s.doc_type || "")}
        ${s.verified ? ' · <span class="verified">✓ quote verified</span>' : ""}${l.is_sample ? ' <span class="sample-tag">SAMPLE</span>' : ""}</span>
        <span>last confirmed <time>${esc(R.fmtDate(l.last_confirmed))}</time>${stale ? " · <b>over 12 months old</b>" : ""}</span></div>
    </article>`;
  };
  const block = (title, note, items) => `<section class="section"><div class="section-head"><h2>${title}</h2><span class="muted mono">${items.length}</span></div>
      ${note ? `<p class="muted" style="margin-top:-6px">${note}</p>` : ""}
      ${items.length ? `<div class="link-grid">${items.join("")}</div>` : '<p class="empty">Nothing on the map yet.</p>'}</section>`;

  let sections;
  if (isCo) {
    sections = [
      block("Suppliers", "Companies that sell to " + esc(n.name) + ".", inn.filter((l) => l.type === "supplies").map((l) => linkCard(l, l.from, "supplies " + n.name))),
      block("Customers", "Companies " + esc(n.name) + " sells to.", out.filter((l) => l.type === "supplies").map((l) => linkCard(l, l.to, "buys from " + n.name))),
      block("Places and materials it depends on", "", out.filter((l) => l.type === "uses" || l.type === "makes_in").map((l) => linkCard(l, l.to, l.type === "uses" ? "uses" : "makes things in"))),
      block("What it produces", "", out.filter((l) => l.type === "produces").map((l) => linkCard(l, l.to, "produces"))),
    ];
  } else {
    sections = [
      block("Who produces it", "", [...inn.filter((l) => l.type === "produces").map((l) => linkCard(l, l.from, "produced by")), ...out.filter((l) => l.type === "produces").map((l) => linkCard(l, l.to, n.name + " produces"))]),
      block(n.kind === "place" ? "Who makes things here" : "Who uses it", "", inn.filter((l) => l.type === "uses" || l.type === "makes_in").map((l) => linkCard(l, l.from, l.type === "uses" ? "uses" : "makes things in"))),
    ];
  }

  const touched = (D.events || []).map((e) => ({ e, imp: (e.impacts || []).find((i) => i.node_id === id), direct: e.affected_nodes.includes(id) }))
    .filter((x) => x.imp || x.direct);
  const eventsHtml = touched.length ? `<div class="table-scroll"><table class="data"><thead><tr><th>Date</th><th>Event</th><th>Severity</th><th>Effect</th><th class="num">Exposure</th><th>Since</th></tr></thead><tbody>
    ${touched.map(({ e, imp, direct }) => `<tr><td class="mono">${esc(e.started_at)}</td><td><a href="event.html?id=${encodeURIComponent(e.id)}">${esc(e.title)}</a>${e.is_sample ? ' <span class="sample-tag">SAMPLE</span>' : ""}</td>
      <td>${R.severityBar(e.severity)}</td><td>${direct ? '<span class="dir" style="color:var(--accent-text)">Directly hit</span>' : R.dirMark(imp.direction)}</td>
      <td class="num mono">${imp ? Math.round(imp.exposure_score) : "—"}</td><td>${imp ? R.sparkline(imp.followups) : ""}</td></tr>`).join("")}
    </tbody></table></div>` : '<p class="empty">No events have touched this yet.</p>';

  main.innerHTML = `<div class="wrap">
    <header class="company-head">
      <div class="eyebrow">${esc(isCo ? R.LAYER_LABEL[n.layer] || "Company" : R.KIND_LABEL[n.kind])}</div>
      <h1>${esc(n.name)}</h1>
      <div class="tags">${isCo && n.ticker ? R.badge(id) : ""}${n.country ? `<span class="chip">${esc(n.country)}</span>` : ""}
        <span class="chip">${out.length + inn.length} links</span></div>
      <p class="muted" style="font-size:18px;margin:0;max-width:40em">${esc(n.notes || "")}</p>
      ${n.aliases && n.aliases.length ? `<p class="muted mono" style="font-size:12px;margin:0">Also known as: ${n.aliases.map(esc).join(" · ")}</p>` : ""}
    </header>
    ${sections.join("")}
    <section class="section"><div class="section-head"><h2>Events that touched ${esc(n.name)}</h2></div>${eventsHtml}</section>
  </div>`;
})();
