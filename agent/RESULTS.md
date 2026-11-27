# Team comparison — November 27, 2026

The locked pipeline matched **27/40 (67.5%)**. Development variants scored **52.5–75.0%**, including **30/40 (75.0%)** immediately before voting and excerpt verification. Always guessing Yellow scores **16/40 (40%)**. With only 40 rows, a rough sampling margin is about **±15 percentage points** near these scores. Similar products produce correlated errors, and the rubric was learned from the same 40 rows. Excluding the matching few-shot example does not make this a held-out benchmark; expect this evaluation to be optimistic.

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

- **40 rows:** 0 new Tavily credits (375 cache hits); 120 new Nebius requests (40 cached), 761,124 input and 76,824 output tokens, approximately **$0.16** at list pricing. A fully cold run uses up to 400 basic Tavily searches and up to 160 Nebius requests; this run did not measure that cold cost.
- **Five rows:** 0 new Tavily credits (47 cache hits); 15 new Nebius requests (five cached), 94,148 input and 9,011 output tokens, approximately **$0.02**. The initial pre-lock dry run used 47 Tavily credits.

From `agent/`, with Tavily and Nebius keys configured, and `CACHE_DIR` pointing to the persistent cache (the comparison used `/home/ubuntu/repos/hackathon/cache`):

```bash
python -m unittest discover -v
CHROME_CDP_URL=http://localhost:29229 python eval.py --workers 8 --no-screenshot --cache-dir "$CACHE_DIR" --out "$CACHE_DIR/eval-results-lock.json"
CHROME_CDP_URL=http://localhost:29229 /usr/bin/time -f 'Wall clock: %e s' python agent.py --blind --input examples/dry_run_urls.txt --out examples/dry_run_verdicts.csv --audit-out examples/dry_run_verdicts.json --workers 5 --cache-dir "$CACHE_DIR"
```

The CDP setting can be omitted when using a local Playwright Chromium install. The two dry-run outputs are checked in under [examples/](examples/).
