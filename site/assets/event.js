/* Event page: reads like a feature article.
   Headline, one-line summary, the ripple animation, ranked impacts, then details and sources. */
(function () {
  "use strict";
  const R = window.Ripple, D = R.D, esc = R.esc;
  R.chrome("event");
  const main = R.qs("#main");
  const ev = (D.events || []).find((e) => e.id === R.param("id")) || (D.events || [])[0];
  if (!ev) { main.innerHTML = '<div class="wrap"><p class="empty">Event not found.</p></div>'; return; }
  document.title = `${ev.title} — Ripple`;

  const impacts = (ev.impacts || []).slice().sort((a, b) => b.exposure_score - a.exposure_score);
  const pathChain = (imp) => imp.path.map((id) => `<a href="${R.nodeUrl(id)}">${esc(R.node(id).name)}</a>`).join('<span class="arrow">→</span>');

  const rankRow = (imp, i) => `<div class="rank-row" style="transition-delay:${(i * 0.06).toFixed(2)}s">
      <span class="rank-n">${String(i + 1).padStart(2, "0")}</span>
      <span class="rank-name"><a href="${R.nodeUrl(imp.node_id)}">${esc(R.node(imp.node_id).name)}</a>${R.dirMark(imp.direction)}</span>
      <span class="score">${Math.round(imp.exposure_score)}<small>exposure</small></span></div>`;

  const impactCard = (imp) => {
    const color = `var(${R.dirVar(imp.direction)})`;
    return `<article class="card impact-card">
      <header><div><div class="name"><a href="${R.nodeUrl(imp.node_id)}">${esc(R.node(imp.node_id).name)}</a></div>
        <div class="meta-row" style="margin-top:4px">${R.badge(imp.node_id)}${R.dirMark(imp.direction)}</div></div>
        <div class="score">${Math.round(imp.exposure_score)}<small>of 100</small></div></header>
      <div class="exposure-bar" aria-hidden="true"><i style="width:${imp.exposure_score}%;background:${color}"></i></div>
      <dl class="facts">
        <div><dt>How much</dt><dd>${esc(imp.how_much || "—")}</dd></div>
        <div><dt>Timing</dt><dd>${esc(imp.timing || "—")}</dd></div>
        <div><dt>Confidence</dt><dd class="conf-${esc(imp.confidence)}">${esc(imp.confidence || "—")}</dd></div>
      </dl>
      ${imp.why ? `<p style="margin:0;font-size:14px">${esc(imp.why)}</p>` : '<p class="muted" style="margin:0;font-size:14px">Not yet explained. Path found by the tracer.</p>'}
      <div class="path-chain" title="The chain of links from the event to this company">${pathChain(imp)}</div>
      ${R.sparkline(imp.followups)}
      ${imp.what_would_change_this ? `<div class="what-change"><b>What would change this:</b> ${esc(imp.what_would_change_this)}</div>` : ""}
    </article>`;
  };

  // Links used on any path, for the sources list
  const usedLinks = [...new Set(impacts.flatMap((i) => i.path_links))].map(R.linkById).filter(Boolean);
  const followRows = impacts.filter((i) => i.followups && Object.keys(i.followups).length);

  main.innerHTML = `
  <article>
    <div class="wrap">
      <header class="article-head">
        <div class="meta-row"><span class="type-chip">${esc(R.TYPE_LABEL[ev.event_type] || ev.event_type)}</span>${R.severityBar(ev.severity)}
          ${ev.is_sample ? '<span class="sample-tag">SAMPLE</span>' : ""}</div>
        <h1>${esc(ev.title)}</h1>
        <p class="dek">${esc(ev.one_line || "")}</p>
        <div class="byline"><span>Started <time>${esc(R.fmtDate(ev.started_at))}</time></span><span>${impacts.length} companies reached</span>
          <span>Directly hit: ${ev.affected_nodes.map((n) => `<a href="${R.nodeUrl(n)}">${esc(R.node(n).name)}</a>`).join(", ")}</span></div>
      </header>

      <div class="ripple-stage">
        <div class="ripple-canvas"><div class="grid-bg"></div><button class="btn replay" type="button" id="replay">Replay ripple</button><div id="ripple"></div></div>
        <aside>
          <div class="eyebrow" style="margin-bottom:10px">Most exposed</div>
          <div class="ranked" id="ranked">${impacts.slice(0, 8).map(rankRow).join("")}</div>
          <div class="legend" style="margin-top:14px"><span><i style="background:var(--hurt)"></i>Hurt</span><span><i style="background:var(--helped)"></i>Helped</span><span><i style="background:var(--unclear)"></i>Unclear</span><span><i class="dash"></i>Low-confidence link</span></div>
          <p class="muted" style="font-size:12px;margin-top:10px">Bigger, brighter dots are more exposed. Hover a line to see the filing quote behind it.</p>
        </aside>
      </div>
    </div>

    <div class="wrap narrow">
      <section class="section">
        <div class="eyebrow" style="margin-bottom:12px">What happened and why it matters</div>
        <div class="prose">${(ev.summary || "").split(/\n+/).map((p) => `<p>${esc(p)}</p>`).join("") || '<p class="muted">The explainer has not written a summary yet.</p>'}</div>
      </section>
    </div>

    <div class="wrap">
      <section class="section">
        <div class="section-head"><h2>Who is exposed</h2><span class="muted mono">ranked by exposure score</span></div>
        <div class="impact-cards">${impacts.map(impactCard).join("") || '<p class="empty">No company is connected to this event on the map yet.</p>'}</div>
      </section>
    </div>

    <div class="wrap narrow">
      ${ev.biggest_unknowns && ev.biggest_unknowns.length ? `<section class="section"><div class="section-head"><h2>Biggest unknowns</h2></div>
        <p class="muted" style="margin-top:-6px">Gaps in the map that matter most for this event.</p>
        <ul class="unknowns">${ev.biggest_unknowns.map((u) => `<li>${esc(u)}</li>`).join("")}</ul></section>` : ""}

      ${followRows.length ? `<section class="section"><div class="section-head"><h2>What happened next</h2></div>
        <p class="muted" style="margin-top:-6px">Stock move against its sector after the event.${ev.is_sample ? " <b>SAMPLE numbers — made up.</b>" : ""}</p>
        <div class="table-scroll"><table class="data"><thead><tr><th>Company</th><th>Our call</th><th class="num">1 day</th><th class="num">1 week</th><th class="num">1 month</th></tr></thead><tbody>
        ${followRows.map((i) => `<tr><td><a href="${R.nodeUrl(i.node_id)}">${esc(R.node(i.node_id).name)}</a></td><td>${R.dirMark(i.direction)}</td>
          ${["1d", "1w", "1m"].map((k) => { const v = i.followups[k]; return `<td class="num mono ${v == null ? "" : v >= 0 ? "up" : "down"}">${R.pct(v)}</td>`; }).join("")}</tr>`).join("")}
        </tbody></table></div></section>` : ""}

      <section class="section"><div class="section-head"><h2>Sources</h2></div>
        <h3>Reports of the event</h3>
        <ul class="source-list">${(ev.sources || []).map((s) => `<li><time>${esc(s.date || "")}</time>${s.url ? `<a href="${esc(s.url)}" rel="noopener">${esc(s.title)}</a>` : `<span>${esc(s.title)}</span>`}</li>`).join("") || '<li class="muted">None stored.</li>'}</ul>
        <h3 style="margin-top:22px">Map links used in the paths above</h3>
        <ul class="source-list">${usedLinks.map((l) => { const s = (l.sources || [])[0] || {}; return `<li><span class="conf">${esc(l.confidence)}</span><span>${R.linkSentence(l)} — <q>${esc(s.quote || "no quote")}</q>
          ${s.url ? ` <a href="${esc(s.url)}" rel="noopener">${esc(s.doc_type || "source")}</a>` : ""} <span class="muted mono">confirmed ${esc(R.fmtDate(l.last_confirmed))}</span>${l.is_sample ? ' <span class="sample-tag">SAMPLE</span>' : ""}</span></li>`; }).join("")}</ul>
      </section>
    </div>
  </article>`;

  const stage = R.qs("#ripple"), ranked = R.qs("#ranked");
  const run = () => {
    ranked.classList.remove("show");
    R.renderRipple(stage, ev, { onSettled: () => ranked.classList.add("show") });
  };
  run();
  R.qs("#replay").addEventListener("click", run);
})();
