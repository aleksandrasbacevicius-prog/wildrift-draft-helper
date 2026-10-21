const $ = (id) => document.getElementById(id);
const LANES = { baron: "Baron", jungle: "Jungle", mid: "Mid", dragon: "Dragon", support: "Support" };
const COMMON_OPPONENTS = 6;
const pct = (n) => `${Number(n).toFixed(1)}%`;
const ITEM_GROUPS = ["Fighter", "Assassin", "Marksman", "Magic", "Defense", "Support"];
// Item groups most relevant to each lane come first in the swap picker.
const LANE_ITEM_FIRST = {
  baron: ["Fighter", "Defense"], jungle: ["Fighter", "Assassin"], mid: ["Magic", "Assassin"],
  dragon: ["Marksman"], support: ["Support", "Defense"],
};
const itemGroupOrder = () => {
  const first = LANE_ITEM_FIRST[state.position] || [];
  return [...first, ...ITEM_GROUPS.filter((g) => !first.includes(g)), "Other"];
};
const state = {
  counters: [], vsName: "", serverBracket: "Diamond+",
  position: "baron", all: [], byPosition: {}, items: [], profile: {},
  build: null, original: [], poolDraft: new Set(),
};
try { state.position = localStorage.getItem("position") || "baron"; } catch {}

// Access token for protected actions (AI builds, saving builds and pools, patch checks). Kept on this
// device only; falls back to memory when the browser blocks storage (e.g. some private modes).
let memoryToken = "";
const tokenStore = {
  get() { try { return localStorage.getItem("accessToken") || memoryToken; } catch { return memoryToken; } },
  set(t) {
    memoryToken = t;
    try { t ? localStorage.setItem("accessToken", t) : localStorage.removeItem("accessToken"); } catch {}
    updateTokenLink();
  },
};
let promptedThisVisit = false; // ask for the token at most once per page load; the footer link asks again

function askForToken() {
  promptedThisVisit = true;
  const entered = window.prompt("Enter your access token.\nOnly the part after your name, e.g. after \"chocoloco:\"");
  // Accept a pasted "name:token" too, by keeping only the token part.
  const token = (entered || "").trim().replace(/^[a-z0-9_-]+:/i, "");
  if (token) tokenStore.set(token);
  return Boolean(token);
}

function updateTokenLink() {
  const link = document.getElementById("signOut");
  if (link) link.textContent = tokenStore.get() ? "Sign out on this phone" : "Enter access token";
}

async function api(path, options = {}, quiet = false) {
  const send = () => {
    const headers = { ...(options.headers || {}) };
    const token = tokenStore.get();
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(path, { ...options, headers });
  };
  let res = await send();
  if (res.status === 401 && !quiet && !promptedThisVisit && askForToken()) res = await send();
  const body = await res.json().catch(() => ({}));
  if (res.status === 401) {
    const hadToken = Boolean(tokenStore.get());
    tokenStore.set("");
    throw new Error(hadToken
      ? "That sign-in isn't valid anymore. Ask for a new personal link, or use \"Enter access token\" at the bottom."
      : "Sign-in needed. Open your personal link, or use \"Enter access token\" at the bottom of the page.");
  }
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const laneIcon = (p) => `/icons/wrf/lanes/${p}.png`;
const tierBadge = (t) => (t ? `<span class="tier ${t}">${t}</span>` : "");
const champ = (name) => state.all.find((c) => c.name === name);
const icon = (entry) => {
  const name = escapeHtml(entry.name);
  const inner = entry.icon
    ? `<img src="${entry.icon}" alt="" draggable="false">`
    : `<span class="badge">${escapeHtml(entry.name.slice(0, 2))}</span>`;
  return `<span class="ico" title="${name}" data-info="${name}">${inner}</span>`;
};

// Small Markdown subset for the agent's reply: headings, bold, bullet and numbered lists.
function renderMarkdown(md) {
  let html = "", list = null;
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of escapeHtml(md).split("\n")) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    const bullet = line.match(/^\s*[-*]\s+(.*)/), numbered = line.match(/^\s*\d+[.)]\s+(.*)/);
    const heading = line.match(/^#{1,6}\s+(.*)/);
    if (bullet || numbered) {
      const tag = bullet ? "ul" : "ol";
      if (list !== tag) { close(); html += `<${tag}>`; list = tag; }
      html += `<li>${(bullet || numbered)[1]}</li>`;
    } else {
      close();
      if (heading) html += `<p><strong>${heading[1]}</strong></p>`;
      else if (line.trim()) html += `<p>${line}</p>`;
    }
  }
  close();
  return html;
}

function renderLanes() {
  $("lanes").innerHTML = Object.entries(LANES).map(([p, label]) =>
    `<button class="lane" data-pos="${p}" aria-pressed="${p === state.position}"><img src="${laneIcon(p)}" alt="">${label}</button>`).join("");
}

function option(c, position, selected, suffix = "") {
  const tier = c.positions[position];
  return `<option value="${escapeHtml(c.name)}" ${c.name === selected ? "selected" : ""}>${tier ? tier + " · " : ""}${escapeHtml(c.name)}${suffix}</option>`;
}

