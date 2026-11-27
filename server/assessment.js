import { getDomain } from 'tldts';

const criteria = [
  { id: 'identity', label: 'Product and domain identity', maxPoints: 40 },
  { id: 'independent', label: 'Independent corroboration', maxPoints: 30 },
  { id: 'operator', label: 'Operator transparency', maxPoints: 20 },
  { id: 'substance', label: 'Product documentation', maxPoints: 10 },
];

const independentRoles = new Set(['partner', 'customer', 'registry', 'authority']);
const clean = value => typeof value === 'string' ? value.replace(/\s+/gu, ' ').trim() : '';

function hostOf(value) {
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return '';
    return url.hostname.toLowerCase().replace(/\.$/, '');
  } catch {
    return '';
  }
}

function site(host) {
  return getDomain(host, { allowPrivateDomains: true }) || host;
}

function namesHost(text, host) {
  const escaped = host.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // A suffix or lookalike of the submitted hostname cannot establish identity.
  return new RegExp('(?:^|[^\\p{L}\\p{N}_.@-])' + escaped +
    '(?=$|[^\\p{L}\\p{N}_.@-]|\\.(?=\\s|$))', 'iu').test(text);
}

function tiesToHost(doc, quote, host, productName) {
  if (namesHost(quote, host)) return true;
  // A named product in the quoted passage and an exact-host link in its
  // source provide a verifiable association when anchor text hides the URL.
  return productName.length >= 2 && quote.toLowerCase().includes(productName.toLowerCase()) &&
    (doc.links ?? []).some(link => hostOf(link) === host);
}

function supports(proposal, item, doc, context) {
  const sourceHost = hostOf(doc.url);
  const quote = clean(item.quote);
  if (quote.length < 12 || quote.length > 1200 || !clean(doc.text).includes(quote)) return false;
  const separate = site(sourceHost) !== site(context.host);
  const independent = separate && doc.origin === 'web_search' && item.vendorAuthored === false &&
    independentRoles.has(item.relation);
  const tied = tiesToHost(doc, quote, context.host, context.productName);

  if (proposal.status === 'contradicted') {
    return independent && tied;
  }
  if (proposal.id === 'independent') return independent && tied;
  if (proposal.id === 'identity') return sourceHost === context.host || tied;
  return !separate || tied;
}

function documentedContradiction(item, doc, host) {
  if (!['authority', 'registry'].includes(item.relation) || !namesHost(item.quote, host)) return false;
  // Reserve an overriding verdict for explicit documentary language. Other
  // supported disagreements stay visible as mixed evidence.
  return doc.origin === 'web_search' &&
    /\b(impersonat(?:es?|ing|ion)|not (?:affiliated|associated|operated|owned|authorized)|unauthori[sz]ed (?:copy|domain)|placeholder|reserved (?:domain|for)|(?:documentation|illustrative) examples?)\b/i.test(item.quote);
}

/** Accept documents only from the trusted collector. Proposals never add sources. */
export function assess(inputUrl, raw) {
  const inputHost = hostOf(inputUrl);
  const productName = clean(raw.productName).slice(0, 180);
  const context = { host: inputHost, productName };
  const documents = new Map((raw.documents ?? []).filter(doc =>
    doc.id && hostOf(doc.url) && ['submitted', 'web_search'].includes(doc.origin) &&
    clean(doc.text)).map(doc => [doc.id, doc]));
  const limitations = new Set((raw.limitations ?? []).map(clean).filter(Boolean));
  const used = new Map();
  let material = false;
  const checks = criteria.map(criterion => {
    const proposal = (raw.checks ?? []).find(entry => entry.id === criterion.id);
    const evidence = [];
    for (const item of proposal?.evidence ?? []) {
      const doc = documents.get(item.sourceId);
      if (!doc || !supports(proposal, item, doc, context)) {
        limitations.add('A proposed citation could not be validated for the ' + criterion.label.toLowerCase() + ' check.');
        continue;
      }
      evidence.push({ sourceId: doc.id, quote: clean(item.quote) });
      used.set(doc.id, { id: doc.id, url: doc.url, title: clean(doc.title) || hostOf(doc.url) });
      if (proposal.id === 'identity' && proposal.status === 'contradicted' &&
          proposal.material === true && documentedContradiction(item, doc, inputHost)) material = true;
    }
    const status = evidence.length && ['confirmed', 'contradicted'].includes(proposal?.status)
      ? proposal.status : 'unverified';
    return { ...criterion, status, points: status === 'confirmed' ? criterion.maxPoints : 0,
      summary: status === 'unverified' ? 'Available evidence did not establish this check.' : clean(proposal.summary),
      evidenceIds: [...new Set(evidence.map(item => item.sourceId))], evidence };
  });

  const failed = raw.failed === true || !documents.size;
  const score = failed ? null : checks.reduce((total, check) => total + check.points, 0);
  const [identity, independent] = checks;
  const disagreement = checks.some(check => check.status === 'contradicted');
  let verdict;
  let interpretation;
  if (failed) {
    verdict = null;
    interpretation = 'The investigation failed before usable evidence was collected. Retry the URL to obtain an assessment.';
  } else if (material) {
    verdict = 'red';
    interpretation = identity.summary + ' Review the cited authority’s statement before relying on this domain.';
  } else if (!raw.incomplete && !disagreement && identity.points && independent.points && score >= 70) {
    verdict = 'green';
    interpretation = independent.summary + ' Review the cited records and product security documentation before adoption. This evidence score does not constitute an endorsement or security audit.';
  } else {
    verdict = 'yellow';
    const missing = checks.filter(check => check.status !== 'confirmed').map(check => check.label.toLowerCase());
    const reason = disagreement ? 'The sources contain conflicting evidence.' :
      raw.incomplete ? 'Retrieval was incomplete.' : 'The available sources leave gaps.';
    interpretation = reason + (missing.length ? ' Verify ' + missing.join(', ') + ' before drawing a conclusion.' :
      ' Retry to complete the outstanding research.');
  }
  return { inputUrl, productName: productName || inputHost, verdict, score, interpretation, checks,
    sources: [...used.values()], limitations: [...limitations] };
}
