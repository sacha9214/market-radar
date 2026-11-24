"""Claude-written market impact for each headline, replacing the keyword rules when enabled.

Two ways to run it:
- ANTHROPIC_API_KEY set: Anthropic API through the Python SDK (billed per token).
- CLAUDE_CODE_OAUTH_TOKEN set (from `claude setup-token`): the Claude Code CLI on the owner's
  Claude subscription, no API billing.
With neither, nothing runs. Each story is analysed once: results from the
previous run (read back from the live site) are reused by link, so a run only pays for the
stories that are new since the last one. Any failure leaves the rule-based outlook in place.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

MODEL = os.environ.get("AI_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("AI_EFFORT", "low")
# Stories below this impact keep the free rule-based outlook (keeps the bill small)
MIN_IMPACT = os.environ.get("AI_MIN_IMPACT", "medium")
BATCH = 20
MAX_NEW_PER_RUN = 80

TARGETS = ["crypto", "stocks", "gold", "oil", "usd"]

SYSTEM = """You are a markets desk analyst writing one-line impact notes for a retail investor dashboard \
that covers crypto and US stocks. For each news headline (with its short summary), say which markets it is \
likely to push and in which direction, and why, based on how markets usually react to this kind of news.

Targets: use "crypto", "stocks" (broad US equities), "gold", "oil", "usd" (the dollar), or the ticker of a \
specific stock or coin the story is about (e.g. "NVDA", "BTC", "COIN"). Direction d is 1 for up, -1 for down.

Be strict:
- Only give an arrow when there is a clear, standard mechanism (rates, inflation, growth, regulation, \
supply/demand, flows, earnings, security incidents, geopolitics). Company news moves that company's ticker, \
not the whole market, unless it is a market-wide driver (e.g. Nvidia for AI/tech).
- If the effect is unclear, mixed, or the story is minor, return an empty effects list. An empty list is a \
good answer; a guessed arrow is a bad one.
- moved = true when the headline mainly reports a price move that already happened ("Bitcoin rebounds 17%"), \
so acting on it now means buying or selling after the market.
- priced_in: "likely" when the news was widely expected or the move already happened, "maybe" when partly \
anticipated, "unlikely" when it is a genuine surprise.
- confidence: how sure the direction is ("low", "medium", "high").
- why_fr: one sentence in natural French, max 30 words, explaining the mechanism for a beginner. why_en: same \
in English. Describe the usual market reaction; never tell the reader to buy or sell.
- Return exactly one result per input id."""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "effects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"t": {"type": "string"}, "d": {"type": "integer", "enum": [-1, 1]}},
                            "required": ["t", "d"],
                            "additionalProperties": False,
                        },
                    },
                    "moved": {"type": "boolean"},
                    "priced_in": {"type": "string", "enum": ["likely", "maybe", "unlikely"]},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "why_fr": {"type": "string"},
                    "why_en": {"type": "string"},
                },
                "required": ["id", "effects", "moved", "priced_in", "confidence", "why_fr", "why_en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

RANK = {"low": 0, "medium": 1, "high": 2}


def user_message(batch: list[dict]) -> str:
    lines = [{"id": n, "headline": it["title"], "summary": it.get("summary", "")[:280], "source": it["source"],
              "published": it["published"]} for n, it in enumerate(batch)]
    return "Headlines:\n" + json.dumps(lines, ensure_ascii=False, indent=1)


def clean(res: dict) -> dict:
    """Normalise one model result into the outlook shape the site renders."""
    seen, effects = set(), []
    for e in res.get("effects", [])[:6]:
        t = str(e.get("t", "")).strip()
        t = t.lower() if t.lower() in TARGETS else t.upper()
        if t and t not in seen and e.get("d") in (1, -1):
            seen.add(t)
            effects.append({"t": t, "d": e["d"]})
    effects.sort(key=lambda e: (e["t"] not in ("crypto", "stocks"), e["t"]))
    return {
        "effects": effects,
        "why": [],
        "why_fr": res.get("why_fr", "")[:300],
        "why_en": res.get("why_en", "")[:300],
        "moved": bool(res.get("moved")),
        "priced_in": res.get("priced_in", "maybe"),
        "conf": res.get("confidence", "low"),
        "src": "ai",
    }


def via_cli(batch: list[dict]) -> dict | None:
    """One batch through `claude -p` on the subscription token, with schema-constrained output."""
    cmd = ["claude", "-p", "--model", MODEL, "--effort", EFFORT, "--output-format", "json",
           "--json-schema", json.dumps(SCHEMA), "--tools", "", "--no-session-persistence"]
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # an API key would take precedence
    try:
        run = subprocess.run(cmd, input=SYSTEM + "\n\n" + user_message(batch), capture_output=True, text=True,
                             timeout=300, env=env)
    except subprocess.TimeoutExpired:
        print("  ai: claude CLI timed out, keeping rules for this batch", file=sys.stderr)
        return None
    if run.returncode != 0:
        print(f"  ai: claude CLI exit {run.returncode}: {(run.stderr or run.stdout)[:300]}", file=sys.stderr)
        return None
    try:
        envelope = json.loads(run.stdout)
    except json.JSONDecodeError:
        return None
    data = envelope.get("structured_output")  # absent when the run ended without valid output
    if not isinstance(data, dict):
        print("  ai: no structured output from claude CLI, keeping rules for this batch", file=sys.stderr)
        return None
    print(f"  ai (subscription): {len(batch)} stories")
    return data


def analyse_batch(client, batch: list[dict]) -> dict[int, dict]:
    data = via_cli(batch) if client is None else via_api(client, batch)
    if not data:
        return {}
    return {r["id"]: clean(r) for r in data.get("items", []) if isinstance(r.get("id"), int) and 0 <= r["id"] < len(batch)}


def via_api(client, batch: list[dict]) -> dict | None:
    import anthropic

    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": user_message(batch)}],
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
            cache_control={"type": "ephemeral"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
        print(f"  ai: transient error, keeping rules for this batch: {e}", file=sys.stderr)
        return None
    except anthropic.APIStatusError as e:
        print(f"  ai: API error {e.status_code}, keeping rules: {e.message}", file=sys.stderr)
        return None

    if resp.stop_reason != "end_turn":
        print(f"  ai: stop_reason={resp.stop_reason}, keeping rules for this batch", file=sys.stderr)
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    u = resp.usage
    print(f"  ai (API): {len(batch)} stories, {u.input_tokens} in / {u.output_tokens} out tokens")
    return data


def enrich(items: list[dict], previous: dict[str, dict]) -> int:
    """Replace rule outlooks with Claude's where enabled. Returns how many new stories were analysed."""
    # Reuse earlier AI results for stories already analysed on a previous run
    for it in items:
        prev = previous.get(it["link"])
        if prev and prev.get("src") == "ai":
            it["outlook"] = prev

    client = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
        except ImportError:
            print("  ai: anthropic package missing, keeping rules", file=sys.stderr)
            return 0
        client = anthropic.Anthropic()
    elif not (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") and shutil.which("claude")):
        return 0

    todo = [it for it in items
            if it["outlook"].get("src") != "ai" and RANK[it["impact"]] >= RANK.get(MIN_IMPACT, 1)]
    todo = todo[:MAX_NEW_PER_RUN]  # newest first: a backlog drains over a few runs instead of one big bill
    if not todo:
        return 0
    done = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        for n, out in analyse_batch(client, batch).items():
            batch[n]["outlook"] = out
            done += 1
    return done
