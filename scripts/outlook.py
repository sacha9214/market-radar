"""Guess which markets a headline is likely to push, and in which direction.

Rule-based on purpose: every arrow traces back to a named rule whose reasoning is
shown on the site (texts live in site/app.js under `why`). When rules disagree the
arrow is dropped rather than guessed. Headlines that only report a price move that
already happened are flagged `moved`, since acting on them means buying after everyone else.
"""
from __future__ import annotations

import re

# Market groups shown on the site. Single tickers (BTC, NVDA…) come from the asset tagger.
CRYPTO, STOCKS, GOLD, OIL, USD = "crypto", "stocks", "gold", "oil", "usd"

RISK_OFF = {CRYPTO: -1, STOCKS: -1, GOLD: +1, USD: +1}
RISK_ON = {CRYPTO: +1, STOCKS: +1}
HAWKISH = {CRYPTO: -1, STOCKS: -1, GOLD: -1, USD: +1}
DOVISH = {CRYPTO: +1, STOCKS: +1, GOLD: +1, USD: -1}

N = r"[\s-]+(?:\S+[\s-]+){0,4}?"  # a gap of up to 4 filler words between two parts of a rule
N6 = r"[\s-]+(?:\S+[\s-]+){0,7}?"

# (id, pattern on lower-cased title, group effects, effect on the assets named in the title)
RULES: list[tuple[str, str, dict[str, int], int]] = [
    # --- central banks (dovish checked first: "kills rate hike bets" is dovish) ---
    ("dovish", r"(kill|dash|fade|pare|slash|scrap|ease|end)\w*" + N6 + r"(rate[\s-])?hike (bets|odds|expectations)|hike bets" + N + r"(fade|ease|vanish|collapse)"
               r"|rate cuts?\b|cuts? (interest )?rates|dovish|lower (interest )?rates|pause[sd]? (rate )?hikes|quantitative easing|\bqe\b|stimulus|injects? liquidity", DOVISH, 0),
    ("hawkish", r"higher (interest )?rates|rate hikes?\b|hikes? (interest )?rates|raises? (interest )?rates|hawkish|higher for longer|fewer (rate )?cuts"
                r"|(rate[\s-])?cut (bets|hopes)" + N + r"(fade|dim|dashed|slashed)|no (rate )?cuts?\b|quantitative tightening", HAWKISH, 0),
    # --- inflation & jobs ---
    ("inflation_hot", r"(inflation|\bcpi\b|\bpce\b|consumer prices|price index)" + N + r"(rise|rises|rose|jump|jumps|accelerat|hott?er|heats? up|surge|climb|beats?|above)"
                      r"|hotter[\s-]than[\s-]expected|sticky inflation|inflation (fears|worries)", HAWKISH, 0),
    ("inflation_cool", r"(inflation|\bcpi\b|\bpce\b|consumer prices)" + N + r"(cool|eases?|slow|fall|falls|fell|drop|below|soft)|cooler[\s-]than[\s-]expected|disinflation", DOVISH, 0),
    ("jobs_weak", r"(unemployment|jobless)" + N + r"(rise|rises|rose|jump|climb|highest)|(payrolls|jobs report|hiring)" + N + r"(miss|slow|weak|disappoint|shrink)|job losses",
                  {STOCKS: -1, GOLD: +1, USD: -1}, 0),
    ("jobs_strong", r"(payrolls|jobs report|hiring)" + N + r"(beat|surge|jump|strong|blowout|tops)|unemployment" + N + r"(fall|falls|fell|drops|lowest)",
                    {USD: +1, CRYPTO: -1}, 0),
    ("recession", r"recession (fears?|risk|warning|looms?)|economy (shrinks|contracts)|gdp (shrinks|contracts|falls)|hard landing", {STOCKS: -1, CRYPTO: -1, GOLD: +1, OIL: -1}, 0),
    # --- geopolitics & trade ---
    ("deescalation", r"ceasefire|truce|peace (deal|talks|agreement)|de-?escalat", {STOCKS: +1, CRYPTO: +1, OIL: -1, GOLD: -1}, 0),
    ("conflict", r"\bwar\b|invasion|invades|missiles?|airstrikes?|strikes on|attacks? on|military (action|escalation)|hit mines|escalat", {**RISK_OFF, OIL: +1}, 0),
    ("tariff_relief", r"tariffs?" + N + r"(pause|paused|cut|lift|lifted|exempt|delay|eased|truce|deal|rollback)|(pause|lift|delay|cut)s?" + N + r"tariffs?|trade (deal|truce)", RISK_ON, 0),
    ("tariff_up", r"(new|impose|imposes|raise|raises|hike|threatens?|slap|slaps)\w*" + N + r"tariffs?|tariffs?" + N + r"(hike|increase|threat|takes? effect)|trade war", {STOCKS: -1, CRYPTO: -1, USD: +1}, -1),
    ("blacklist", r"blacklist|export (ban|controls?)|entity list", {}, -1),
    ("oil_supply", r"\bopec\b" + N + r"(cut|cuts|curb)|hormuz|tankers?|oil (supply|output) (cut|disrupt)|sanctions? on (russian|iranian) oil|pipeline (attack|shut)", {OIL: +1, STOCKS: -1}, 0),
    ("oil_glut", r"\bopec\b" + N + r"(boost|raise|increase|hike)s? (output|production)|oil glut", {OIL: -1}, 0),
    ("shutdown", r"government shutdown|debt ceiling|default on", {STOCKS: -1, GOLD: +1, CRYPTO: -1}, 0),
    # --- crypto ---
    ("hack", r"hack(ed|s)?\b|exploit|drained|stolen|breach|heist|laundering|mixers?", {}, -1),
    ("depeg", r"depeg|loses? (its )?peg|insolven|bankrupt|chapter 11|halts? withdrawals|bank run|collapse", {}, -1),
    ("etf_positive", r"etf" + N + r"(approv|launch|debut|green[\s-]?light|inflows?)|(approv|launch)\w*" + N + r"etf|inflows?", {}, +1),
    ("etf_negative", r"etf" + N + r"(reject|delay|denied|outflows?)|(reject|delay|den)\w*" + N + r"etf|outflows?", {}, -1),
    ("btc_buyer", r"strategic (bitcoin |crypto )?reserve|(buys?|adds?|bought|acquires?)" + N + r"(btc|bitcoin|eth|ether)\b|treasury (company|firm)" + N + r"(buys?|adds?)",
                  {CRYPTO: +1}, +1),
    ("seller", r"(sells?|sold|dumps?|unloads?|moves?)" + N + r"(btc|bitcoin|eth|ether|tokens?|coins?)\b" + N + r"(to|on)? ?(exchanges?|coinbase|binance|kraken)?|mt\.? ?gox|token unlocks?|repayments?",
               {}, -1),
    ("reg_positive", r"(sec|cftc|court|judge|regulators?)" + N + r"(drop|drops|dismiss|terminat|toss|throws? out|ends?|close[sd]?|approv|green[\s-]?light|allows?|can count)"
                     r"|(bill|act|law)" + N + r"(pass|passes|passed|signed|advances)|regulatory clarity|legal framework|license (granted|approved)|wins? (lawsuit|case)",
                     {CRYPTO: +1}, +1),
    ("reg_negative", r"(sec|cftc|doj|regulators?|prosecutors?)" + N + r"(sue|sues|charge|charges|charged|probe|investigat|crack ?down|fine[sd]?)"
                     r"|\bbans?\b|banned|indict|lawsuit (against|filed)|subpoena|delist", {}, -1),
    # --- companies ---
    ("earnings_beat", r"(beats?|tops?|exceeds?|crushes?)" + N + r"(estimates|expectations|forecasts)|record (revenue|profit|earnings|sales)|raises? (guidance|forecast|outlook)|strong (results|earnings|quarter)",
                      {}, +1),
    ("earnings_miss", r"miss(es|ed)?" + N + r"(estimates|expectations|forecasts)|(cuts?|lowers?|slashes?) (guidance|forecast|outlook)|profit warning|weak (results|earnings|quarter|guidance)",
                      {}, -1),
    ("upgrade", r"upgrade[sd]?\b|raises? price target|price target (raised|hike)", {}, +1),
    ("downgrade", r"downgrade[sd]?\b|cuts? price target|lowers? price target", {}, -1),
    ("buyback", r"buyback|share repurchase|stock split|special dividend", {}, +1),
    ("ceo_exit", r"(ceo|boss|chief executive|founder)" + N + r"(quits|resigns|steps down|ousted|fired|departs)", {}, -1),
    ("ceo_return", r"(returns|reinstate[sd]?)" + N + r"(as )?(ceo|chief executive)", {}, +1),
    ("antitrust", r"antitrust|probe|investigation into|fined|recall", {}, -1),
    ("deal", r"(to acquire|acquires|takeover bid|buyout|merger talks|in talks to (buy|merge))", {}, +1),
]

