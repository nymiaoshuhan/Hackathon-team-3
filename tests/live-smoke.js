// Explicit opt-in only. Each URL runs a real, billable investigation.
import http from 'node:http';
import { once } from 'node:events';
import { api } from '../server/api.js';

const server = http.createServer(api).listen(0, '127.0.0.1');
await once(server, 'listening');
try {
  await Promise.all(['https://sentry.io/', 'https://example.com/'].map(async url => {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/api/investigate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
    });
    const result = await response.json();
    console.log(JSON.stringify({ url, status: response.status, verdict: result.verdict, score: result.score,
      sources: result.sources?.map(source => source.url), limitations: result.limitations, error: result.error }));
    if (!response.ok || !result.verdict) process.exitCode = 1;
  }));
} finally {
  server.close();
}