function fillMe(selected) {
  const pos = state.position, pool = state.profile[pos] || [], vs = $("vs").value;
  const ranked = state.byPosition[pos] || [];
  const mine = pool.map(champ).filter((c) => c && c.name !== vs);
  const others = ranked.filter((c) => !pool.includes(c.name) && c.name !== vs);
  // Counters from another lane's list still need to be pickable from the strip.
  const listed = new Set([...mine, ...others].map((c) => c.name));
  const extra = state.counters.filter((c) => !listed.has(c.name) && c.name !== vs);
  const known = [...mine, ...others, ...extra].map((c) => c.name);
  selected = known.includes(selected) ? selected : (mine[0] || others[0] || extra[0] || state.all[0]).name;
  $("me").innerHTML =
    (mine.length ? `<optgroup label="My pool">${mine.map((c) => option(c, pos, selected)).join("")}</optgroup>` : "") +
    `<optgroup label="${LANES[pos]} tier list">${others.map((c) => option(c, pos, selected)).join("")}</optgroup>` +
    (extra.length ? `<optgroup label="Other counters">${extra.map((c) => option(c, pos, selected)).join("")}</optgroup>` : "");
  $("me").value = selected;
}

// "Counters to <opponent>": tappable icons under the opponent picker, your pool highlighted.
function renderCounterStrip() {
  const vs = $("vs").value, pool = state.profile[state.position] || [];
  // Your pool first; otherwise keep the server's order (strongest agreement between sources first).
  const counters = [...state.counters].sort((a, b) => pool.includes(b.name) - pool.includes(a.name)).slice(0, 8);
  $("counterStrip").classList.toggle("hidden", !counters.length);
  $("counterStrip").innerHTML = counters.length
    ? `<div class="strip-label">Counters to ${escapeHtml(vs)} <span class="plain">(tap to play)</span></div>
       <div class="strip-source">From WildRiftCore, WildRiftFire and WR-META. "2 sites" = they agree.</div>
       <div class="counter-row">${counters.map((c) => `
         <button class="counter-pick ${pool.includes(c.name) ? "mine" : ""} ${c.name === $("me").value ? "chosen" : ""}" data-champ="${escapeHtml(c.name)}">
           <img src="${c.icon}" alt="" draggable="false"><span>${escapeHtml(c.name)}</span>
           ${tierBadge(c.positions[state.position])}${pool.includes(c.name) ? '<span class="pool-mark">your pool</span>' : ""}
           ${(c.sources || []).length > 1 ? `<span class="agree-mark">${c.sources.length} sites</span>` : ""}
         </button>`).join("")}</div>`
    : "";
}

// Verdict under your pick: who counters whom, with alternatives when you're the one countered.
function renderVerdict(m) {
  const me = $("me").value, vs = $("vs").value, pool = state.profile[state.position] || [];
  let html = "";
  if (m.even) {
    html = `<div class="verdict-line even">≈ Skill matchup: neither side has an edge</div>`;
  } else if (m.counters_each_other) {
    html = `<div class="verdict-line even">≈ Even matchup: sources list ${escapeHtml(me)} and ${escapeHtml(vs)} as countering each other</div>`;
  } else if (m.you_counter_enemy) {
    html = `<div class="verdict-line good">✓ ${escapeHtml(me)} counters ${escapeHtml(vs)}</div>`;
  } else if (m.enemy_counters_you) {
    const options = [...state.counters]
      .filter((c) => c.name !== me)
      .sort((a, b) => pool.includes(b.name) - pool.includes(a.name))
      .slice(0, 3)
      .map((c) => `${escapeHtml(c.name)}${c.positions[state.position] ? ` (${c.positions[state.position]})` : ""}`);
    html = `<div class="verdict-line bad">✗ ${escapeHtml(vs)} counters ${escapeHtml(me)}</div>` +
      (options.length ? `<div class="verdict-try">Try: ${options.join(", ")}</div>` : "");
  }
  $("verdict").innerHTML = html;
  $("verdict").classList.toggle("hidden", !html);
}

// Who is strong against the lane opponent, used to group "Your champion" for counterpicking.
async function loadCounters() {
  state.vsName = $("vs").value;
  try {
    state.counters = await api(`/api/counters/${encodeURIComponent(state.vsName)}?position=${state.position}`);
  } catch {
    state.counters = [];
  }
  fillMe($("me").value);
  renderCounterStrip();
}

function fillVs(selected) {
  // Fall back to every champion if this lane's tier list is empty.
  const pos = state.position;
  const ranked = state.byPosition[pos] || [];
  const choices = ranked.length ? ranked : state.all;
  // Most common opponents this patch = highest Diamond+ pick rate in this lane.
  const common = choices.filter((c) => c.stats && c.stats[pos])
    .sort((a, b) => b.stats[pos].pick - a.stats[pos].pick).slice(0, COMMON_OPPONENTS);
  const commonNames = common.map((c) => c.name);
  const rest = choices.filter((c) => !commonNames.includes(c.name));
  selected = choices.some((c) => c.name === selected) ? selected : (common[0] || choices[0]).name;
  const picked = (c) => ` · ${Math.round(c.stats[pos].pick)}% picked`;
  $("vs").innerHTML =
    (common.length ? `<optgroup label="Most common this patch">${common.map((c) => option(c, pos, selected, picked(c))).join("")}</optgroup>` : "") +
    `<optgroup label="${LANES[pos]} tier list">${rest.map((c) => option(c, pos, selected)).join("")}</optgroup>`;
  $("vs").value = selected;
}

