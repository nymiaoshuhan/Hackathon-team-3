import assert from 'node:assert/strict';
import test from 'node:test';
import { assess } from '../server/assessment.js';
import { fixtureResearch } from '../server/fixtures.js';

const url = 'https://orbit-fixture.example/';
const fixture = scenario => fixtureResearch(url, scenario);

test('confirmed checks award 40, 30, 20, and 10 points from traceable passages', () => {
  const result = assess(url, fixture('credible'));
  assert.equal(result.verdict, 'green');
  assert.equal(result.score, 100);
  assert.deepEqual(result.checks.map(check => check.points), [40, 30, 20, 10]);
  assert.ok(result.checks.every(check => check.evidenceIds.every(id => result.sources.some(source => source.id === id))));
});

test('an authoritative contradiction overrides positive points', () => {
  const research = fixture('contradiction');
  const positive = fixture('credible');
  research.documents.push(positive.documents[2]);
  research.checks.push(positive.checks[3]);
  const result = assess(url, research);
  assert.equal(result.verdict, 'red');
  assert.equal(result.score, 10);
});

test('incomplete retrieval stays yellow even with positive findings', () => {
  const partial = assess(url, fixture('timeout'));
  assert.equal(partial.verdict, 'yellow');
  assert.equal(partial.score, 0);
  const research = fixture('credible');
  research.incomplete = true;
  assert.equal(assess(url, research).verdict, 'yellow');
});

test('complete retrieval failure leaves the score and verdict unset', () => {
  const result = assess(url, { documents: [], checks: [], incomplete: true, limitations: ['Network timeout.'] });
  assert.equal(result.score, null);
  assert.equal(result.verdict, null);
});

test('fabricated source IDs and unmatched quotes are rejected', () => {
  const result = assess(url, fixture('fabricated'));
  assert.equal(result.verdict, 'yellow');
  assert.equal(result.score, 40);
  assert.deepEqual(result.sources.map(source => source.id), ['S1']);
  assert.deepEqual(result.checks.slice(1).map(check => check.evidence), [[], [], []]);
  assert.ok(result.limitations.some(item => item.includes('citation')));
});

test('vendor-authored external posts and vendor subdomains cannot corroborate independently', () => {
  const externalPost = fixture('credible');
  externalPost.checks[1].evidence[0].vendorAuthored = true;
  assert.equal(assess(url, externalPost).verdict, 'yellow');
  const related = fixture('credible');
  related.documents[1].url = 'https://partners.orbit-fixture.example/case-study';
  assert.equal(assess(url, related).checks[1].status, 'unverified');
});

test('matches the actual domain and rejects partial hostname matches', () => {
  for (const wrongHost of ['fakeorbit-fixture.example', 'orbit-fixture.example.attacker.com', 'other.orbit-fixture.example']) {
    const research = fixture('credible');
    const text = research.documents[1].text.replace('orbit-fixture.example', wrongHost);
    research.documents[1].text = text;
    research.checks[1].evidence[0].quote = text;
    assert.equal(assess(url, research).checks[1].status, 'unverified', wrongHost);
  }
});

test('a self-declared or ambiguous contradiction cannot trigger red', () => {
  const research = fixture('contradiction');
  research.checks[0].evidence[0].relation = 'vendor';
  assert.equal(assess(url, research).verdict, 'yellow');
  const ambiguous = fixture('contradiction');
  const quote = 'The domain orbit-fixture.example has received a correction request.';
  ambiguous.documents[1].text = quote;
  ambiguous.checks[0].evidence[0].quote = quote;
  assert.equal(assess(url, ambiguous).verdict, 'yellow');
});