MOVE = re.compile(
    r"\b(rall(y|ies|ied)|soar(s|ed)?|surge[sd]?|jump(s|ed)?|climb(s|ed)?|rebound(s|ed)?|spike[sd]?|gain(s|ed)?|ris(es|e|ing)|rose|"
    r"plunge[sd]?|tumble[sd]?|slump(s|ed)?|sink(s)?|sank|fall(s)?|fell|drop(s|ped)?|slide[sd]?|crash(es|ed)?|dip(s|ped)?|sell-?off|rout|"
    r"higher|lower|up \d|down \d)\b"
)
MOVE_SUBJECT = re.compile(
    r"bitcoin|\bbtc\b|ether|\beth\b|crypto|solana|\bxrp\b|stocks?|shares|s&p|nasdaq|dow|futures|markets?|index|nikkei|kospi|"
    r"\bgold\b|\boil\b|dollar|yields?|price|nvidia|tesla|apple|microsoft|amazon"
)
PRICE_TALK = re.compile(r"\d+(\.\d+)?\s?%|\$\d|record high|all-time high|two-year low|lows?\b|highs?\b|liquidations?")

NEGATED_BUY = re.compile(r"buys? no\b|no (new )?(bitcoin|btc)|didn'?t buy|pauses? (bitcoin |btc )?(buying|purchases)")
OPINION = re.compile(r"^(why|how|what|here'?s|here’s|is |are |can |could |should |will )|\?\s*$|\b(says it'?s waiting|predicts?|could hit)\b")