function renderEnemies() {
  const previous = Object.fromEntries([...$("enemies").querySelectorAll("select")].map((s) => [s.dataset.pos, s.value]));
  $("enemies").innerHTML = Object.keys(LANES).filter((p) => p !== state.position).map((p) => {
    const options = (state.byPosition[p] || []).map((c) => option(c, p, previous[p])).join("");
    return `<div><label><img src="${laneIcon(p)}" alt="">${LANES[p]}</label>
      <select data-pos="${p}"><option value="">None</option>${options}</select></div>`;
  }).join("");
}

function renderBuild() {
  const b = state.build;
  const opts = b.options || { core: [], boots: [], extras: [], runes: [] };
  const count = (list) => (list && list.length ? `${list.length} option${list.length > 1 ? "s" : ""}` : "tap to swap");
  $("core").innerHTML = b.core.map((item, slot) => {
    const swapped = item.name !== state.original[slot];
    return `<div class="item ${swapped ? "swapped" : ""}" data-slot="${slot}" role="button" tabindex="0"
        aria-label="Swap ${escapeHtml(item.name)}">
      ${icon(item)}<div>${escapeHtml(item.name)}</div>
      <div class="swap">${swapped ? `was ${escapeHtml(state.original[slot])}` : count(opts.core[slot])}</div>
    </div>`;
  }).join("");
  $("boots").innerHTML = b.boots.map((i) => `${icon(i)}<span class="muted">${escapeHtml(i.name)}</span>`).join("");
  // The full build: boots, then the core (follows your swaps), then the later items. Boots and later items swap here.
  const later = b.extras.map((item, slot) =>
    `<button class="slot ${item.name !== state.originalExtras[slot] ? "swapped" : ""} ${adjusted("extras", slot) ? "adjusted" : ""}"
       data-extra-slot="${slot}" aria-label="Swap ${escapeHtml(item.name)}">${icon(item)}</button>`);
  const boots = b.boots.map((item) =>
    `<button class="slot ${item.name !== state.originalBoots[0] ? "swapped" : ""} ${adjusted("boots", 0) ? "adjusted" : ""}"
       data-boots-slot="0" aria-label="Swap ${escapeHtml(item.name)}">${icon(item)}</button>`);
  $("final").innerHTML = [...boots, ...b.core.map(icon), ...later].join("");
  const sits = [
    ...(b.situational_items || []).map((s) => `<div class="sit"><span class="when">${escapeHtml(s.when)}</span>${icon(s.item)}</div>`),
    ...b.situational.map((s) => `<div class="sit"><span class="when">${escapeHtml(s.when)}</span>${icon(s.replace)}<span>→</span>${icon(s.with)}</div>`),
  ];
  $("sitBlock").classList.toggle("hidden", !sits.length);
  $("situational").innerHTML = sits.join("");
  $("runes").innerHTML = b.runes.map((r, slot) => {
    const swapped = r.name !== state.originalRunes[slot];
    return `<div class="rune ${slot === 0 ? "keystone" : ""} ${swapped ? "swapped" : ""}" data-rune-slot="${slot}" role="button" tabindex="0"
        aria-label="Swap rune ${escapeHtml(r.name)}">${icon(r)}<span>${escapeHtml(r.name)}</span></div>`;
  }).join("");
  $("spells").innerHTML = [...b.spells, ...b.starting].map((x) => `${icon(x)}<span class="muted">${escapeHtml(x.name)}</span>`).join("");
  renderChoices();
  renderMatchupNote();
  const otherLane = b.position && b.position !== state.position;
  $("laneNote").textContent = otherLane ? `No separate ${LANES[state.position]} build for ${b.name}; showing their ${LANES[b.position] || b.position} build.` : "";
  $("laneNote").classList.toggle("hidden", !otherLane);
  const changed = isCustomised();
  $("buildState").textContent = changed ? (state.savedFor === b.name ? "Your saved build" : "Not saved yet") : "Recommended build";
  $("resetBuild").classList.toggle("hidden", !changed);
}

const adjusted = (slot, index) => ((state.build.matchup || {}).adjustments || []).some((a) => a.slot === slot && a.index === index);

// Why the build differs against this opponent: matchup-specific counter items, or anti-magic when they deal magic damage.
function renderMatchupNote() {
  const m = state.build.matchup;
  const show = Boolean(m && m.enemy);
  $("matchupNote").classList.toggle("hidden", !show);
  if (!show) return;
  const changes = m.adjustments.map((a) =>
    `<li>${icon(a.with)}<span><strong>${escapeHtml(a.with.name)}</strong> instead of ${escapeHtml(a.replace.name)}: ${escapeHtml(a.why)}</span></li>`).join("");
  $("matchupNote").innerHTML = `<div class="matchup-note__head ${m.rule}">${escapeHtml(m.note)}</div>` + (changes ? `<ul>${changes}</ul>` : "");
}

