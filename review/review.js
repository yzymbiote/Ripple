/* Review queue page: talks to the local server started by `python -m ripple review`. */
(function () {
  "use strict";
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const VERB = { supplies: "supplies", makes_in: "makes things in", uses: "uses", produces: "produces" };
  const HELP = {
    pending: "Links found in filings. Read the quote: does it really say this? Approve, fix (Edit) or reject.",
    candidates: "Relationships the AI found but code couldn't match to a node on the map — unnamed customers, or companies not on the map yet. Link one to a node if the quote clearly names it; otherwise reject it, or leave it for later.",
    approved: "Approved links are shown on the public site. You can send one back to pending.",
    rejected: "Rejected links never appear on the site. You can send one back to pending.",
  };
  let data = null, tab = "pending";

  async function load() {
    const r = await fetch("/api/review");
    data = await r.json();
    render();
  }
  async function post(url, body, card) {
    card.querySelectorAll("button").forEach((b) => (b.disabled = true));
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const out = await r.json();
    if (out.error) {
      card.querySelector(".err").textContent = out.error;
      card.querySelectorAll("button").forEach((b) => (b.disabled = false));
      return;
    }
    document.getElementById("saved").textContent = "Saved " + new Date().toLocaleTimeString();
    await load();
  }
  const name = (id) => (data.nodes[id] ? data.nodes[id].name : id);
  const nodeOptions = (sel, kinds) => Object.values(data.nodes).filter((n) => !kinds || kinds.includes(n.kind))
    .map((n) => `<option value="${esc(n.id)}" ${n.id === sel ? "selected" : ""}>${esc(n.name)}${n.ticker ? " (" + esc(n.ticker) + ")" : ""}</option>`).join("");

  function linkCard(l) {
    const s = l.sources[0] || {};
    return `<article class="card rv" data-id="${esc(l.id)}">
      <div class="rv-head"><div class="rv-claim">${esc(name(l.from_node))} <span class="verb">${VERB[l.type] || l.type}</span> ${esc(name(l.to_node))}
        ${l.what ? `<span class="muted" style="font-weight:400"> · ${esc(l.what)}</span>` : ""}${l.share != null ? ` <span class="mono muted">· ${l.share}%</span>` : ""}</div>
        <span class="status-pill status-${esc(l.status)}">${esc(l.status.replace("_", " "))}</span></div>
      ${[...new Set(l.sources.map((x) => x.quote))].map((q) => {
        const n = l.sources.filter((x) => x.quote === q).length;
        return `<blockquote>${esc(q)}</blockquote>${n > 1 ? `<div class="muted mono" style="font-size:12px">same sentence found in ${n} filings</div>` : ""}`;
      }).join("")}
      <div class="meta"><span>${esc(l.id)}</span><span>${esc(s.doc_type || "")} ${esc(s.published_at || "")}</span>
        ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">open filing ↗</a>` : ""}
        <span>${s.quote_verified ? "✓ quote found word for word" : "quote NOT verified"}</span><span>${esc(l.confidence)} confidence</span>
        <span>${l.sources.length} source${l.sources.length === 1 ? "" : "s"}</span></div>
      <div class="actions">
        ${l.status !== "approved" ? '<button class="btn btn-approve" data-act="approve">Approve</button>' : ""}
        ${l.status !== "rejected" ? '<button class="btn btn-reject" data-act="reject">Reject</button>' : ""}
        ${l.status !== "pending_review" ? '<button class="btn" data-act="pending">Back to pending</button>' : ""}
        <button class="btn" data-act="toggle-edit">Edit</button><span class="err"></span></div>
      <form class="edit">
        <label>From<select name="from_node">${nodeOptions(l.from_node)}</select></label>
        <label>Link type<select name="type">${Object.keys(VERB).map((t) => `<option ${t === l.type ? "selected" : ""}>${t}</option>`).join("")}</select></label>
        <label>To<select name="to_node">${nodeOptions(l.to_node)}</select></label>
        <label>What flows<input name="what" value="${esc(l.what || "")}"></label>
        <label>Share %<input name="share" type="number" step="0.1" value="${l.share == null ? "" : l.share}"></label>
        <label>Confidence<select name="confidence">${["high", "medium", "low"].map((c) => `<option ${c === l.confidence ? "selected" : ""}>${c}</option>`).join("")}</select></label>
        <label>&nbsp;<button class="btn" data-act="save-edit" type="button">Save changes</button></label>
      </form>
    </article>`;
  }

  function candidateCard(c) {
    const filer = name(c.filer_node);
    const party = c.other_party ? esc(c.other_party) : "<i>an unnamed party</i>";
    const claim = c.type === "supplies" ? (c.direction === "other_to_filer" ? `${party} supplies ${esc(filer)}` : `${esc(filer)} supplies ${party}`)
      : `${esc(filer)} ${VERB[c.type] || c.type} ${party}`;
    return `<article class="card rv" data-cand="${c.id}">
      <div class="rv-head"><div class="rv-claim">${claim}${c.what ? `<span class="muted" style="font-weight:400"> · ${esc(c.what)}</span>` : ""}${c.share != null ? ` <span class="mono muted">· ${c.share}%</span>` : ""}</div>
        <span class="status-pill status-pending_review">needs a name</span></div>
      <blockquote>${esc(c.quote)}</blockquote>
      <div class="meta"><span>${esc(c.doc_type || "")} ${esc(c.published_at || "")}</span>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">open filing ↗</a>` : ""}
        <span>${c.quote_verified ? "✓ quote found word for word" : "quote NOT verified"}</span><span>${esc(c.reason || "")}</span></div>
      <div class="actions">
        <select aria-label="Node on the map"><option value="">Match to a node on the map…</option>${nodeOptions(null)}</select>
        ${c.other_party ? '<label class="muted" style="font-size:13px"><input type="checkbox" checked> remember this name</label>' : ""}
        <button class="btn btn-approve" data-act="link">Make it a link (pending)</button>
        <button class="btn btn-reject" data-act="reject">Reject</button><span class="err"></span></div>
    </article>`;
  }

  function render() {
    const by = { pending: [], approved: [], rejected: [] };
    data.links.forEach((l) => by[l.status === "pending_review" ? "pending" : l.status].push(l));
    document.getElementById("n-pending").textContent = by.pending.length;
    document.getElementById("n-approved").textContent = by.approved.length;
    document.getElementById("n-rejected").textContent = by.rejected.length;
    document.getElementById("n-candidates").textContent = data.candidates.length;
    document.getElementById("tab-help").textContent = HELP[tab];
    const list = document.getElementById("list");
    const items = tab === "candidates" ? data.candidates.map(candidateCard) : by[tab].map(linkCard);
    list.innerHTML = items.join("") || '<p class="empty">Nothing here. 🎉</p>';
  }

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    tab = t.dataset.tab;
    document.querySelectorAll(".tab").forEach((x) => x.setAttribute("aria-selected", String(x === t)));
    render();
  }));
  document.getElementById("list").addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    const card = b.closest(".rv");
    const act = b.dataset.act;
    if (card.dataset.id) {
      const id = card.dataset.id;
      if (act === "toggle-edit") return card.querySelector(".edit").classList.toggle("open");
      if (act === "save-edit") {
        const f = Object.fromEntries(new FormData(card.querySelector(".edit")).entries());
        return post(`/api/link/${encodeURIComponent(id)}`, { action: "edit", fields: f }, card);
      }
      return post(`/api/link/${encodeURIComponent(id)}`, { action: act }, card);
    }
    const cid = card.dataset.cand;
    if (act === "reject") return post(`/api/candidate/${cid}`, { action: "reject" }, card);
    if (act === "link") {
      const node = card.querySelector("select").value;
      if (!node) { card.querySelector(".err").textContent = "Pick a node first."; return; }
      const cb = card.querySelector("input[type=checkbox]");
      return post(`/api/candidate/${cid}`, { action: "link", other_node: node, add_alias: cb ? cb.checked : false }, card);
    }
  });
  load().catch(() => { document.getElementById("list").innerHTML = '<p class="empty">Can\'t reach the review server. Start it with: python -m ripple review</p>'; });
})();
