# SaaSLens

Enter one public SaaS product URL. SaaSLens checks the product and its claimed operator against independent sources, then shows a cited verdict, an evidence score, and what still needs verification. The [sample dataset](hackathon_40_solutions_commented%20%281%29.csv) is for later testing.

## Run locally

Use Node.js 22.12 or later. Run `npm ci` and `npm run dev`, then open [SaaSLens](http://127.0.0.1:4173). **Fixture mode** exercises the full interface with synthetic evidence and requires no credentials.

For **Live research**, set `OPENAI_API_KEY` in the server environment or the ignored `.env.local` file and restart. Set `OPENAI_MODEL` to select a model supporting hosted web search and structured output. The default is `gpt-4.1`.

## How the verdict works

The Node API accepts `POST /api/investigate` with `{"url":"https://product.example/"}`. One OpenAI Agents SDK researcher uses hosted web search. The server checks DNS and redirects, bounds page retrieval, and matches quoted evidence against retrieved text.

| Confirmed finding | Points |
| --- | ---: |
| Product identity at the exact submitted domain | 40 |
| Independent corroboration linking that product and domain | 30 |
| Identifiable operator with public legal or contact information | 20 |
| Concrete product documentation or changelog | 10 |

**Green** requires both identity checks, at least 70 points, completed retrieval, and no verified contradiction. **Red** takes priority when an authoritative source establishes a material contradiction. **Yellow** covers gaps, mixed findings, and partial retrieval. A failed investigation has no score. Points measure evidence coverage. Security and safety require a separate assessment.

## Tests

Run `npm test` for scoring, citation, fetch, and API tests. Run `npm run build` followed by `npm run test:ui` for the four fixture scenarios and retry flow in a browser. Playwright uses Edge on Windows when available, or Chromium installed with `npx playwright install chromium`.

With a configured key, `node --env-file-if-exists=.env.local tests/live-smoke.js` runs billable live investigations of Sentry and example.com. Their results depend on the evidence accessible at run time.
