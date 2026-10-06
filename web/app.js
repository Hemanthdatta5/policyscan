"use strict";
// All fetched/policy text is inserted with textContent only. Never innerHTML.

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "style") Object.assign(node.style, v);
    else node[k] = v;
  }
  for (const c of children) node.append(c);
  return node;
}

async function api(path, method = "GET", body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map((m) => m.msg).join("; ");
    throw new Error(msg || `Request failed (${res.status})`);
  }
  return data;
}

const tone = (score) => (score >= 8 ? "good" : score >= 5 ? "warn" : "bad");
let currentUser = null;
let currentReport = null;

function renderAccount() {
  $("who").textContent = currentUser ? currentUser : "";
  $("btn-login").hidden = !!currentUser;
  $("btn-mine").hidden = !currentUser;
  $("btn-logout").hidden = !currentUser;
}

async function refreshMe() {
  try { currentUser = (await api("/api/auth/me")).email; } catch { currentUser = null; }
  renderAccount();
}

function section(title, ...kids) {
  return el("section", { class: "panel" }, el("h2", { textContent: title }), ...kids);
}

function renderRing(score) {
  const r = 62, c = 2 * Math.PI * r;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 150 150");
  for (const [stroke, frac] of [["var(--surface-2)", 1], [`var(--${tone(score)})`, score / 10]]) {
    const circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", 75); circle.setAttribute("cy", 75); circle.setAttribute("r", r);
    circle.setAttribute("fill", "none"); circle.setAttribute("stroke-width", 12);
    circle.setAttribute("stroke", stroke); circle.setAttribute("stroke-linecap", "round");
    circle.setAttribute("stroke-dasharray", `${c * frac} ${c}`);
    svg.append(circle);
  }
  return el("div", { class: "ring" }, svg,
    el("div", { class: "val" }, el("div", { class: "num", textContent: score.toFixed(1) }), el("div", { class: "of", textContent: "out of 10" })));
}

function renderReport(rep) {
  currentReport = rep;
  const root = $("report");
  root.replaceChildren();
  root.hidden = false;
  const t = tone(rep.score);

  const meta = el("div", { class: "meta" },
    el("span", { textContent: `${rep.paragraph_count} paragraphs analyzed` }),
    el("span", { textContent: `classifier: ${rep.classifier}` }));
  const actions = el("div", { class: "row", style: { marginTop: "12px" } });
  const saveBtn = el("button", { class: "btn small", type: "button", textContent: rep.saved ? "Saved" : "Save report", disabled: !!rep.saved });
  saveBtn.addEventListener("click", async () => {
    if (!currentUser) { $("auth-panel").hidden = false; $("auth-error").textContent = "Log in to save reports."; return; }
    try { renderReport(await api(`/api/reports/${encodeURIComponent(rep.id)}/save`, "POST")); } catch (e) { $("scan-error").textContent = e.message; }
  });
  actions.append(saveBtn);

  root.append(el("section", { class: "panel summary" },
    renderRing(rep.score),
    el("div", {},
      el("div", { class: "site", textContent: rep.policy_url || rep.url || "Pasted policy text" }),
      el("div", { class: "verdict" }, el("span", { class: `pill p-${t}`, textContent: rep.rating })),
      meta, actions)));

  // Category breakdown
  const cats = rep.categories.map((c) => {
    const frac = c.checked ? c.earned / c.max : 0;
    const ctone = frac >= 0.8 ? "good" : frac >= 0.5 ? "warn" : "bad";
    const row = el("div", { class: "cat" },
      el("div", { class: "name", textContent: c.label }),
      el("div", { class: "pts", textContent: c.checked ? `${c.earned} / ${c.max}` : "not checked" }),
      el("div", { class: "bar" }, el("i", { style: { width: `${frac * 100}%`, background: `var(--${ctone})` } })));
    if (c.checked && c.reasons.length === 0) row.append(el("div", { class: "why", textContent: "Full points." }));
    for (const r of c.reasons) row.append(el("div", { class: "why", textContent: `−${r.points_lost}: ${r.reason}` }));
    return row;
  });

  // Red flags
  const flags = rep.reasons.length
    ? rep.reasons.map((r) => el("div", { class: "flag" },
        el("span", { class: "sev", style: { background: `var(--${r.points_lost >= 0.75 ? "bad" : "warn"})` } }),
        el("div", {},
          el("div", { class: "t", textContent: `−${r.points_lost} · ${r.reason}` }),
          r.quote ? el("q", { textContent: r.quote }) : "",
          el("div", { class: "tag", textContent: `found by: ${r.source}` }))))
    : [el("div", { class: "d", textContent: "No points lost." })];
  root.append(el("div", { class: "grid2" }, section("Score breakdown", ...cats), section("Red flags", ...flags)));

  // Trackers
  const tr = rep.trackers;
  let trackerBody;
  if (!tr.checked) {
    trackerBody = el("div", { class: "note", textContent: tr.error ? `Tracker check unavailable: ${tr.error}` : "Not checked (pasted text)." });
  } else if (tr.findings.length === 0) {
    trackerBody = el("div", { class: "note", textContent: `No known trackers found among ${tr.third_party_hosts} third-party hosts.` });
  } else {
    const body = el("tbody");
    for (const f of tr.findings) {
      body.append(el("tr", {},
        el("td", { textContent: f.entity }),
        el("td", { class: "dom", textContent: f.domains.join(", ") }),
        el("td", { textContent: f.category }),
        el("td", { textContent: f.phase === "before" ? "before banner" : "after banner" }),
        el("td", {}, el("span", { class: `pill p-${f.disclosed ? "good" : "bad"}`, textContent: f.disclosed ? "in policy" : "not in policy" }))));
    }
    trackerBody = el("div", { class: "tablewrap" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["Company", "Domains", "Type", "Loaded", "Policy"].map((h) => el("th", { textContent: h })))), body));
  }
  const checklist = rep.checklist.map((c) => el("div", { class: "check" },
    el("span", { class: "m", style: { color: `var(--${c.met ? "good" : "bad"})` }, textContent: c.met ? "✓" : "✗" }),
    el("span", { textContent: `${c.regime}: ${c.item}` })));
  root.append(el("div", { class: "grid2" }, section("Trackers: policy vs. practice", trackerBody),
    section("GDPR / CCPA checklist", ...checklist, el("div", { class: "note", textContent: "Keyword check of the policy text, not a legal assessment." }))));
  root.scrollIntoView({ behavior: "smooth" });
}

