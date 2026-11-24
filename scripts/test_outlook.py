"""Headline -> expected arrow. Run: python scripts/test_outlook.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from outlook import outlook  # noqa: E402

CASES = [
    ("SEC approves spot Solana ETF", ["SOL"], ["crypto"], "SOL+"),
    ("California court terminates lawsuit against Coinbase over TerraUSD purchases", ["COIN"], ["crypto"], "COIN+"),
    ("Market rout kills 50 basis points December Fed rate hike bets", [], ["crypto", "stocks"], "crypto+"),
    ("Fed's John Williams indicates higher interest rates likely 'over time'", [], ["crypto", "stocks"], "crypto-"),
    ("US CPI rises more than expected in October", [], ["crypto", "stocks"], "crypto-"),
    ("Inflation cools to 2.4%, below forecasts", [], ["crypto", "stocks"], "crypto+"),
    ("Fed cuts rates by 25 basis points", [], ["crypto", "stocks"], "crypto+"),
    ("Trump imposes new 25% tariffs on Chinese goods", [], ["crypto", "stocks"], "stocks-"),
    ("Trump pauses tariffs for 90 days", [], ["crypto", "stocks"], "stocks+"),
    ("Nvidia beats estimates, raises guidance", ["NVDA"], ["stocks"], "NVDA+"),
    ("Apple misses revenue expectations", ["AAPL"], ["stocks"], "AAPL-"),
    ("Bitcoin ETFs see $1B inflows", ["BTC"], ["crypto"], "BTC+"),
    ("Bitcoin ETFs shed $1.8B in third-largest weekly outflow", ["BTC"], ["crypto"], "BTC-"),
    ("Exchange hacked for $40M in ether", ["ETH"], ["crypto"], "ETH-"),
    ("Israel and Iran agree to ceasefire", [], ["crypto", "stocks"], "oil-"),
    ("Iran says three tankers hit mines in Hormuz", [], ["crypto", "stocks"], "oil+"),
    ("Strategy buys 457 BTC", ["BTC"], ["crypto"], "BTC+"),
    ("Tether loses peg briefly", ["USDT"], ["crypto"], "crypto-"),
    ("SEC sues Binance", ["BNB"], ["crypto"], "BNB-"),
    ("U.S. adds Megaspeed to trade blacklist amid Nvidia controversy", ["NVDA"], ["stocks"], "NVDA-"),
]
CASES_ABSENT = [
    ("U.S. adds Megaspeed to trade blacklist amid Nvidia controversy", ["NVDA"], ["stocks", "crypto"], "stocks-"),
    ("Bitcoin and tech stocks rally as Nvidia reinstates Jensen Huang as CEO", ["BTC", "NVDA"], ["crypto", "stocks"], "BTC+"),
]

NO_ARROW = [
    ("Strive Buys No Bitcoin Last Week, Holdings Stay at 43,404 BTC", ["BTC"], ["crypto"]),
    ("Why 42 Macro says it's waiting to buy the Bitcoin dip", ["BTC"], ["crypto"]),
    ("Poundland is facing collapse - what's gone wrong?", [], ["stocks"]),
    ("Next data accessed in cyber breach", [], ["stocks"]),
]
MOVED = [("Bitcoin rebounds 17% from $55K lows", ["BTC"], ["crypto"], True),
         ("Cross River Bank launches first bitcoin-backed loans, offering up to $250,000", ["BTC"], ["crypto"], False)]


def arrows(o):
    return {f"{e['t']}{'+' if e['d'] > 0 else '-'}" for e in o["effects"]}


fails = [t for t, a, m, exp in CASES if exp not in arrows(outlook(t, a, m))]
fails += [t for t, a, m, bad in CASES_ABSENT if bad in arrows(outlook(t, a, m))]
fails += [t for t, a, m in NO_ARROW if outlook(t, a, m)["effects"]]
fails += [t for t, a, m, mv in MOVED if outlook(t, a, m)["moved"] != mv]
for f in fails:
    print("FAIL:", f, arrows(outlook(f, [], ["crypto", "stocks"])))
total = len(CASES) + len(CASES_ABSENT) + len(NO_ARROW) + len(MOVED)
print(f"{total - len(fails)}/{total} passed")
sys.exit(1 if fails else 0)