// Whole item cores and rune pages: most played on the server, alternatives, WildRiftCore variants, the guide.
function renderChoices() {
  const b = state.build, choices = b.choices || { core: [], runes: [] };
  const sameNames = (a, c) => a.length === c.length && a.every((n, i) => n === c[i]);
  const core = b.core.map((i) => i.name), page = b.runes.map((r) => r.name);
  const sub = (c) => c.pick != null ? `${pct(c.win)} win · ${pct(c.pick)} pick` : escapeHtml(c.when || c.source);
  const chip = (kind, key, c, active) =>
    `<button class="choice ${active ? "active" : ""}" data-kind="${kind}" data-key="${key}" aria-pressed="${active}">
      <strong>${escapeHtml(c.label)}</strong><span>${sub(c)}</span></button>`;
  const server = b.server || {};
  const source = server.updated ? `<div class="choices-note">Server stats: ${escapeHtml(state.serverBracket)} ranked, CN server, updated ${escapeHtml(server.updated)}</div>` : "";
  $("coreChoices").classList.toggle("hidden", choices.core.length < 2);
  $("coreChoices").innerHTML = choices.core.length > 1
    ? `<div class="choice-row">${choices.core.map((c, i) => chip("core", i, c, sameNames(core, c.items.map((x) => x.name)))).join("")}</div>${source}`
    : "";
  $("runeChoices").classList.toggle("hidden", choices.runes.length < 2);
  $("runeChoices").innerHTML = choices.runes.length > 1
    ? `<div class="choice-row">${choices.runes.map((c, i) => chip("runes", i, c, sameNames(page, c.runes.map((r) => r.name)))).join("")}</div>`
    : "";
  const serverLine = (entries, words) => entries.length
    ? `<span class="muted">On the server:</span> ${entries.map((e) => `${words(e)} <span class="muted">${pct(e.pick)} pick, ${pct(e.win)} win</span>`).join(" · ")}`
    : "";
  $("serverBoots").innerHTML = serverLine(server.boots || [], (e) => escapeHtml(e.item.name));
  $("serverSpells").innerHTML = serverLine(server.spells || [], (e) => e.spells.map((s) => escapeHtml(s.name)).join(" + "));
}

async function applyChoice(kind, key) {
  const choice = state.build.choices[kind][Number(key)];
  if (kind === "core") state.build.core = choice.items.map((i) => itemByName(i.name));
  else state.build.runes = choice.runes.map((r) => runeByName(r.name));
  $("result").innerHTML = "";
  renderBuild();
  await savePreferences();
}

const differs = (list, original) => list.some((x, slot) => x.name !== original[slot]);
const isCustomised = () =>
  differs(state.build.core, state.original) || differs(state.build.runes, state.originalRunes) ||
  differs(state.build.boots, state.originalBoots) || differs(state.build.extras, state.originalExtras);

const itemByName = (name) => state.items.find((i) => i.name === name) || { name, icon: null };
const runeByName = (name) => state.runeList.find((r) => r.name === name) || { name, icon: null };

async function loadBuild() {
  const name = $("me").value, vs = $("vs").value, position = state.position;
  const [build, prefs] = await Promise.all([
    api(`/api/champions/${encodeURIComponent(name)}/build?position=${position}&vs=${encodeURIComponent(vs)}`),
    api(`/api/preferences/${encodeURIComponent(name)}?position=${position}`, {}, true).catch(() => ({ saved: null })),
  ]);
  if (name !== $("me").value || vs !== $("vs").value || position !== state.position) return; // a newer pick replaced this one
  // The full build is boots + core + later items; keep the later items separately so they can be swapped.
  build.extras = build.final.slice(build.boots.length + build.core.length);
  state.build = build;
  state.original = build.core.map((i) => i.name);
  state.originalRunes = build.runes.map((r) => r.name);
  state.originalBoots = build.boots.map((i) => i.name);
  state.originalExtras = build.extras.map((i) => i.name);
  state.savedFor = null;
  const saved = prefs.saved;
  if (saved && saved.core.length === build.core.length && saved.runes.length === build.runes.length) {
    build.core = saved.core.map(itemByName);
    build.runes = saved.runes.map(runeByName);
    if (saved.boots && build.boots.length) build.boots = [itemByName(saved.boots)];
    if (saved.extras && saved.extras.length === build.extras.length) build.extras = saved.extras.map(itemByName);
    state.savedFor = build.name;
  }
  renderBuild();
}

