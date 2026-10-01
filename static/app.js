const $ = (id) => document.getElementById(id);
const LANES = { baron: "Baron", jungle: "Jungle", mid: "Mid", dragon: "Dragon", support: "Support" };
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
  position: "baron", all: [], byPosition: {}, items: [], profile: {},
  build: null, original: [], poolDraft: new Set(),
};
try { state.position = localStorage.getItem("position") || "baron"; } catch {}

// Access token for protected actions (AI builds, saving the pool, patch checks). Kept on this device only.
const tokenStore = {
  get() { try { return localStorage.getItem("accessToken") || ""; } catch { return ""; } },
  set(t) { try { t ? localStorage.setItem("accessToken", t) : localStorage.removeItem("accessToken"); } catch {} },
};

async function api(path, options = {}, retried = false) {
  const headers = { ...(options.headers || {}) };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  const body = await res.json().catch(() => ({}));
  if (res.status === 401 && !retried) {
    const entered = window.prompt("Enter the access token for this app (APP_TOKEN in .env):");
    if (entered) {
      tokenStore.set(entered.trim());
      $("signOut").classList.remove("hidden");
      return api(path, options, true);
    }
  }
  if (res.status === 401) tokenStore.set("");
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const laneIcon = (p) => `/icons/wrf/lanes/${p}.png`;
const tierBadge = (t) => (t ? `<span class="tier ${t}">${t}</span>` : "");
const champ = (name) => state.all.find((c) => c.name === name);
const icon = (entry) => (entry.icon ? `<img src="${entry.icon}" alt="" title="${escapeHtml(entry.name)}">` : `<span class="badge" title="${escapeHtml(entry.name)}">${escapeHtml(entry.name.slice(0, 2))}</span>`);

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

function option(c, position, selected) {
  const tier = c.positions[position];
  return `<option value="${escapeHtml(c.name)}" ${c.name === selected ? "selected" : ""}>${tier ? tier + " · " : ""}${escapeHtml(c.name)}</option>`;
}

function fillMe(selected) {
  const pos = state.position, pool = state.profile[pos] || [];
  const ranked = state.byPosition[pos] || [];
  const mine = pool.map(champ).filter(Boolean);
  const others = ranked.filter((c) => !pool.includes(c.name));
  selected = selected && (pool.includes(selected) || ranked.some((c) => c.name === selected)) ? selected : (mine[0] || ranked[0]).name;
  $("me").innerHTML =
    (mine.length ? `<optgroup label="My pool">${mine.map((c) => option(c, pos, selected)).join("")}</optgroup>` : "") +
    `<optgroup label="${LANES[pos]} tier list">${others.map((c) => option(c, pos, selected)).join("")}</optgroup>`;
  $("me").value = selected;
}

function fillVs(selected) {
  const ranked = state.byPosition[state.position] || [];
  const me = $("me").value;
  const choices = ranked.filter((c) => c.name !== me);
  selected = choices.some((c) => c.name === selected) ? selected : choices[0].name;
  $("vs").innerHTML = choices.map((c) => option(c, state.position, selected)).join("");
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
  $("core").innerHTML = b.core.map((item, slot) => {
    const swapped = item.name !== state.original[slot];
    return `<div class="item ${swapped ? "swapped" : ""}" data-slot="${slot}" role="button" tabindex="0"
        aria-label="Swap ${escapeHtml(item.name)}">
      ${icon(item)}<div>${escapeHtml(item.name)}</div>
      <div class="swap">${swapped ? `was ${escapeHtml(state.original[slot])}` : "tap to swap"}</div>
    </div>`;
  }).join("");
  $("boots").innerHTML = b.boots.map((i) => `${icon(i)}<span class="muted">${escapeHtml(i.name)}</span>`).join("");
  // The full build follows your core swaps.
  const swappedFor = Object.fromEntries(state.original.map((name, slot) => [name, b.core[slot]]));
  $("final").innerHTML = b.final.map((i) => swappedFor[i.name] || i).map(icon).join("");
  $("sitBlock").classList.toggle("hidden", !b.situational.length);
  $("situational").innerHTML = b.situational.map((s) =>
    `<div class="sit"><span class="when">${escapeHtml(s.when)}</span>${icon(s.replace)}<span>→</span>${icon(s.with)}</div>`).join("");
  $("runes").innerHTML = b.runes.map((r, slot) => {
    const swapped = r.name !== state.originalRunes[slot];
    return `<div class="rune ${slot === 0 ? "keystone" : ""} ${swapped ? "swapped" : ""}" data-rune-slot="${slot}" role="button" tabindex="0"
        aria-label="Swap rune ${escapeHtml(r.name)}">${icon(r)}<span>${escapeHtml(r.name)}</span></div>`;
  }).join("");
  $("spells").innerHTML = [...b.spells, ...b.starting].map((x) => `${icon(x)}<span class="muted">${escapeHtml(x.name)}</span>`).join("");
  const changed = isCustomised();
  $("buildState").textContent = changed ? (state.savedFor === b.name ? "Your saved build" : "Not saved yet") : "Recommended build";
  $("resetBuild").classList.toggle("hidden", !changed);
}

const isCustomised = () =>
  state.build.core.some((i, slot) => i.name !== state.original[slot]) ||
  state.build.runes.some((r, slot) => r.name !== state.originalRunes[slot]);

const itemByName = (name) => state.items.find((i) => i.name === name) || { name, icon: null };
const runeByName = (name) => state.runeList.find((r) => r.name === name) || { name, icon: null };

async function loadBuild() {
  const name = $("me").value;
  const [build, prefs] = await Promise.all([
    api(`/api/champions/${encodeURIComponent(name)}/build`),
    api(`/api/preferences/${encodeURIComponent(name)}`, {}, true).catch(() => ({ saved: null })),
  ]);
  state.build = build;
  state.original = build.core.map((i) => i.name);
  state.originalRunes = build.runes.map((r) => r.name);
  state.savedFor = null;
  const saved = prefs.saved;
  if (saved && saved.core.length === build.core.length && saved.runes.length === build.runes.length) {
    build.core = saved.core.map(itemByName);
    build.runes = saved.runes.map(runeByName);
    state.savedFor = build.name;
  }
  renderBuild();
}

// Saves your item and rune choices for this champion (asks for your access token if needed).
async function savePreferences() {
  const b = state.build;
  try {
    if (isCustomised()) {
      await api(`/api/preferences/${encodeURIComponent(b.name)}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ core: b.core.map((i) => i.name), runes: b.runes.map((r) => r.name) }),
      });
      state.savedFor = b.name;
    } else {
      await api(`/api/preferences/${encodeURIComponent(b.name)}`, { method: "DELETE" });
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
  $("result").innerHTML = "";
  renderBuild();
  await savePreferences();
}

// Picker: a bottom sheet with icons. Items are grouped by category (lane-relevant first),
// runes by tree (keystones for the first slot, the slot's own tree first for the others).
function openPicker(kind, slot) {
  state.picker = { kind, slot };
  const list = kind === "item" ? state.build.core : state.build.runes;
  const original = kind === "item" ? state.original : state.originalRunes;
  const current = list[slot].name;
  $("sheetTitle").textContent = `Swap ${current}`;
  $("sheetReset").classList.toggle("hidden", current === original[slot]);
  $("sheetSearch").value = "";
  $("sheetSearch").placeholder = kind === "item" ? "Search items" : "Search runes";
  renderPicker();
  $("sheet").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closePicker() {
  $("sheet").classList.add("hidden");
  document.body.style.overflow = "";
}

function pickButton(entry, current, taken, extra = "") {
  const isCurrent = entry.name === current, inUse = !isCurrent && taken.includes(entry.name);
  return `<button class="pick ${isCurrent ? "current" : ""}" data-name="${escapeHtml(entry.name)}" ${inUse ? 'disabled title="Already picked"' : ""}>
    ${icon(entry)}${extra}${escapeHtml(entry.name)}</button>`;
}

const RUNE_TREES = ["Domination", "Precision", "Resolve", "Sorcery"];
const TIER_RANK = { "S+": 0, S: 1, A: 2, B: 3, C: 4, D: 5 };

function renderPicker() {
  const { kind, slot } = state.picker, query = $("sheetSearch").value.trim().toLowerCase();
  const matches = (name) => !query || name.toLowerCase().includes(query);
  const shown = new Set(); // while searching, list each entry once, under its first group
  let groups;
  if (kind === "item") {
    const core = state.build.core.map((i) => i.name);
    groups = itemGroupOrder().map((group) => {
      const items = state.items.filter((i) => !i.categories.includes("Boots") && matches(i.name) && !(query && shown.has(i.name)) &&
        (group === "Other" ? !i.categories.some((c) => ITEM_GROUPS.includes(c)) : i.categories.includes(group)));
      items.forEach((i) => shown.add(i.name));
      return [group, items.map((i) => pickButton(i, core[slot], core))];
    });
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
  }
  $("sheetBody").innerHTML = groups.filter(([, buttons]) => buttons.length)
    .map(([label, buttons]) => `<h3>${label}</h3><div class="pick-grid">${buttons.join("")}</div>`).join("")
    || `<p class="muted">Nothing matches "${escapeHtml(query)}".</p>`;
}

async function applyPick(name) {
  const { kind, slot } = state.picker;
  if (kind === "item") state.build.core[slot] = itemByName(name);
  else state.build.runes[slot] = runeByName(name);
  $("result").innerHTML = "";
  closePicker();
  renderBuild();
  await savePreferences();
}

async function loadMatchup() {
  const me = $("me").value, vs = $("vs").value;
  $("matchupTitle").textContent = `Playing against ${vs}`;
  const m = await api(`/api/matchup?me=${encodeURIComponent(me)}&vs=${encodeURIComponent(vs)}`);
  const tier = m.enemy_tiers[state.position];
  $("matchupTags").innerHTML =
    (tier ? `<span class="tag">${LANES[state.position]} ${tierBadge(tier)}</span>` : "") +
    (m.enemy_damage_type ? `<span class="tag ${m.enemy_damage_type}">${m.enemy_damage_type} damage</span>` : "") +
    (m.enemy_heals ? `<span class="tag">Heals: consider anti-heal</span>` : "");
  $("matchupTips").innerHTML = m.has_tips
    ? m.how_to_play_against_enemy.map((t) => `<li>${escapeHtml(t)}</li>`).join("")
    : `<li class="muted">No hand-written tips for ${escapeHtml(vs)} yet. The AI button can still help.</li>`;
}

function updatePortraits() {
  $("meIcon").src = champ($("me").value).icon;
  $("vsIcon").src = champ($("vs").value).icon;
}

async function refreshView({ build = true } = {}) {
  updatePortraits();
  $("result").innerHTML = "";
  await Promise.all([build ? loadBuild() : null, loadMatchup()]);
}

async function setPosition(pos) {
  state.position = pos;
  try { localStorage.setItem("position", pos); } catch {}
  renderLanes();
  closePoolEditor();
  fillMe();
  fillVs();
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
    $("aiUsage").textContent = "5 custom builds per person every 48h. You'll be asked for your access token.";
  }
}

function showUsage(u) {
  if (!u) return;
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

async function init() {
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
  $("me").addEventListener("change", () => { fillVs($("vs").value); refreshView(); });
  $("vs").addEventListener("change", () => refreshView({ build: false }));
  const openFrom = (e) => { const item = e.target.closest(".item"); if (item) openPicker("item", Number(item.dataset.slot)); };
  $("core").addEventListener("click", openFrom);
  $("core").addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), openFrom(e)));
  const openRune = (e) => { const r = e.target.closest(".rune"); if (r) openPicker("rune", Number(r.dataset.runeSlot)); };
  $("runes").addEventListener("click", openRune);
  $("runes").addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), openRune(e)));
  $("resetBuild").addEventListener("click", resetBuild);
  $("sheetBody").addEventListener("click", (e) => { const p = e.target.closest(".pick"); if (p && !p.disabled) applyPick(p.dataset.name); });
  $("sheetSearch").addEventListener("input", renderPicker);
  $("sheetReset").addEventListener("click", () => {
    const { kind, slot } = state.picker;
    applyPick((kind === "item" ? state.original : state.originalRunes)[slot]);
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
  $("checkUpdate").addEventListener("click", checkForUpdate);
  $("signOut").classList.toggle("hidden", !tokenStore.get());
  $("signOut").addEventListener("click", () => { tokenStore.set(""); location.reload(); });
  loadUsage();
  await setPosition(state.position in LANES ? state.position : "baron");
}

init().catch((e) => { $("result").innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`; });
