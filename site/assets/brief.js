/* Monday brief: drafted from the data every week; you edit it before posting.
   ?week=YYYY-MM-DD picks the Monday; default = the latest Monday. */
(function () {
  "use strict";
  const R = window.Ripple, D = R.D, esc = R.esc;
  R.chrome("brief");
  const day = 864e5;
  const iso = (d) => d.toISOString().slice(0, 10);
  const parse = (s) => new Date(s + "T00:00:00Z");
  let monday = R.param("week") ? parse(R.param("week")) : new Date(Date.UTC(new Date().getUTCFullYear(), new Date().getUTCMonth(), new Date().getUTCDate()));
  while (monday.getUTCDay() !== 1) monday = new Date(monday - day);
  const from = new Date(monday - 7 * day), to = new Date(monday - day);
  const inRange = (s, a, b) => s && parse(s) >= a && parse(s) <= b;

  const events = (D.events || []).slice().sort((a, b) => b.severity - a.severity || (b.started_at || "").localeCompare(a.started_at || ""));
  let top = events.filter((e) => inRange(e.started_at, from, to)).slice(0, 3);
  const developing = top.length < 2 ? events.filter((e) => !top.includes(e) && inRange(e.started_at, new Date(monday - 30 * day), to)).slice(0, 2 - top.length) : [];
  const newLinks = (D.links || []).filter((l) => inRange(l.first_seen, from, to));
  const lastMonth = events.filter((e) => inRange(e.started_at, new Date(monday - 45 * day), new Date(monday - 21 * day)));
  const anySample = top.concat(developing, lastMonth).some((e) => e.is_sample) || newLinks.some((l) => l.is_sample);

  function verdict(imp) {
    const m = imp.followups && (imp.followups["1m"] != null ? imp.followups["1m"] : imp.followups["1w"]);
    if (m == null || imp.direction === "unclear") return null;
    const held = (imp.direction === "hurt" && m < 0) || (imp.direction === "helped" && m > 0);
    return { held, move: m };
  }
  const topCompanies = (e) => (e.impacts || []).slice(0, 3).map((i) => `${R.node(i.node_id).name} (${R.DIR_WORD[i.direction].toLowerCase()})`).join(", ");

  const item = (e, label) => `<article class="card brief-item">
      <div class="meta-row"><span class="type-chip">${esc(label || R.TYPE_LABEL[e.event_type])}</span><time>${esc(R.fmtDate(e.started_at))}</time>${R.severityBar(e.severity)}${e.is_sample ? '<span class="sample-tag">SAMPLE</span>' : ""}</div>
      <h3><a href="event.html?id=${encodeURIComponent(e.id)}" style="color:var(--text)">${esc(e.title)}</a></h3>
      <p style="margin:0">${esc(e.one_line || "")}</p>
      <p class="muted" style="margin:0;font-size:14px">Most exposed: ${esc(topCompanies(e)) || "—"}</p></article>`;

  const calls = lastMonth.map((e) => {
    const v = (e.impacts || []).map((i) => ({ i, v: verdict(i) })).filter((x) => x.v);
    return { e, v };
  }).filter((x) => x.v.length);

  R.qs("#main").innerHTML = `
    <header class="article-head">
      <div class="eyebrow">The Monday brief · week of ${esc(R.fmtDate(iso(from)))} – ${esc(R.fmtDate(iso(to)))}</div>
      <h1 style="font-size:clamp(34px,5vw,56px)">${top.length ? esc(top[0].title) : "A quiet week on the map"}</h1>
      <p class="dek">${top.length ? `${top.length} event${top.length === 1 ? "" : "s"} touched the AI hardware chain this week. Here's who was exposed, what changed on the map, and how last month's calls held up.` : "No new supply events crossed our threshold this week."}</p>
      ${anySample ? '<p style="margin-top:14px"><span class="sample-tag">SAMPLE</span> <span class="muted">This draft uses sample data.</span></p>' : ""}
      <div class="brief-actions">
        <button class="btn" id="copy-md" type="button">Copy as newsletter (Markdown)</button>
        <button class="btn" id="copy-thread" type="button">Copy social thread</button>
        <button class="btn" type="button" onclick="window.print()">Print / save as PDF</button>
        <span class="muted mono" id="copied" aria-live="polite"></span>
      </div>
    </header>
    <section class="section"><div class="section-head"><h2>The ripples that mattered</h2></div>
      <div style="display:grid;gap:14px">${top.map((e) => item(e)).join("") + developing.map((e) => item(e, "Still developing")).join("") || '<p class="empty">Nothing this week.</p>'}</div></section>
    <section class="section"><div class="section-head"><h2>What changed on the map</h2><span class="muted mono">${newLinks.length} new link${newLinks.length === 1 ? "" : "s"}</span></div>
      ${newLinks.length ? `<ul class="source-list">${newLinks.map((l) => `<li><span class="conf">${esc(l.confidence)}</span><span>${R.linkSentence(l)}</span></li>`).join("")}</ul>` : '<p class="empty">No new approved links this week.</p>'}</section>
    <section class="section"><div class="section-head"><h2>How last month's calls turned out</h2></div>
      ${calls.length ? `<div class="table-scroll"><table class="data"><thead><tr><th>Event</th><th>Company</th><th>Our call</th><th class="num">Move since</th><th>Verdict</th></tr></thead><tbody>
        ${calls.flatMap(({ e, v }) => v.map(({ i, v: r }) => `<tr><td>${esc(e.title)}${e.is_sample ? ' <span class="sample-tag">SAMPLE</span>' : ""}</td><td>${esc(R.node(i.node_id).name)}</td><td>${R.dirMark(i.direction)}</td>
          <td class="num mono ${r.move >= 0 ? "up" : "down"}">${R.pct(r.move)}</td><td class="${r.held ? "verdict-held" : "verdict-missed"}">${r.held ? "Held up" : "Didn't hold"}</td></tr>`)).join("")}
        </tbody></table></div>` : '<p class="empty">No calls from 3–6 weeks ago with price follow-ups yet.</p>'}</section>
    <p class="muted" style="font-size:13px;margin-top:40px">Drafted automatically from the map. Edit before posting. Research and information only. Not investment advice.</p>`;

  const site = location.href.split("brief.html")[0];
  function markdown() {
    const lines = [`# The Ripple Monday brief — week of ${iso(from)}`, ""];
    if (anySample) lines.push("_SAMPLE data — not real events._", "");
    lines.push("## The ripples that mattered", "");
    top.concat(developing).forEach((e) => lines.push(`**${e.title}** (severity ${e.severity}/5, ${e.started_at})  `, `${e.one_line || ""}  `, `Most exposed: ${topCompanies(e)}  `, `${site}event.html?id=${e.id}`, ""));
    lines.push("## What changed on the map", "");
    (newLinks.length ? newLinks.map((l) => `- ${R.node(l.from).name} ${R.LINK_VERB[l.type]} ${R.node(l.to).name}${l.what ? " (" + l.what + ")" : ""}`) : ["- No new approved links this week."]).forEach((x) => lines.push(x));
    lines.push("", "## How last month's calls turned out", "");
    (calls.length ? calls.flatMap(({ e, v }) => v.map(({ i, v: r }) => `- ${e.title}: ${R.node(i.node_id).name}, called ${i.direction}, moved ${R.pct(r.move)} — ${r.held ? "held up" : "didn't hold"}`)) : ["- Nothing to score yet."]).forEach((x) => lines.push(x));
    lines.push("", "_Research and information only. Not investment advice._");
    return lines.join("\n");
  }
  function thread() {
    const posts = [`The Ripple Monday brief, week of ${iso(from)}: ${top.length ? top.length + " supply events touched the AI hardware chain." : "a quiet week."}${anySample ? " (SAMPLE data)" : ""} 🧵`];
    top.concat(developing).forEach((e, n) => posts.push(`${n + 1}/ ${e.title} (severity ${e.severity}/5). Most exposed: ${topCompanies(e)}. ${site}event.html?id=${e.id}`.slice(0, 280)));
    posts.push(`${newLinks.length} new sourced links on the map this week. Every link points to the filing it came from. Not investment advice.`);
    return posts.join("\n\n");
  }
  const copy = (text) => (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(
    () => (R.qs("#copied").textContent = "Copied ✓"), () => { window.prompt("Copy this:", text); });
  R.qs("#copy-md").addEventListener("click", () => copy(markdown()));
  R.qs("#copy-thread").addEventListener("click", () => copy(thread()));
})();