// Saves your item and rune choices for this champion (asks for your access token if needed).
async function savePreferences() {
  const b = state.build;
  try {
    if (isCustomised()) {
      await api(`/api/preferences/${encodeURIComponent(b.name)}?position=${state.position}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          core: b.core.map((i) => i.name), runes: b.runes.map((r) => r.name),
          boots: differs(b.boots, state.originalBoots) ? b.boots[0].name : null,
          extras: differs(b.extras, state.originalExtras) ? b.extras.map((i) => i.name) : [],
        }),
      });
      state.savedFor = b.name;
    } else {
      await api(`/api/preferences/${encodeURIComponent(b.name)}?position=${state.position}`, { method: "DELETE" });
      state.savedFor = null;
    }
  } catch (e) {
    state.savedFor = null;
    renderBuild();
    $("buildState").textContent = `Not saved: ${e.message}`;
    return;
  }
  renderBuild();
}

async function resetBuild() {
  state.build.core = state.original.map(itemByName);
  state.build.runes = state.originalRunes.map(runeByName);
  state.build.boots = state.originalBoots.map(itemByName);
  state.build.extras = state.originalExtras.map(itemByName);
  $("result").innerHTML = "";
  renderBuild();
  await savePreferences();
}

// Picker: a bottom sheet with icons. Suggestions for this slot and matchup come first, with the reason;
// then items by category (lane-relevant first) or runes by tree (keystones for the first slot).
const PICKER_SLOTS = {
  item: { list: () => state.build.core, original: () => state.original, options: (slot) => state.build.options.core[slot] },
  boots: { list: () => state.build.boots, original: () => state.originalBoots, options: () => state.build.options.boots },
  extra: { list: () => state.build.extras, original: () => state.originalExtras, options: (slot) => state.build.options.extras[slot] },
  rune: { list: () => state.build.runes, original: () => state.originalRunes, options: (slot) => state.build.options.runes[slot] },
};

function openPicker(kind, slot) {
  state.picker = { kind, slot };
  const { list, original } = PICKER_SLOTS[kind];
  const current = list()[slot].name;
  $("sheetTitle").textContent = `Swap ${current}`;
  $("sheetReset").classList.toggle("hidden", current === original()[slot]);
  $("sheetSearch").value = "";
  $("sheetSearch").placeholder = kind === "rune" ? "Search runes" : "Search items";
  renderPicker();
  $("sheet").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}
function closePicker() {
  $("sheet").classList.add("hidden");
  document.body.style.overflow = "";
}

function pickButton(entry, current, taken, extra = "", suggestion = null) {
  const isCurrent = entry.name === current, inUse = !isCurrent && taken.includes(entry.name);
  const why = suggestion ? `<small class="why ${suggestion.matchup ? "matchup" : ""}">${escapeHtml(suggestion.why)}</small>` : "";
  return `<button class="pick ${isCurrent ? "current" : ""} ${suggestion ? "suggestion" : ""}" data-name="${escapeHtml(entry.name)}" ${inUse ? 'disabled title="Already picked"' : ""}>
    ${icon(entry)}<span>${extra}${escapeHtml(entry.name)}${why}</span></button>`;
}

const RUNE_TREES = ["Domination", "Precision", "Resolve", "Sorcery"];
const TIER_RANK = { "S+": 0, S: 1, A: 2, B: 3, C: 4, D: 5 };

function renderPicker() {
  const { kind, slot } = state.picker, query = $("sheetSearch").value.trim().toLowerCase();
  const matches = (name) => !query || name.toLowerCase().includes(query);
  const shown = new Set(); // while searching, list each entry once, under its first group
  const suggestions = (PICKER_SLOTS[kind].options(slot) || []).filter((o) => matches(o.name));
  let groups;
  if (kind !== "rune") {
    // Everything already in the full build counts as taken, so an item can't be picked twice.
    const taken = [...state.build.boots, ...state.build.core, ...state.build.extras].map((i) => i.name);
    const current = PICKER_SLOTS[kind].list()[slot].name;
    const wantBoots = kind === "boots";
    groups = itemGroupOrder().map((group) => {
      const items = state.items.filter((i) => i.categories.includes("Boots") === wantBoots && matches(i.name) && !(query && shown.has(i.name)) &&
        (wantBoots || (group === "Other" ? !i.categories.some((c) => ITEM_GROUPS.includes(c)) : i.categories.includes(group))));
      items.forEach((i) => shown.add(i.name));
      return [wantBoots ? "Boots" : group, items.map((i) => pickButton(i, current, taken))];
    });
    if (wantBoots) groups = groups.slice(0, 1);
    groups.unshift(["Suggested", suggestions.map((o) => pickButton({ ...itemByName(o.name), ...o }, current, taken, "", o))]);
  } else {
    const page = state.build.runes.map((r) => r.name);
    const tree = runeByName(page[slot]).tree || "";
    const trees = slot === 0 ? ["Keystone"] : [tree, ...RUNE_TREES.filter((t) => t !== tree)].filter(Boolean);
    groups = trees.map((t) => {
      const runes = state.runeList
        .filter((r) => r.tree === t && (slot === 0 ? r.kind === "keystone" : r.kind === "minor") && matches(r.name))
        .sort((a, b) => (TIER_RANK[a.tier] ?? 9) - (TIER_RANK[b.tier] ?? 9) || a.name.localeCompare(b.name));
      return [t === "Keystone" ? "Keystones" : t, runes.map((r) => pickButton(r, page[slot], page, `${tierBadge(r.tier)} `))];
    });
    groups.unshift(["Suggested", suggestions.map((o) => pickButton({ ...runeByName(o.name), ...o }, page[slot], page, "", o))]);
  }
  $("sheetBody").innerHTML = groups.filter(([, buttons]) => buttons.length)
    .map(([label, buttons]) => `<h3>${label}</h3><div class="pick-grid ${label === "Suggested" ? "suggested" : ""}">${buttons.join("")}</div>`).join("")
    || `<p class="muted">Nothing matches "${escapeHtml(query)}".</p>`;
}

async function applyPick(name) {
  const { kind, slot } = state.picker;
  PICKER_SLOTS[kind].list()[slot] = kind === "rune" ? runeByName(name) : itemByName(name);
  $("result").innerHTML = "";
  closePicker();
  renderBuild();
  await savePreferences();
}
async function loadMatchup() {
  const me = $("me").value, vs = $("vs").value;
  $("matchupTitle").textContent = `Playing against ${vs}`;
  const m = await api(`/api/matchup?me=${encodeURIComponent(me)}&vs=${encodeURIComponent(vs)}&position=${state.position}`);
  if (me !== $("me").value || vs !== $("vs").value) return; // a newer pick replaced this one while it loaded
  renderVerdict(m);
  renderCounterStrip();
  const tier = m.enemy_tiers[state.position];
  const laneLine = (name, s) => s && s.pick != null
    ? `<div><strong>${escapeHtml(name)}</strong> ${pct(s.win)} win · ${pct(s.pick)} pick · ${pct(s.ban)} ban</div>` : "";
  const lines = laneLine(me, m.your_lane_stats) + laneLine(vs, m.enemy_lane_stats);
  $("laneStats").innerHTML = lines
    ? `<div class="muted">This patch in ${LANES[state.position]}, ${escapeHtml(state.serverBracket)} (not head-to-head):</div>${lines}` : "";
  $("matchupTags").innerHTML =
    (tier ? `<span class="tag">${LANES[state.position]} ${tierBadge(tier)}</span>` : "") +
    (m.enemy_damage_type ? `<span class="tag ${m.enemy_damage_type}">${m.enemy_damage_type} damage</span>` : "") +
    (m.enemy_heals ? `<span class="tag">Heals: consider anti-heal</span>` : "");
  $("matchupTips").innerHTML = m.has_tips
    ? m.how_to_play_against_enemy.map((t) => `<li>${escapeHtml(t)}</li>`).join("")
    : `<li class="muted">No matchup tips for ${escapeHtml(me)} against ${escapeHtml(vs)} yet. The AI button can still help.</li>`;
  $("synergies").innerHTML = m.your_synergies.length
    ? `<h3>${escapeHtml(me)} pairs well with</h3><div class="strip">${m.your_synergies.map((s) => {
        const c = champ(s.name);
        return `${c ? `<img src="${c.icon}" alt="">` : ""}<span class="muted">${escapeHtml(s.name)} (${LANES[s.position] || s.position})</span>`;
      }).join("")}</div>`
    : "";
}

function updatePortraits() {
  const portrait = (name) => (champ(name) || {}).icon || "";
  $("meIcon").src = portrait($("me").value);
  $("vsIcon").src = portrait($("vs").value);
}

async function refreshView({ build = true } = {}) {
  updatePortraits();
  $("result").innerHTML = "";
  // One champion's missing build or matchup shouldn't break the rest of the page.
  const pick = `${$("me").value}|${$("vs").value}|${state.position}`;
  const [buildResult, matchupResult] = await Promise.allSettled([build ? loadBuild() : null, loadMatchup()]);
  if (pick !== `${$("me").value}|${$("vs").value}|${state.position}`) return; // outdated: a newer pick is loading
  if (buildResult.status === "rejected") showBuildError(buildResult.reason);
  if (matchupResult.status === "rejected") $("matchupTips").innerHTML = `<li class="muted">${escapeHtml(matchupResult.reason.message)}</li>`;
}

function showBuildError(error) {
  state.build = null;
  $("core").innerHTML = `<p class="muted">${escapeHtml(error.message)}. Try another champion.</p>`;
  ["boots", "final", "situational", "runes", "spells", "coreChoices", "runeChoices", "serverBoots", "serverSpells"].forEach((id) => ($(id).innerHTML = ""));
  $("buildState").textContent = "";
  $("resetBuild").classList.add("hidden");
}

async function setPosition(pos) {
  state.position = pos;
  try { localStorage.setItem("position", pos); } catch {}
  renderLanes();
  closePoolEditor();
  state.counters = [];
  fillVs();
  await loadCounters();
  renderEnemies();
  await refreshView();
}

// Item picker: a bottom sheet with icons, grouped by category (lane-relevant groups first).
function openPoolEditor() {
  const pos = state.position;
  state.poolDraft = new Set(state.profile[pos] || []);
  $("poolLane").textContent = LANES[pos];
  $("poolList").innerHTML = (state.byPosition[pos] || []).map((c) =>
    `<button class="pool-pick" data-name="${escapeHtml(c.name)}" aria-pressed="${state.poolDraft.has(c.name)}">
      <img src="${c.icon}" alt="">${tierBadge(c.positions[pos])} ${escapeHtml(c.name)}</button>`).join("");
  $("poolEditor").classList.remove("hidden");
  $("editPool").classList.add("hidden");
}

function closePoolEditor() {
  $("poolEditor").classList.add("hidden");
  $("editPool").classList.remove("hidden");
}

async function savePool() {
  const pos = state.position;
  // Keep the existing order, append new picks in tier order.
  const kept = (state.profile[pos] || []).filter((n) => state.poolDraft.has(n));
  const added = (state.byPosition[pos] || []).map((c) => c.name).filter((n) => state.poolDraft.has(n) && !kept.includes(n));
  try {
    state.profile = await api("/api/profile", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...state.profile, [pos]: [...kept, ...added] }),
    });
  } catch (e) {
    alert(`Couldn't save your pool: ${e.message}`);
    return;
  }
  closePoolEditor();
  const current = $("me").value;
  fillMe(current);
  fillVs($("vs").value);
  if ($("me").value !== current) await refreshView();
}

async function tailor() {
  const button = $("tailor");
  if (!state.build) return;
  const swaps = state.build.core
    .map((item, slot) => ({ remove: state.original[slot], add: item.name }))
    .filter((s) => s.remove !== s.add);
  const others = [...$("enemies").querySelectorAll("select")].map((s) => s.value).filter(Boolean);
  button.disabled = true;
  button.textContent = "Thinking…";
  $("result").innerHTML = "";
  try {
    const { result, ai_usage } = await api("/api/builds/tailor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        champion: $("me").value, enemies: [$("vs").value, ...others], swaps, position: state.position,
        runes: state.build.runes.map((r) => r.name),
      }),
    });
    $("result").innerHTML = renderMarkdown(result);
    showUsage(ai_usage);
  } catch (e) {
    $("result").innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`;
  } finally {
    button.textContent = "Tailor build with AI";
    button.disabled = false;
    loadUsage();
  }
}

async function showMeta() {
  const m = await api("/api/meta");
  $("patch").textContent = m.patch ? `Patch ${m.patch}` : "";
  state.serverBracket = (m.server && m.server.bracket) || "Diamond+";
  const fetched = m.fetched ? `Data fetched ${m.fetched.slice(0, 10)}` : "No data yet";
  const busy = m.update.state === "checking" || m.update.state === "updating";
  $("dataLine").textContent = m.update.message || fetched;
  return { busy, hasData: Boolean(m.patch) };
}

// Each person has their own limit. Checking it never pops up the token prompt.
async function loadUsage() {
  try {
    showUsage(await api("/api/usage", {}, true));
  } catch {
    $("whoami").textContent = "";
    $("aiUsage").textContent = "5 custom builds per person every 48h. Open your personal link to sign in.";
  }
}

function showUsage(u) {
  if (!u) return;
  $("whoami").textContent = u.user && u.user !== "local" ? `Signed in as ${u.user}` : "";
  const wait = u.remaining ? "" : ` Next one in ${u.next_free_in_hours}h.`;
  $("aiUsage").textContent = `${u.remaining} of ${u.limit} custom builds left for you (per ${u.window_hours}h). Repeats are free.${wait}`;
  $("tailor").disabled = u.remaining === 0;
}

async function checkForUpdate() {
  try {
    await api("/api/refresh", { method: "POST" });
  } catch (e) {
    $("dataLine").textContent = e.message;
    return;
  }
  const poll = setInterval(async () => {
    const { busy } = await showMeta();
    if (!busy) { clearInterval(poll); location.reload(); }
  }, 3000);
}


// Press and hold (or right-click) an item or rune to see its details.
const HOLD_MS = 450;
let holdTimer = null;
let suppressNextClick = false;

function infoHtml(name) {
  const item = state.items.find((i) => i.name === name);
  if (item) {
    const d = item.details;
    if (!d) return `<p class="muted">No stats available for this item yet.</p>`;
    return `
      ${d.summary ? `<p class="info-summary">${escapeHtml(d.summary)}</p>` : ""}
      ${d.gold ? `<p class="info-gold">${d.gold} gold</p>` : ""}
      ${d.stats.length ? `<ul class="info-stats">${d.stats.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}
      ${d.effects.map((e) => `<p><strong>${escapeHtml(e.name)}:</strong> ${escapeHtml(e.text)}</p>`).join("")}
      ${d.tip ? `<p class="muted">${escapeHtml(d.tip)}</p>` : ""}`;
  }
  const rune = state.runeList.find((r) => r.name === name);
  if (rune) {
    const kind = rune.kind === "keystone" ? "Keystone" : `${rune.tree} rune`;
    return `<p>${tierBadge(rune.tier)} ${escapeHtml(kind)}</p>
      <p class="muted">Rune descriptions aren't available from our data sources yet.</p>`;
  }
  return null;
}

