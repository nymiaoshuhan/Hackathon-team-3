# Team comparison — November 27, 2026

The locked pipeline (`6297199`) and the updated pipeline (`f5549f7`) each matched **27/40 (67.5%)**, with **zero Red → Green and zero Green → Red errors**. We kept the updated version for its hardware support, coverage fallbacks, and partial verdicts on timeout.

Development variants scored **52.5–75.0%**, including **30/40 (75.0%)** immediately before voting and excerpt verification. Always guessing Yellow scores **16/40 (40%)**. With only 40 rows, a rough sampling margin is about **±15 percentage points** near these scores. Similar products produce correlated errors, and the rubric was learned from the same 40 rows. Excluding the matching few-shot example does not make this a held-out benchmark; expect this evaluation to be optimistic.

## Locked pipeline

| Expected ↓ / predicted → | Green | Yellow | Red |
| --- | ---: | ---: | ---: |
| Green | 7 | 7 | 0 |
| Yellow | 2 | 14 | 0 |
| Red | 0 | 4 | 6 |

**Highest-cost errors:** zero Red → Green and zero Green → Red. Four labeled Reds went to manual review instead of being blocked; seven labeled Greens also went to review. The verifier can turn a majority verdict into Yellow if no fully supported flag of that color survives.

| CSV rows | Expected → predicted | Vendors/products |
| --- | --- | --- |
| 1, 6, 8, 13, 23, 26, 33 | Green → Yellow | Omnissa, Postfix, Datto, COGPACK, Gainsight, ManageEngine, opsi |
| 9, 31 | Yellow → Green | Autodesk Fusion, Schneespur |
| 4, 11, 21, 35 | Red → Yellow | PimEyes, Knooing, Tipard PDF to Word Converter, Prayer Platform |

## Updated pipeline

| Expected ↓ / predicted → | Green | Yellow | Red |
| --- | ---: | ---: | ---: |
| Green | 6 | 8 | 0 |
| Yellow | 1 | 15 | 0 |
| Red | 0 | 4 | 6 |

Only two predictions changed. Autodesk Fusion (row 9, labeled Yellow) moved from Green to Yellow, correcting a miss. IrfanView (row 39, labeled Green) moved from Green to Yellow, adding a miss. All ten labeled Red rows kept the same verdict.

## Judge-only Nebius comparison

For the model comparison, capture each row's evidence once with screenshots off, then swap only the judge and verifier model. The capture reused **375 Tavily responses and spent 0 new credits**. It rejected uncached Tavily requests rather than buying new results. This controls the evidence within the comparison, not against the earlier 67.5% result: live sources, collection coverage, and cached responses can differ across runs. Use the judge-only baseline in the table, not 67.5%, to compare models.

| Model | Accuracy | LLM / rules rows | Wall, median, p95 | Reported input / output tokens | Estimated cost |
| --- | ---: | ---: | --- | --- | ---: |
| `openai/gpt-oss-120b` | 22/40 (55.0%) | 40 / 0 | 31.64 s, 5.69 s, 7.28 s | 1,130,416 / 101,425 | $0.23 |
| `deepseek-ai/DeepSeek-V4.1-Flash-1017-fast` | 25/40 (62.5%) | 29 / 11 | 92.57 s, 16.31 s, 25.89 s | 1,090,597 / 390,461 | $1.59 |
| `zai-org/GLM-5.3` | 20/40 (50.0%) | 13 / 27 | 243.02 s, 41.80 s, 62.97 s | 1,112,576 / 432,863 | $3.46 |

Each matrix below lists the predicted Green / Yellow / Red counts for each expected color. None of these runs had a Red → Green or Green → Red error.

| Model | Expected Green | Expected Yellow | Expected Red |
| --- | --- | --- | --- |
| GPT-OSS | 3 / 11 / 0 | 2 / 14 / 0 | 0 / 5 / 5 |
| DeepSeek Flash Fast | 3 / 11 / 0 | 0 / 16 / 0 | 0 / 4 / 6 |
| GLM-5.3 | 0 / 14 / 0 | 0 / 15 / 1 | 0 / 5 / 5 |

