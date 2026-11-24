"use strict";

const POLL_MS = 60_000;
const STALE_MIN = 35;

const I18N = {
  fr: {
    calTitle: "Calendrier éco — cette semaine",
    calHint: "Annonces programmées qui font bouger le marché. Les prix bougent à la seconde où elles tombent.",
    topTitle: "Plus gros titres — 24 h",
    all: "Tout",
    stocks: "Actions",
    impHigh: "Fort",
    impMed: "Fort + moyen",
    search: "Rechercher (ex. Fed, Nvidia, ETF)…",
    high: "fort", medium: "moyen", low: "faible", new: "nouveau",
    sources: (n) => `${n} sources`,
    also: "Aussi :",
    updated: (r) => `Mis à jour ${r}`,
    stale: (r) => `Données en retard (${r})`,
    loading: "Chargement…",
    notifyOff: "🔔 Alertes : off",
    notifyOn: "🔔 Alertes : on",
    notifyDenied: "🔕 Alertes bloquées",
    notifyTitle: "Market Radar — news à fort impact",
    newBanner: (n) => `${n} nouvelle(s) news depuis ta dernière visite — afficher`,
    empty: "Rien ne correspond à ces filtres.",
    noCal: "Calendrier indisponible pour le moment.",
    now: "maintenant",
    live: "publié",
    in: (s) => `dans ${s}`,
    cats: { macro: "Macro / Fed", regulation: "Régulation", geopolitics: "Géopolitique", security: "Hacks", earnings: "Résultats" },
    disclaimer:
      "Les news arrivent avec 10 à 30 min de retard (flux RSS publics, actualisés par GitHub Actions). Les pros les ont en millisecondes : ce site sert à ne pas être pris par surprise, pas à battre le marché. Le score d'impact est calculé par mots-clés et peut se tromper. Rien ici n'est un conseil en investissement.",
    feeds: (ok, n) => `${ok}/${n} sources en ligne`,
  },
  en: {
    calTitle: "Economic calendar — this week",
    calHint: "Scheduled releases that move markets. Prices react the second they drop.",
    topTitle: "Biggest stories — 24 h",
    all: "All",
    stocks: "Stocks",
    impHigh: "High",
    impMed: "High + medium",
    search: "Search (e.g. Fed, Nvidia, ETF)…",
    high: "high", medium: "medium", low: "low", new: "new",
    sources: (n) => `${n} sources`,
    also: "Also:",
    updated: (r) => `Updated ${r}`,
    stale: (r) => `Data delayed (${r})`,
    loading: "Loading…",
    notifyOff: "🔔 Alerts: off",
    notifyOn: "🔔 Alerts: on",
    notifyDenied: "🔕 Alerts blocked",
    notifyTitle: "Market Radar — high-impact news",
    newBanner: (n) => `${n} new stor${n > 1 ? "ies" : "y"} since your last visit — show`,
    empty: "Nothing matches these filters.",
    noCal: "Calendar unavailable right now.",
    now: "now",
    live: "released",
    in: (s) => `in ${s}`,
    cats: { macro: "Macro / Fed", regulation: "Regulation", geopolitics: "Geopolitics", security: "Hacks", earnings: "Earnings" },
    disclaimer:
      "News arrives 10–30 min late (public RSS feeds, refreshed by GitHub Actions). Pros get it in milliseconds: this site keeps you from being caught off guard, it won't beat the market. The impact score is keyword-based and can be wrong. Nothing here is investment advice.",
    feeds: (ok, n) => `${ok}/${n} sources online`,
  },
};