function showInfo(name) {
  const body = infoHtml(name);
  if (!body) return false;
  const entry = state.items.find((i) => i.name === name) || state.runeList.find((r) => r.name === name);
  $("infoTitle").innerHTML = `${icon({ ...entry, name })}<span>${escapeHtml(name)}</span>`;
  $("infoBody").innerHTML = body;
  $("info").classList.remove("hidden");
  return true;
}

function closeInfo() {
  $("info").classList.add("hidden");
}

function setUpHoldForInfo() {
  const cancel = () => { clearTimeout(holdTimer); holdTimer = null; };
  document.addEventListener("pointerdown", (e) => {
    const target = e.target.closest("[data-info]");
    if (!target || target.closest("#info")) return;
    cancel();
    holdTimer = setTimeout(() => {
      holdTimer = null;
      if (showInfo(target.dataset.info)) suppressNextClick = true;
    }, HOLD_MS);
  });
  ["pointerup", "pointercancel", "pointerleave", "scroll"].forEach((t) => document.addEventListener(t, cancel, true));
  // Some phones send no click after a long press; don't let the flag swallow the next real tap.
  document.addEventListener("pointerup", () => suppressNextClick && setTimeout(() => (suppressNextClick = false), 400), true);
  document.addEventListener("pointermove", (e) => { if (Math.abs(e.movementX) + Math.abs(e.movementY) > 6) cancel(); });
  // A hold shouldn't also count as a tap (which would open the swap picker or pick an item).
  document.addEventListener("click", (e) => {
    if (suppressNextClick) { suppressNextClick = false; e.stopPropagation(); e.preventDefault(); }
  }, true);
  document.addEventListener("contextmenu", (e) => {
    const target = e.target.closest("[data-info]");
    if (target) { e.preventDefault(); cancel(); showInfo(target.dataset.info); }
  });
  $("infoClose").addEventListener("click", closeInfo);
  $("info").addEventListener("click", (e) => e.target === $("info") && closeInfo());
  document.addEventListener("keydown", (e) => e.key === "Escape" && closeInfo());
}