These are judge timings for 40 rows with eight workers, excluding evidence collection, not full blind-batch timings. Cost estimates apply [Nebius list prices](https://tokenfactory.nebius.com/model-catalog.md) to reported usage before provider-side cache discounts; failed requests may not return usage. The Flash variant did not recover any additional Greens, needed a rules fallback on 11 rows, and cost more. GLM needed the rules fallback on 27 rows, even though its one-call probe had responded fastest. Neither result justifies switching the live default. In the GPT-OSS audit, seven of the eleven missed Greens were voted Yellow before verification. Four had Green majorities but no fully supported Green claim survived. Both initial judgment and evidence verification contribute to the Yellow bias.

Two code experiments also did not justify a live change. Appending localized and generic keywords directly to existing risk queries, together with a material-quote exception in verification, scored **25/40** (44 new Tavily credits) and introduced one Red → Green error. The affected row had three Green votes, so a verifier exception that only applies to Red votes could not have caused that verdict. Retaining the original enforcement query, moving localized terms to a separate query within the same budget, and adding guidance for maintained, established products removed the Red → Green error, but scored **24/40** (4 new Tavily credits, no Red ↔ Green errors); Red recall fell from **6/10 to 3/10** versus the updated pipeline. These were bundled experiments, not per-feature ablations, and are not in the live branch.

## Five unseen submission rows

| Product | Verdict | Worker seconds |
| --- | --- | ---: |
| Notion | Green | 6.64 |
| SQLite | Green | 5.67 |
| Bruno | Yellow | 6.98 |
| LastPass | Yellow | 7.34 |
| FreePDFConvert | Yellow | 5.10 |

All five domains were outside the labeled CSV. The batch finished in **7.48 s** with a warm search cache, no crashed or timed-out rows, and matching CSV and JSON verdicts. This tests batch behavior, not prediction accuracy; no independent blind labels were collected. All 11 distinct final citations returned HTTP 200 in the spot-check. Three supporting excerpts were not found verbatim in the fetched HTML (SQLite's YouTube citation, one Bruno excerpt, and the LastPass blog post); those links are not fully substantiated by this check. In particular, the SQLite professional-support claim still needs a direct source. A 200 response and an excerpt-based pass are not proof that a human can verify each claim on the page.

## Cost and reproduction

- **Locked, 40 rows:** 0 new Tavily credits (375 cache hits); 120 new Nebius requests (40 cached), 761,124 input and 76,824 output tokens, approximately **$0.16** at list pricing.
- **Updated, 40 rows:** 9 new Tavily credits (366 cache hits); 44 new Nebius requests (116 cached), 306,148 input and 27,647 output tokens, approximately **$0.063**. A 150-uncached-search guard made no substitutions and skipped no searches. The measured cost reflects a shared warm cache, not cheaper cold judging. A fully cold run uses up to 400 basic Tavily searches and up to 160 Nebius requests.
- **Five rows:** 0 new Tavily credits (47 cache hits); 15 new Nebius requests (five cached), 94,148 input and 9,011 output tokens, approximately **$0.02**. The initial pre-lock dry run used 47 Tavily credits.

From `agent/`, with Tavily and Nebius keys configured, and `CACHE_DIR` pointing to the persistent cache (the comparison used `/home/ubuntu/repos/hackathon/cache`):

```bash
python -m unittest discover -v
CHROME_CDP_URL=http://localhost:29229 python eval.py --workers 8 --no-screenshot --cache-dir "$CACHE_DIR" --out "$CACHE_DIR/eval-results-lock.json"
CHROME_CDP_URL=http://localhost:29229 /usr/bin/time -f 'Wall clock: %e s' python agent.py --blind --input examples/dry_run_urls.txt --out examples/dry_run_verdicts.csv --audit-out examples/dry_run_verdicts.json --workers 5 --cache-dir "$CACHE_DIR"
```

To reproduce the updated 40-row run, use commit `f5549f7` with the same evaluation command and `--out "$CACHE_DIR/eval-results-tip.json"`. The capped launcher used for this measurement was external to the CLI; the command above does not enforce a credit cap. The CDP setting can be omitted when using a local Playwright Chromium install. The locked dry-run outputs are checked in under [examples/](examples/).