const store = {
  get(k, d) { try { const v = localStorage.getItem("mr-" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("mr-" + k, JSON.stringify(v)); } catch { /* private mode */ } },
};

const state = {
  lang: store.get("lang", "fr"),
  market: store.get("market", "all"),
  impact: store.get("impact", "medium"),
  cat: null,
  q: "",
  news: null,
  cal: null,
  known: null, // links seen during this session (for alerts)
  lastVisit: store.get("lastVisit", null),
  onlyNew: false,
};

const $ = (s) => document.querySelector(s);
const t = (k) => I18N[state.lang][k];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function rel(date) {
  const rtf = new Intl.RelativeTimeFormat(state.lang, { numeric: "auto", style: "short" });
  const s = (new Date(date) - Date.now()) / 1000;
  const a = Math.abs(s);
  if (a < 60) return t("now");
  if (a < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(s / 3600), "hour");
  return rtf.format(Math.round(s / 86400), "day");
}

function dur(ms) {
  const m = Math.round(ms / 60000);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ${String(m % 60).padStart(2, "0")}`;
  return `${Math.floor(h / 24)} j ${h % 24} h`.replace(" j ", state.lang === "fr" ? " j " : "d ");
}

const hhmm = (d) => new Date(d).toLocaleTimeString(state.lang, { hour: "2-digit", minute: "2-digit" });

/* ---------- data ---------- */
async function load(path) {
  const r = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

async function refresh(first = false) {
  try {
    const [news, cal] = await Promise.all([load("data/news.json"), load("data/calendar.json").catch(() => null)]);
    const fresh = state.known ? news.items.filter((i) => !state.known.has(i.link)) : [];
    state.news = news;
    if (cal) state.cal = cal;
    if (!state.known) state.known = new Set();
    news.items.forEach((i) => state.known.add(i.link));
    if (!first) alertFor(fresh);
    render();
  } catch (e) {
    $("#status-text").textContent = "offline";
    $("#status").classList.add("stale");
  }
}

/* ---------- alerts ---------- */
function notifyState() {
  if (!("Notification" in window)) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  return store.get("notify", false) && Notification.permission === "granted" ? "on" : "off";
}

function paintNotify() {
  const b = $("#notify-btn");
  const s = notifyState();
  b.hidden = s === "unsupported";
  b.textContent = s === "on" ? t("notifyOn") : s === "denied" ? t("notifyDenied") : t("notifyOff");
  b.classList.toggle("on", s === "on");
}

$("#notify-btn").addEventListener("click", async () => {
  const s = notifyState();
  if (s === "on") store.set("notify", false);
  else if (s === "off") {
    const p = await Notification.requestPermission();
    store.set("notify", p === "granted");
  }
  paintNotify();
});

let flashTimer = null;
function alertFor(fresh) {
  const big = fresh.filter((i) => i.impact === "high");
  if (!big.length) return;
  // Tab title counter, even without notification permission
  let n = 0;
  clearInterval(flashTimer);
  flashTimer = setInterval(() => {
    document.title = n++ % 2 ? "Market Radar" : `(${big.length}) 🔴 ${big[0].title.slice(0, 40)}`;
  }, 1200);
  if (notifyState() === "on") {
    big.slice(0, 3).forEach((i) => {
      const note = new Notification(t("notifyTitle"), { body: `${i.title}\n— ${i.source}`, tag: i.link });
      note.onclick = () => { window.open(i.link, "_blank", "noopener"); note.close(); };
    });
  }
}
window.addEventListener("focus", () => { clearInterval(flashTimer); document.title = "Market Radar"; });

/* ---------- render ---------- */
function render() {
  if (!state.news) return;
  renderStatus();
  renderNews();
  renderTop();
  renderCalendar();
  const f = state.news.feeds || {};
  const ok = Object.values(f).filter((v) => v.startsWith("ok")).length;
  $("#feeds-status").textContent = t("feeds")(ok, Object.keys(f).length) + " · " + Object.keys(f).join(", ");
}

function renderStatus() {
  const u = state.news.updated;
  const late = (Date.now() - new Date(u)) / 60000 > STALE_MIN;
  $("#status").classList.toggle("stale", late);
  $("#status-text").textContent = (late ? t("stale") : t("updated"))(rel(u));
}

function matches(i) {
  if (state.market !== "all" && !i.markets.includes(state.market)) return false;
  if (state.impact === "high" && i.impact !== "high") return false;
  if (state.impact === "medium" && i.impact === "low") return false;
  if (state.cat && !i.categories.includes(state.cat)) return false;
  if (state.onlyNew && !isNew(i)) return false;
  if (state.q) {
    const hay = (i.title + " " + i.summary + " " + i.source + " " + i.assets.join(" ")).toLowerCase();
    if (!state.q.split(/\s+/).every((w) => hay.includes(w))) return false;
  }
  return true;
}

const isNew = (i) => state.lastVisit && new Date(i.published) > new Date(state.lastVisit);

function renderNews() {
  const items = state.news.items.filter(matches);
  $("#news").innerHTML = items.map(card).join("");
  $("#empty").hidden = items.length > 0;
  $("#empty").textContent = t("empty");

  const newCount = state.news.items.filter((i) => isNew(i) && i.impact !== "low").length;
  const banner = $("#new-banner");
  banner.hidden = !newCount || state.onlyNew;
  banner.textContent = t("newBanner")(newCount);
}

function card(i) {
  const also = i.others.length
    ? `<div class="also">${t("also")} ${i.others.map((o) => `<a href="${esc(o.link)}" target="_blank" rel="noopener">${esc(o.source)}</a>`).join(", ")}</div>`
    : "";
  const tags = [
    ...i.assets.map((a) => `<span class="tag">${esc(a)}</span>`),
    ...i.categories.map((c) => `<span class="tag cat">${esc(t("cats")[c] || c)}</span>`),
  ].join("");
  return `<li class="${i.impact}${isNew(i) && i.impact === "high" ? " fresh" : ""}">
    <div>
      <div class="row1">
        <span class="badge ${i.impact}">${t(i.impact)}</span>
        ${isNew(i) ? `<span class="badge new">${t("new")}</span>` : ""}
        <span class="time" title="${esc(new Date(i.published).toLocaleString(state.lang))}">${hhmm(i.published)} · ${rel(i.published)}</span>
        <span>${esc(i.source)}</span>
        ${i.sources > 1 ? `<span class="multi">● ${t("sources")(i.sources)}</span>` : ""}
      </div>
      <h3><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.title)}</a></h3>
      ${i.summary && i.summary !== i.title ? `<p class="sum">${esc(i.summary)}</p>` : ""}
      ${tags ? `<div class="tags">${tags}</div>` : ""}
      ${also}
    </div>
  </li>`;
}

function renderTop() {
  const day = Date.now() - 86400000;
  const top = state.news.items
    .filter((i) => new Date(i.published) > day && (state.market === "all" || i.markets.includes(state.market)))
    .sort((a, b) => b.score - a.score || b.sources - a.sources)
    .slice(0, 6);
  $("#top").innerHTML = top
    .map((i) => `<li><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.title)}</a>
      <div class="meta"><span class="badge ${i.impact}">${t(i.impact)}</span> ${esc(i.source)} · ${rel(i.published)}</div></li>`)
    .join("");
}

function renderCalendar() {
  const el = $("#calendar");
  const evs = state.cal?.events || [];
  if (!evs.length) { el.innerHTML = `<li class="day">${t("noCal")}</li>`; return; }
  const now = Date.now();
  const today = new Date().toDateString();
  let lastDay = "";
  const rows = [];
  for (const e of evs) {
    const d = new Date(e.date);
    const diff = d - now;
    // keep today's past events (dimmed), drop older ones
    if (diff < 0 && d.toDateString() !== today && diff < -3 * 3600000) continue;
    const dayLabel = d.toLocaleDateString(state.lang, { weekday: "long", day: "numeric", month: "short" });
    if (dayLabel !== lastDay) { rows.push(`<li class="day">${esc(dayLabel)}</li>`); lastDay = dayLabel; }
    const cls = [e.impact, diff < 0 ? "past" : diff < 3 * 3600000 ? "soon" : ""].join(" ");
    const when = diff < 0 ? (diff > -3600000 ? `${t("live")} ${rel(e.date)}` : hhmm(e.date)) : diff < 86400000 ? t("in")(dur(diff)) : hhmm(e.date);
    const meta = [e.forecast && `prév. ${e.forecast}`, e.previous && `préc. ${e.previous}`].filter(Boolean).join(" · ");
    const metaEn = [e.forecast && `fcst ${e.forecast}`, e.previous && `prev ${e.previous}`].filter(Boolean).join(" · ");
    rows.push(`<li class="${cls}">
      <span class="cur">${esc(e.country)}</span>
      <div><div class="ev-title">${esc(e.title)}</div><div class="ev-meta">${hhmm(e.date)}${meta ? " · " + esc(state.lang === "fr" ? meta : metaEn) : ""}</div></div>
      <span class="when">${esc(when)}</span>
    </li>`);
  }
  el.innerHTML = rows.join("");
}

/* ---------- controls ---------- */
function paintStatic() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
  $("#f-search").placeholder = t("search");
  $("#lang-btn").textContent = state.lang === "fr" ? "EN" : "FR";
  $("#f-cats").innerHTML = Object.entries(t("cats"))
    .map(([k, v]) => `<button class="chip${state.cat === k ? " on" : ""}" data-v="${k}">${esc(v)}</button>`).join("");
  ["market", "impact"].forEach((k) =>
    document.querySelectorAll(`#f-${k} button`).forEach((b) => b.classList.toggle("on", b.dataset.v === state[k])));
  paintNotify();
  mountTicker();
}