function signInFromLink() {
  const key = new URLSearchParams(location.hash.slice(1)).get("key");
  if (!key) return;
  tokenStore.set(key.trim());
  history.replaceState(null, "", location.pathname + location.search); // keep the key out of history and screenshots
}

async function init() {
  signInFromLink();
  const { busy, hasData } = await showMeta();
  if (!hasData) {
    $("result").innerHTML = `<p class="muted">Downloading champion data for the first time. This takes a few minutes…</p>`;
    if (busy) setTimeout(init, 5000);
    return;
  }
  let positions;
  [state.all, state.items, state.runeList, state.profile, ...positions] = await Promise.all([
    api("/api/champions"), api("/api/items"), api("/api/runes"), api("/api/profile"),
    ...Object.keys(LANES).map((p) => api(`/api/champions?position=${p}`)),
  ]);
  Object.keys(LANES).forEach((p, i) => (state.byPosition[p] = positions[i]));

  $("lanes").addEventListener("click", (e) => { const b = e.target.closest(".lane"); if (b) setPosition(b.dataset.pos); });
  $("me").addEventListener("change", () => refreshView());
  $("vs").addEventListener("change", async () => {
    const before = $("me").value;
    await loadCounters();
    refreshView(); // the build adapts to the opponent
  });
  $("counterStrip").addEventListener("click", (e) => {
    const pick = e.target.closest(".counter-pick");
    if (!pick) return;
    $("me").value = pick.dataset.champ;
    refreshView();
  });
  const openFrom = (e) => { const item = e.target.closest(".item"); if (item) openPicker("item", Number(item.dataset.slot)); };
  $("core").addEventListener("click", openFrom);
  $("core").addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), openFrom(e)));
  const openRune = (e) => { const r = e.target.closest(".rune"); if (r) openPicker("rune", Number(r.dataset.runeSlot)); };
  $("runes").addEventListener("click", openRune);
  $("runes").addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), openRune(e)));
  $("resetBuild").addEventListener("click", resetBuild);
  const onChoice = (e) => { const c = e.target.closest(".choice"); if (c) applyChoice(c.dataset.kind, c.dataset.key); };
  $("final").addEventListener("click", (e) => {
    const slot = e.target.closest(".slot");
    if (slot && slot.dataset.bootsSlot != null) openPicker("boots", 0);
    else if (slot) openPicker("extra", Number(slot.dataset.extraSlot));
  });
  $("coreChoices").addEventListener("click", onChoice);
  $("runeChoices").addEventListener("click", onChoice);
  $("sheetBody").addEventListener("click", (e) => { const p = e.target.closest(".pick"); if (p && !p.disabled) applyPick(p.dataset.name); });
  $("sheetSearch").addEventListener("input", renderPicker);
  $("sheetReset").addEventListener("click", () => {
    const { kind, slot } = state.picker;
    applyPick(PICKER_SLOTS[kind].original()[slot]);
  });
  $("sheetClose").addEventListener("click", closePicker);
  $("sheet").addEventListener("click", (e) => e.target === $("sheet") && closePicker());
  document.addEventListener("keydown", (e) => e.key === "Escape" && closePicker());
  $("editPool").addEventListener("click", openPoolEditor);
  $("poolList").addEventListener("click", (e) => {
    const b = e.target.closest(".pool-pick"); if (!b) return;
    const n = b.dataset.name;
    state.poolDraft.has(n) ? state.poolDraft.delete(n) : state.poolDraft.add(n);
    b.setAttribute("aria-pressed", state.poolDraft.has(n));
  });
  $("savePool").addEventListener("click", savePool);
  $("tailor").addEventListener("click", tailor);
  setUpHoldForInfo();
  $("checkUpdate").addEventListener("click", checkForUpdate);
  updateTokenLink();
  $("signOut").addEventListener("click", () => {
    if (tokenStore.get()) tokenStore.set("");
    else askForToken();
    location.reload();
  });
  loadUsage();
  await setPosition(state.position in LANES ? state.position : "baron");
}

init().catch((e) => { $("result").innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`; });