CRYPTO_TICKERS = {"BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "USDT", "USDC"}
GROUP_OF = {"S&P 500": STOCKS, "NASDAQ": STOCKS, "DOW": STOCKS, "GOLD": GOLD, "OIL": OIL, "USD": USD}

# Company news moves that company's stock, not a coin that happens to be in the same headline
COMPANY_RULES = {"earnings_beat", "earnings_miss", "upgrade", "downgrade", "buyback", "ceo_exit", "ceo_return", "antitrust", "deal", "blacklist"}

COMPILED = [(rid, re.compile(p), eff, own) for rid, p, eff, own in RULES]


def outlook(title: str, assets: list[str], markets: list[str]) -> dict:
    t = title.lower()
    if OPINION.search(t):  # explainers and opinions carry no new information
        return {"effects": [], "why": [], "moved": False, "mixed": False, "conf": "low"}
    fired: list[str] = []
    score: dict[str, int] = {}

    def add(target: str, d: int) -> None:
        score[target] = score.get(target, 0) + d

    for rid, pat, eff, own in COMPILED:
        if not pat.search(t):
            continue
        # a dovish match already explains "hike"/"cut" wording; don't let hawkish re-fire on it
        if rid == "hawkish" and "dovish" in fired:
            continue
        if rid == "etf_negative" and "etf_positive" in fired:
            continue
        if rid == "reg_negative" and "reg_positive" in fired:
            continue
        if rid == "btc_buyer" and NEGATED_BUY.search(t):
            continue
        fired.append(rid)
        for g, d in eff.items():
            add(g, d)
        if own:
            named = [a for a in assets if a not in ("USDT", "USDC")]
            if rid in COMPANY_RULES:
                named = [a for a in named if a not in CRYPTO_TICKERS and a not in GROUP_OF]
                if not named:
                    continue
            for a in named:
                add(GROUP_OF.get(a, a), own)
            # No ticker named: a crypto hack/ban/outflow weighs on crypto as a whole, but one
            # unnamed company's news does not move the stock market, so no arrow there.
            if not named and CRYPTO in markets:
                add(CRYPTO, own)

    effects = [{"t": k, "d": 1 if v > 0 else -1} for k, v in score.items() if v != 0]
    # crypto tickers already carry the signal; keep the group arrow too only if it was set by a rule
    effects.sort(key=lambda e: (e["t"] not in (CRYPTO, STOCKS), e["t"]))

    moved = bool(MOVE.search(t) and MOVE_SUBJECT.search(t) and PRICE_TALK.search(t))
    mixed = any(v == 0 for v in score.values()) and not effects
    conf = "medium" if len(fired) >= 2 and effects else "low"
    return {"effects": effects[:6], "why": fired[:3], "moved": moved, "mixed": mixed, "conf": conf}
