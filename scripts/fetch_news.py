#!/usr/bin/env python3
"""Fetch market-moving news from public RSS feeds and score it by likely impact.

Writes site/data/news.json and site/data/calendar.json. Standard library only,
so the GitHub Action needs no install step.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from outlook import outlook

OUT = Path(__file__).resolve().parent.parent / "site" / "data"
UA = "Mozilla/5.0 (compatible; market-radar/1.0; +https://github.com/)"
MAX_AGE_H = 48
MAX_ITEMS = 300

# (name, url, kind) — kind: crypto | markets | official
FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "crypto"),
    ("Cointelegraph", "https://cointelegraph.com/rss", "crypto"),
    ("Decrypt", "https://decrypt.co/feed", "crypto"),
    ("The Block", "https://www.theblock.co/rss.xml", "crypto"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/feed", "crypto"),
    ("Investing.com Crypto", "https://www.investing.com/rss/news_301.rss", "crypto"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "markets"),
    ("CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "markets"),
    ("CNBC Finance", "https://www.cnbc.com/id/10000664/device/rss/rss.html", "markets"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "markets"),
    ("MarketWatch Pulse", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse", "markets"),
    ("Investing.com", "https://www.investing.com/rss/news_25.rss", "markets"),
    ("Investing.com Economy", "https://www.investing.com/rss/news_95.rss", "markets"),
    ("Seeking Alpha", "https://seekingalpha.com/market_currents.xml", "markets"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "markets"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", "official"),
    ("SEC", "https://www.sec.gov/news/pressreleases.rss", "official"),
    ("ECB", "https://www.ecb.europa.eu/rss/press.html", "official"),
    ("White House", "https://www.whitehouse.gov/presidential-actions/feed/", "official"),
]

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# --- scoring ---------------------------------------------------------------
# Each rule: (regex, weight). Matched on the lower-cased title (+ a bit of summary at half weight).
RULES = [
    # Central banks & macro data: the things that move everything at once
    (r"\bfomc\b|\bfed(eral reserve)?\b|\bpowell\b|rate (cut|hike|decision)|interest rates?", 3),
    (r"\bcpi\b|\bpce\b|inflation|nonfarm|payrolls|jobs report|unemployment rate|\bgdp\b", 3),
    (r"recession|stagflation|treasury yields?|bond (market|yields?)|10-year", 2),
    (r"\becb\b|lagarde|bank of japan|\bboj\b|bank of england|\bpboc\b", 2),
    # Policy, regulation, law
    (r"\bsec\b|\bcftc\b|gensler|atkins|regulat|lawsuit|indict|charged|court|ruling|settle", 2),
    (r"etf (approv|reject|filing|launch)|spot (bitcoin|ether|eth|sol\w*|xrp) etf|etf flows?|\betfs?\b", 2),
    (r"executive order|tariffs?|sanctions?|trade war|export (ban|controls?)|ban(s|ned)?\b", 3),
    (r"strategic (bitcoin )?reserve|stablecoin (bill|law)|genius act|clarity act|market structure bill", 3),
    (r"government shutdown|debt ceiling|default", 3),
    # Geopolitics / shocks
    (r"\bwar\b|invasion|missile|airstrike|ceasefire|military|nuclear", 3),
    (r"\bopec\b|oil (prices?|surges?|plunges?)|crude|hormuz|tankers?|strait|shipping lanes?", 2),
    (r"probe|investigation|subpoena|raid", 1),
    # Market moves & stress
    (r"(market|stocks?|crypto|bitcoin|btc|prices?|flash|index) crash|crash(es|ed)? (to|below|under)|plunge|tumble|sell-?off|\brout\b|freefall|meltdown|capitulat|bloodbath", 3),
    (r"soar|surge|skyrocket|rall(y|ies)|record high|all-time high|\bath\b|breaks? \$?\d", 2),
    (r"liquidat|margin call|bank run|insolven|bankrupt|chapter 11|collapse|halt(s|ed)? (trading|withdrawals)", 3),
    (r"hack(ed)?\b|exploit|drained|stolen|breach|depeg", 3),
    (r"delist|suspend", 2),
    # Corporate
    (r"earnings|revenue|guidance|beats? estimates|miss(es)? estimates|profit warning", 2),
    (r"merger|acquisition|acquire[sd]?|takeover|buyback|ipo\b|layoffs?|stock split", 2),
    (r"downgrade|upgrade|price target", 1),
    (r"whales?|inflows?|outflows?|treasury (company|firm)|adds? \d[\d,]* (btc|bitcoin)", 1),
]

BIG_NAMES = (
    r"bitcoin|\bbtc\b|ethereum|\beth\b|\bether\b|solana|\bxrp\b|tether|\busdc\b|blackrock|binance|coinbase|"
    r"nvidia|apple|microsoft|tesla|amazon|alphabet|google|\bmeta\b|s&p 500|nasdaq|dow jones|"
    r"trump|white house|china|treasury"
)

FLUFF = (
    r"price prediction|predicts?\b|could (hit|reach)|how to|what is|explained|opinion|podcast|"
    r"sponsored|newsletter|weekly recap|morning brief|top \d+|best \w+ to buy|quiz|webinar|giveaway|"
    r"\?$|here's why|here’s why|analyst says|watch:|video:"
)

MOVE_VERBS = r"\b(up|down|jumps?|soars?|surges?|rises?|gains?|climbs?|rall(y|ies)|falls?|drops?|slides?|sinks?|slumps?|plunges?|tumbles?|dips?|crash(es)?|spikes?)\b"

CATEGORIES = {
    "macro": r"\bfomc\b|\bfed\b|federal reserve|powell|rate (cut|hike|decision)|interest rate|\bcpi\b|\bpce\b|inflation|payrolls|jobs report|unemployment|\bgdp\b|recession|yields?|\becb\b|\bboj\b|bank of (japan|england)|treasury",
    "regulation": r"\bsec\b|\bcftc\b|regulat|lawsuit|court|ruling|indict|charged|bill\b|act\b|law\b|congress|senate|executive order|ban\b|license",
    "geopolitics": r"\bwar\b|invasion|missile|ceasefire|military|tariff|sanction|trade war|china|russia|ukraine|iran|israel|opec|election|nuclear",
    "security": r"hack|exploit|drained|stolen|breach|depeg|scam|rug ?pull",
    "earnings": r"earnings|revenue|guidance|quarter|profit|beats? estimates|miss(es)? estimates",
}

ASSETS = {
    "BTC": r"bitcoin|\bbtc\b",
    "ETH": r"ethereum|\beth\b|\bether\b",
    "SOL": r"solana|\bsol\b",
    "XRP": r"\bxrp\b|ripple",
    "BNB": r"\bbnb\b|binance coin",
    "DOGE": r"dogecoin|\bdoge\b",
    "USDT": r"tether|\busdt\b",
    "USDC": r"\busdc\b|circle",
    "COIN": r"coinbase",
    "MSTR": r"microstrategy|\bmstr\b|michael saylor",
    "NVDA": r"nvidia|\bnvda\b",
    "AAPL": r"\bapple\b|\baapl\b",
    "MSFT": r"microsoft|\bmsft\b",
    "TSLA": r"tesla|\btsla\b",
    "AMZN": r"amazon|\bamzn\b",
    "GOOGL": r"alphabet|google|\bgoogl\b",
    "META": r"\bmeta\b|facebook",
    "S&P 500": r"s&p 500|\bs&p\b|\bspx\b",
    "NASDAQ": r"nasdaq|\bqqq\b",
    "DOW": r"dow jones|\bthe dow\b",
    "GOLD": r"\bgold\b",
    "OIL": r"\boil\b|crude|brent|\bwti\b",
    "USD": r"\bdollar\b|\bdxy\b",
}

CRYPTO_HINT = r"crypto|bitcoin|\bbtc\b|ethereum|\beth\b|solana|stablecoin|token|blockchain|defi|\bnft\b|altcoin|binance|coinbase|tether|xrp|memecoin|web3"
STOCK_HINT = r"stocks?|shares|s&p|nasdaq|dow|wall street|equit|earnings|nyse|ipo|index|futures"

STOP = set(
    "a an the of to in on for and or as at by with from is are was were be been its it this that after before "
    "over under amid into says said new up down vs".split()
)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    out = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        f: dict[str, str] = {}
        for c in el:
            name = local(c.tag)
            if name == "link":
                f.setdefault("link", (c.text or "").strip() or c.attrib.get("href", ""))
            elif name in ("title", "description", "summary", "pubDate", "published", "updated", "date"):
                f.setdefault(name, c.text or "")
        out.append(
            {
                "title": clean(f.get("title")),
                "link": f.get("link", "").strip(),
                "summary": clean(f.get("description") or f.get("summary"))[:300],
                "date": parse_date(f.get("pubDate") or f.get("published") or f.get("date") or f.get("updated")),
            }
        )
    return out


def get_source(src: tuple[str, str, str]) -> tuple[str, list[dict], str | None]:
    name, url, kind = src
    try:
        items = parse_feed(fetch(url))
        for it in items:
            it["source"] = name
            it["kind"] = kind
        return name, items, None
    except Exception as e:  # one dead feed must never break the run
        return name, [], f"{type(e).__name__}: {e}"[:200]


def score(item: dict) -> tuple[int, list[str]]:
    title = item["title"].lower()
    summary = item["summary"].lower()
    s = 0
    hits: set[str] = set()
    for pat, w in RULES:
        if re.search(pat, title):
            s += w
            hits.add(pat)
        elif re.search(pat, summary):
            s += w / 2
    if re.search(BIG_NAMES, title):
        s += 1
    if re.search(FLUFF, title):
        s -= 4
    if item["kind"] == "official":
        s += 2
    # Big % moves in the headline ("up 8.99%", "falls 12%")
    if re.search(MOVE_VERBS, title):
        pcts = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s?%", title)]
        if pcts and max(pcts) >= 5:
            s += 3
        elif pcts and max(pcts) >= 2:
            s += 1
    return round(s), sorted(hits)


def classify(item: dict) -> dict:
    text = (item["title"] + " " + item["summary"]).lower()
    title = item["title"].lower()
    cats = [c for c, pat in CATEGORIES.items() if re.search(pat, title)]
    assets = [a for a, pat in ASSETS.items() if re.search(pat, title)]
    is_crypto = item["kind"] == "crypto" or bool(re.search(CRYPTO_HINT, text))
    is_stock = item["kind"] != "crypto" and (bool(re.search(STOCK_HINT, text)) or bool(assets))
    # Macro and geopolitics hit both markets
    if "macro" in cats or "geopolitics" in cats:
        is_crypto = is_stock = True
    markets = [m for m, on in (("crypto", is_crypto), ("stocks", is_stock)) if on] or ["stocks"]
    return {"categories": cats, "assets": assets, "markets": markets}


def tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9$%.]+", title.lower())
    return {w for w in words if w not in STOP and len(w) > 2}


def cluster(items: list[dict]) -> list[dict]:
    """Group the same story reported by several outlets. More outlets = bigger story."""
    groups: list[dict] = []
    for it in sorted(items, key=lambda x: x["date"]):
        tk = tokens(it["title"])
        best = None
        for g in groups:
            if not tk or not g["_tk"]:
                continue
            j = len(tk & g["_tk"]) / len(tk | g["_tk"])
            if j >= 0.45 and abs((it["date"] - g["_last"]).total_seconds()) < 12 * 3600:
                best = g
                break
        if best is None:
            groups.append({**it, "_tk": tk, "_last": it["date"], "others": []})
        else:
            if it["source"] != best["source"] and all(o["source"] != it["source"] for o in best["others"]):
                best["others"].append({"source": it["source"], "link": it["link"], "date": it["date"]})
            best["_tk"] |= tk
            best["_last"] = it["date"]
    return groups


def build_news(now: datetime) -> dict:
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(get_source, FEEDS))

    status = {name: (err or f"ok ({len(items)})") for name, items, err in results}
    cutoff = now - timedelta(hours=MAX_AGE_H)
    items, seen = [], set()
    for _, its, _ in results:
        for it in its:
            if not it["title"] or not it["link"] or not it["date"]:
                continue
            if it["date"] > now + timedelta(minutes=10) or it["date"] < cutoff:
                continue
            key = it["link"].split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            items.append(it)

    out = []
    for g in cluster(items):
        s, _ = score(g)
        cls = classify(g)
        n_sources = 1 + len(g["others"])
        s += min(n_sources - 1, 3) * 2  # confirmed by several outlets
        level = "high" if s >= 6 else "medium" if s >= 3 else "low"
        out.append(
            {
                "title": g["title"],
                "link": g["link"],
                "source": g["source"],
                "summary": g["summary"],
                "published": g["date"].isoformat(),
                "score": s,
                "impact": level,
                "sources": n_sources,
                "others": [{"source": o["source"], "link": o["link"]} for o in g["others"]],
                **cls,
                "outlook": outlook(g["title"], cls["assets"], cls["markets"]),
            }
        )
    out.sort(key=lambda x: x["published"], reverse=True)
    return {"updated": now.isoformat(), "count": len(out[:MAX_ITEMS]), "feeds": status, "items": out[:MAX_ITEMS]}


def previous_calendar() -> dict | None:
    """The calendar feed is rate-limited; on failure reuse what the live site already serves."""
    base = os.environ.get("SITE_URL", "").rstrip("/")
    local_file = OUT / "calendar.json"
    try:
        if base:
            return json.loads(fetch(f"{base}/data/calendar.json"))
        if local_file.exists():
            return json.loads(local_file.read_text())
    except Exception:
        pass
    return None


def build_calendar(now: datetime) -> dict:
    # The calendar barely changes and its host rate-limits: refetch at most hourly.
    prev = previous_calendar()
    if prev and prev.get("events") and not prev.get("stale"):
        age = now - (parse_date(prev.get("updated")) or now - timedelta(days=1))
        if age < timedelta(hours=1):
            return prev
    try:
        data = json.loads(fetch(CALENDAR_URL))
    except Exception as e:
        if prev and prev.get("events"):
            prev["stale"] = True
            return prev
        return {"updated": now.isoformat(), "error": str(e)[:200], "events": []}
    events = []
    for e in data:
        imp = (e.get("impact") or "").lower()
        cur = e.get("country", "")
        # US data moves both crypto and stocks; elsewhere keep only the big ones
        if imp not in ("high", "medium") or (cur != "USD" and imp != "high"):
            continue
        d = parse_date(e.get("date"))
        if not d:
            continue
        events.append(
            {
                "title": e.get("title", ""),
                "country": cur,
                "date": d.isoformat(),
                "impact": imp,
                "forecast": e.get("forecast", ""),
                "previous": e.get("previous", ""),
            }
        )
    events.sort(key=lambda x: x["date"])
    return {"updated": now.isoformat(), "events": events}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    t0 = time.time()
    news = build_news(now)
    cal = build_calendar(now)
    (OUT / "news.json").write_text(json.dumps(news, ensure_ascii=False, separators=(",", ":")))
    (OUT / "calendar.json").write_text(json.dumps(cal, ensure_ascii=False, separators=(",", ":")))
    ok = sum(1 for v in news["feeds"].values() if v.startswith("ok"))
    high = sum(1 for i in news["items"] if i["impact"] == "high")
    print(f"{news['count']} stories ({high} high impact) from {ok}/{len(FEEDS)} feeds, "
          f"{len(cal['events'])} calendar events, {time.time() - t0:.1f}s")
    for name, st in news["feeds"].items():
        if not st.startswith("ok"):
            print(f"  ! {name}: {st}", file=sys.stderr)
    return 0 if ok >= len(FEEDS) // 2 else 1


if __name__ == "__main__":
    sys.exit(main())
