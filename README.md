# Market Radar

Live feed of the news that moves crypto and stock markets, ranked by likely impact, plus this week's economic calendar (CPI, PCE, jobs, FOMC…).

**Live:** https://sacha9214.github.io/market-radar/

## How it works

- `scripts/fetch_news.py` (standard library only) pulls ~19 public RSS feeds — CoinDesk, Cointelegraph, The Block, Decrypt, CNBC, MarketWatch, Investing.com, Seeking Alpha, BBC, plus official sources (Federal Reserve, SEC, ECB, White House).
- Each headline gets a keyword-based impact score (rate decisions, inflation data, regulation, tariffs, hacks, big % moves…). The same story reported by several outlets is grouped, and each extra outlet raises the score.
- `scripts/outlook.py` adds a likely-impact estimate per headline: which markets (crypto, stocks, gold, oil, dollar, or a named ticker) it usually pushes up or down, with the reasoning shown on the site. About 30 named rules (rate decisions, inflation, tariffs, conflicts, hacks, ETF flows, earnings…); when rules disagree, no arrow is shown. Headlines that only report a price move that already happened are flagged "already moved". Checked by `scripts/test_outlook.py` on every run.
- Optional AI analysis (`scripts/ai_outlook.py`): when the repository has an `ANTHROPIC_API_KEY` secret, Claude writes the impact note for each new medium/high story instead of the rules (direction, a one-line explanation in French and English, whether it is likely priced in, confidence). Each story is analysed once; earlier results are reused from the live site. Repository variables `AI_MODEL` (default `claude-opus-5-5`) and `AI_MIN_IMPACT` (`medium`, or `high` / `low`) tune cost. Any API error falls back to the rules.
- The economic calendar comes from the Forex Factory weekly feed (US high/medium impact events, other countries high only).
- A GitHub Action runs every ~10 minutes, rebuilds `site/data/*.json` and deploys to GitHub Pages. No commits, no server.
- The page polls for new data every minute and can send a browser notification when a new high-impact story appears (while the tab is open).

## Limits

- News arrives 10–30 minutes after publication (RSS lag + GitHub's scheduled-run delays). Professional desks get it in milliseconds. This is for not being caught off guard, not for beating the market.
- The impact score and the up/down arrows are keyword heuristics and will misjudge some headlines. Expected news is often already priced in, and markets sometimes do the opposite.
- GitHub disables scheduled workflows after 60 days without repository activity; re-enable it in the Actions tab if updates stop.
- Not investment advice.

## Run locally

```bash
python3 scripts/fetch_news.py
python3 -m http.server 8000 --directory site
```