function bindSeg(id, key) {
  $(id).addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    state[key] = b.dataset.v;
    store.set(key, state[key]);
    paintStatic();
    render();
  });
}
bindSeg("#f-market", "market");
bindSeg("#f-impact", "impact");

$("#f-cats").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  state.cat = state.cat === b.dataset.v ? null : b.dataset.v;
  paintStatic();
  render();
});
$("#f-search").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); render(); });
$("#new-banner").addEventListener("click", () => { state.onlyNew = true; state.impact = "low"; paintStatic(); render(); });
$("#lang-btn").addEventListener("click", () => {
  state.lang = state.lang === "fr" ? "en" : "fr";
  store.set("lang", state.lang);
  paintStatic();
  render();
});

let tickerLang = null;
function mountTicker() {
  if (tickerLang === state.lang) return;
  tickerLang = state.lang;
  const box = document.querySelector(".tradingview-widget-container");
  box.innerHTML = '<div class="tradingview-widget-container__widget"></div>';
  const s = document.createElement("script");
  s.src = "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js";
  s.async = true;
  const fr = state.lang === "fr";
  s.innerHTML = JSON.stringify({
    symbols: [
      { proName: "FOREXCOM:SPXUSD", title: "S&P 500" },
      { proName: "FOREXCOM:NSXUSD", title: "Nasdaq 100" },
      { proName: "BITSTAMP:BTCUSD", title: "Bitcoin" },
      { proName: "BITSTAMP:ETHUSD", title: "Ethereum" },
      { proName: "COINBASE:SOLUSD", title: "Solana" },
      { proName: "TVC:GOLD", title: fr ? "Or" : "Gold" },
      { proName: "TVC:USOIL", title: fr ? "Pétrole WTI" : "WTI Oil" },
      { proName: "FX_IDC:EURUSD", title: "EUR/USD" },
    ],
    showSymbolLogo: true,
    isTransparent: true,
    displayMode: "adaptive",
    colorTheme: "dark",
    locale: fr ? "fr" : "en",
  });
  box.appendChild(s);
}

/* ---------- boot ---------- */
$("#status-text").textContent = t("loading");
paintStatic();
refresh(true);
setInterval(refresh, POLL_MS);
setInterval(() => { if (state.news) { renderStatus(); renderCalendar(); } }, 30_000);
// remember this visit so the next one can highlight what's new
window.addEventListener("pagehide", () => store.set("lastVisit", new Date().toISOString()));
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") store.set("lastVisit", new Date().toISOString());
});
