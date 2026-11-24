# Market Radar

Live feed of the news that moves crypto and stock markets, ranked by likely impact, plus this week's economic calendar (CPI, PCE, jobs, FOMC…).

**Live:** https://sacha9214.github.io/market-radar/

## How it works

- `scripts/fetch_news.py` (standard library only) pulls ~19 public RSS feeds — CoinDesk, Cointelegraph, The Block, Decrypt, CNBC, MarketWatch, Investing.com, Seeking Alpha, BBC, plus official sources (Federal Reserve, SEC, ECB, White House).
- Each headline gets a keyword-based impact score (rate decisions, inflation data, regulation, tariffs, hacks, big % moves…). The same story reported by several outlets is grouped, and each extra outlet raises the score.
- The economic calendar comes from the Forex Factory weekly feed (US high/medium impact events, other countries high only).
- A GitHub Action runs every ~10 minutes, rebuilds `site/data/*.json` and deploys to GitHub Pages. No commits, no server.
- The page polls for new data every minute and can send a browser notification when a new high-impact story appears (while the tab is open).

## Limits

- News arrives 10–30 minutes after publication (RSS lag + GitHub's scheduled-run delays). Professional desks get it in milliseconds. This is for not being caught off guard, not for beating the market.
- The impact score is a keyword heuristic and will misjudge some headlines.
- GitHub disables scheduled workflows after 60 days without repository activity; re-enable it in the Actions tab if updates stop.
- Not investment advice.

## Run locally

```bash
python3 scripts/fetch_news.py
python3 -m http.server 8000 --directory site
```
