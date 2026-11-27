import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { once } from 'node:events';
import http from 'node:http';
import { api } from '../server/api.js';

const server = http.createServer(api);
let endpoint;
before(async () => {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  endpoint = `http://127.0.0.1:${server.address().port}/api/investigate`;
});
after(() => server.close());

function post(input, scenario) {
  const headers = { 'Content-Type': 'application/json' };
  if (scenario) headers['X-Fixture-Case'] = scenario;
  return fetch(endpoint, { method: 'POST', headers, body: JSON.stringify(input) });
}

test('API accepts exactly one public URL and rejects invalid input before research', async () => {
  for (const input of [{}, { url: 'file:///private' }, { url: 'https://127.0.0.1' },
    { url: 'https://me:secret@site.example/' }, { url: 'https://site.example', vendor: 'unexpected' }]) {
    assert.equal((await post(input, 'credible')).status, 400);
  }
  assert.equal((await post({ url: 'https://site.example' }, 'unknown')).status, 400);
});

test('fixture findings pass through the same API without live services', async () => {
  const url = 'https://product.example/';
  for (const [scenario, verdict] of Object.entries({
    credible: 'green', contradiction: 'red', timeout: 'yellow', fabricated: 'yellow',
  })) {
    const response = await post({ url }, scenario);
    assert.equal(response.status, 200);
    const report = await response.json();
    assert.equal(report.inputUrl, url);
    assert.equal(report.verdict, verdict);
    assert.equal(report.checks.length, 4);
    assert.ok(report.limitations.some(message => message.includes('synthetic')));
  }
});