async function runScan(body, button) {
  $("scan-error").textContent = "";
  $("status").textContent = body.url ? "Finding the policy and auditing trackers. This can take up to a minute…" : "Analyzing…";
  button.disabled = true;
  try { renderReport(await api("/api/scan", "POST", body)); }
  catch (e) { $("scan-error").textContent = e.message; $("report").hidden = true; }
  finally { $("status").textContent = ""; button.disabled = false; }
}

function selectTab(which) {
  const isUrl = which === "url";
  $("tab-url").setAttribute("aria-selected", String(isUrl));
  $("tab-text").setAttribute("aria-selected", String(!isUrl));
  $("form-url").hidden = !isUrl;
  $("form-text").hidden = isUrl;
}

async function loadMine() {
  const list = $("saved-list");
  list.replaceChildren();
  try {
    const rows = await api("/api/reports");
    if (!rows.length) list.append(el("li", { textContent: "No saved reports yet." }));
    for (const r of rows) {
      const b = el("button", { type: "button" }, el("span", { textContent: r.target }),
        el("span", { textContent: `${r.score.toFixed(1)} · ${r.rating}` }));
      b.addEventListener("click", async () => renderReport(await api(`/api/reports/${encodeURIComponent(r.id)}`)));
      list.append(el("li", {}, b));
    }
  } catch (e) { list.append(el("li", { textContent: e.message })); }
}

async function auth(kind) {
  $("auth-error").textContent = "";
  try {
    await api(`/api/auth/${kind}`, "POST", { email: $("email").value, password: $("password").value });
    $("password").value = "";
    $("auth-panel").hidden = true;
    await refreshMe();
  } catch (e) { $("auth-error").textContent = e.message; }
}

$("tab-url").addEventListener("click", () => selectTab("url"));
$("tab-text").addEventListener("click", () => selectTab("text"));
$("form-url").addEventListener("submit", (e) => { e.preventDefault(); runScan({ url: $("url").value.trim() }, e.submitter); });
$("form-text").addEventListener("submit", (e) => { e.preventDefault(); runScan({ text: $("text").value }, e.submitter); });
$("btn-login").addEventListener("click", () => { $("auth-panel").hidden = !$("auth-panel").hidden; });
$("auth-form").addEventListener("submit", (e) => { e.preventDefault(); auth("login"); });
$("do-register").addEventListener("click", () => auth("register"));
$("btn-logout").addEventListener("click", async () => { await api("/api/auth/logout", "POST"); $("mine-panel").hidden = true; await refreshMe(); });
$("btn-mine").addEventListener("click", async () => { $("mine-panel").hidden = !$("mine-panel").hidden; if (!$("mine-panel").hidden) await loadMine(); });
refreshMe();
