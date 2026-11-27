import { assess } from './assessment.js';
import { fixtureResearch, fixtureScenarios } from './fixtures.js';
import { validatePublicUrl } from './fetch.js';

export class InputError extends Error {}

export async function investigateProduct(url, { fixtureCase } = {}) {
  let inputUrl;
  try {
    inputUrl = validatePublicUrl(url).href;
  } catch {
    throw new InputError('Enter a public HTTP or HTTPS product URL without credentials.');
  }
  if (fixtureCase !== undefined) {
    if (!fixtureScenarios.includes(fixtureCase)) {
      throw new InputError('Choose one of the listed fixture scenarios.');
    }
    return assess(inputUrl, fixtureResearch(inputUrl, fixtureCase));
  }
  if (!process.env.OPENAI_API_KEY?.trim()) {
    throw new Error('Live research needs a server-side API key. You can use fixture mode now.');
  }
  const { research } = await import('./live.js');
  return assess(inputUrl, await research(inputUrl));
}
