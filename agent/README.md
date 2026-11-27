# Vendor Verdict — Agents with Taste

An evidence-first procurement agent for Stackgini's hackathon challenge. Given a product URL, it returns **Green** (proceed with ordinary checks), **Yellow** (verify before buying), or **Red** (stop and escalate). This is a buying triage tool, not a security audit or a public vendor rating.

## Run

```bash
cd agent
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium

python agent.py https://stackgini.de/ --evidence
python agent.py --input urls.txt --out verdicts.csv
python agent.py --input urls.txt --out verdicts.json --evidence
```

`urls.txt` contains one URL per line; blank lines and lines beginning with `#` are ignored. Add `--no-screenshot` for faster runs; sparse pages can still trigger browser fallback. Use `CHROME_CDP_URL=http://localhost:29229` instead of installing Chromium if you've already got a local Chrome DevTools endpoint. Screenshots and fetches are cached in `cache/` for 24 hours; `--cache-dir` selects another cache. `--workers` controls batch concurrency.

Keys are optional. Export them or put them in a local, ignored `.env` file:

| Variable | Purpose |
| --- | --- |
| `TAVILY_API_KEY` | Adds independent web search. Without it, coverage is mostly first-party pages and domain history. |
| `LLM_API_KEY` | Enables the model judge. Without it, the conservative deterministic judge runs. |
| `LLM_PROVIDER` | Optional explicit override: `openai`, `anthropic`, or `nebius`. Otherwise inferred from the key prefix. |
| `LLM_MODEL` | Defaults: `gpt-4o-mini`, `claude-haiku-4-5`, or `openai/gpt-oss-120b`, respectively. |
| `LLM_BASE_URL` | Optional provider endpoint override; Nebius defaults to `https://api.tokenfactory.nebius.com/v1`. |
| `LLM_VISION` | Set to `1` and select a vision-capable model to include the homepage screenshot in the model call. |

## What the agent checks

1. **Vendor pages** — starts with the exact product and homepage, then follows a small sample of relevant links. Extracts corporate and compliance statements, traction counts, logo alt text, lifecycle language, release dates, and linked-page errors. The browser captures a screenshot and fills in JS-heavy pages when needed.
2. **Domain history** — consults RDAP registration events and Wayback captures; dates belong to the domain/capture, not necessarily to the company. Looks for historical traction text in the available snapshot.
3. **External research** — nine parallel Tavily basic-search topics cover enforcement, incidents, ownership, exact product naming, lifecycle, customers, traction, jurisdictions, and procurement transitions. When a repository surfaces, GitHub provides metadata and the default branch's latest commit. One optional extra search samples named customer logos; a deployment is only corroborated when a fetched customer-owned page describes actual use. Partners, badges, and search snippets don't count; an inconclusive result isn't evidence the claim is false.
4. **Judge** — the evidence list has numbered items. The model selects IDs, and the agent resolves those IDs to exact collector URLs. Invalid citations are removed; unsupported high-level calls fall back to local rules. This validates the links' provenance, not whether every model paraphrase is entailed. Review claims and links before relying on them. JSON records coverage limitations and the judge mode, and optionally the collected evidence; CSV is the compact submission view.

Collectors share a bounded HTTP cache and pace requests by host. Website fetches respect robots rules and disallow direct private-network URLs; this CLI is not a sandbox, and should not be exposed as a service that browses arbitrary untrusted input. Network errors, robots denials, missing archive coverage, and empty searches are not negative vendor findings. No agents contact vendors or run active security probes.

## Evaluate

```bash
python -m unittest discover -v
python eval.py --workers 8 --no-screenshot --out eval-results.json
```

Evaluation defaults to the labeled event CSV at the repository root; use `--labels` to override the path. The pipeline does not copy the CSV or reviewer notes into `agent/` or send them to the model. It passes only the URL for research, excludes any matching anonymized few-shot pattern, then prints accuracy, judge-mode coverage, a three-way confusion matrix, and per-row disagreements. Keep evaluation files within the event. The scoreboard is a development aid; the live challenge uses previously unseen products.

### API budget

On a cold cache the 40-row evaluation uses at most **400 Tavily credits** (nine base searches and up to one customer check per vendor at [one credit per basic search](https://docs.tavily.com/documentation/api-credits)), 5% of the team's 8,000-credit budget. You don't need to run it repeatedly: use one labeled baseline, one evaluation after meaningful changes, and a small unseen smoke test. An unchanged rerun within 24 hours reuses successful search responses. CLI and evaluation log estimated Tavily credits, cache hits and failed calls; the Tavily dashboard is authoritative for billing.

The default [Nebius gpt-oss-120b](https://nebius.com/models/openai/gpt-oss-120b) public endpoint lists $0.15 per million input tokens and $0.60 per million output tokens. At 7,000 input and 2,000 output tokens per vendor, a cold 40-row evaluation is about **$0.09**; actual token counts are logged. Identical model requests reuse the disk cache, while a model, rubric, or evidence change triggers fresh judging. Other models and vision pricing vary.

## What the examples teach

The sample includes **40** products: **14 Green** (35%), **16 Yellow** (40%), and **10 Red** (25%). Screenshots help explain what the buyer sees, but unattractive and well-maintained tools coexist with polished sites making misleading claims. Product/version identity matters: related products on the same vendor domain can have different licensing, support and risk.

Stackgini sells an AI operating system for IT demand management; its site presents named case studies with measurable outcomes. An agent worth demonstrating would distinguish those vendor-published claims from confirmation on the customer's own site or a partner marketplace.

Next high-value checks: compare traction counts across pages and archive dates; independently match a named customer's product and timeframe; verify certifying body, scope and expiry; resolve legal entities through an official register; and compare an incident's date and product scope against remediation status. For the live demo, show two contrasting cases: dated but actively shipped software, and a polished site whose most important claim is contradicted by an authoritative source.
