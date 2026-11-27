import { InputError, investigateProduct } from './investigate.js';

function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(body));
}

async function readInput(req) {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of req) {
    bytes += chunk.length;
    if (bytes > 8192) throw new InputError('Request exceeds the URL input limit.');
    chunks.push(chunk);
  }
  let input;
  try {
    input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw new InputError('Send a JSON object containing the product URL.');
  }
  if (typeof input?.url !== 'string' || Object.keys(input).length !== 1 || input.url.length > 2048) {
    throw new InputError('Supply one product URL in the url field.');
  }
  return input.url;
}

export async function api(req, res) {
  if (req.url !== '/api/investigate') return json(res, 404, { error: 'Unknown API endpoint.' });
  if (req.method !== 'POST') return json(res, 405, { error: 'Use POST to investigate a URL.' });
  if (req.headers['content-type']?.split(';')[0] !== 'application/json') {
    return json(res, 415, { error: 'Send the URL as JSON.' });
  }
  try {
    const url = await readInput(req);
    const report = await investigateProduct(url, { fixtureCase: req.headers['x-fixture-case'] });
    return json(res, 200, report);
  } catch (err) {
    if (err instanceof InputError || err.code === 'UNSAFE_URL') return json(res, 400, { error: err.message });
    const error = process.env.OPENAI_API_KEY?.trim()
      ? 'Live research could not finish. Retry, or use fixture mode to explore a sample report.'
      : 'Live research needs a server-side API key. Choose fixture mode or configure the key and restart.';
    return json(res, 503, { error, score: null });
  }
}
