import { getDomain } from 'tldts';

const criteria = [
  { id: 'identity', label: 'Product and domain identity', maxPoints: 40 },
  { id: 'independent', label: 'Independent corroboration', maxPoints: 30 },
  { id: 'operator', label: 'Operator transparency', maxPoints: 20 },
  { id: 'substance', label: 'Product documentation', maxPoints: 10 },
];

const independentRoles = new Set(['partner', 'customer', 'registry', 'authority']);
const confirmedSummaries = {
  identity: 'The source identifies the product at the submitted domain.',
  independent: 'A separate publisher connects the product to the submitted domain.',
  operator: 'The source provides public information about the operator.',
  substance: 'The source documents how the product works or records a specific change.',
};
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

function escapeRegex(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function namesHost(text, host) {
  const escaped = escapeRegex(host);
  // A suffix or lookalike of the submitted hostname cannot establish identity.
  return new RegExp('(?:^|[^\\p{L}\\p{N}_.@-])' + escaped +
    '(?=$|[^\\p{L}\\p{N}_.@-]|\\.(?=\\s|$))', 'iu').test(text);
}

function tiesToHost(doc, quote, host, productName) {
  if (namesHost(quote, host)) return true;
  // Plain page-wide link inventories cannot bind a quotation to a domain.
  const name = productName.toLowerCase();
  return name.length >= 2 && quote.toLowerCase().includes(name) &&
    (doc.linkContexts ?? []).some(link => hostOf(link.url) === host &&
      clean(link.text).toLowerCase().includes(name) &&
      (clean(link.text).includes(quote) || quote.includes(clean(link.text))));
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
  if (proposal.id === 'independent') {
    const original = context.identitySources;
    const distinctPublisher = !original.length || original.some(first =>
      site(hostOf(first.url)) !== site(sourceHost));
    const copied = original.some(first => clean(first.text).includes(quote)) ||
      context.vendorDocs.some(first => clean(first.text).includes(quote));
    return independent && tied && distinctPublisher && !copied;
  }
  if (proposal.id === 'identity') return sourceHost === context.host || tied;
  return !separate || tied;
}

function documentedContradiction(item, doc, host) {
  if (!['authority', 'registry'].includes(item.relation) || !namesHost(item.quote, host)) return false;
  // Check both the excerpt and the containing sentence. A quote can be exact
  // while omitting "it is false that" from the beginning of the sentence.
  const hostPattern = '(?<![\\p{L}\\p{N}_@.-])' + escapeRegex(host);
  const reserved = ' (?:is|are) (?:a placeholder(?: domain)?|(?:reserved|maintained|designated) (?:solely |exclusively )?for (?:use in )?(?:documentation|examples?|illustrative purposes))';
  const impersonating = ' (?:impersonates|is impersonating|is an unauthori[sz]ed (?:copy|domain)|is not (?:affiliated with|operated by|owned by|authorized by))';
  const subjectList = '(?:,? (?:and|or) [a-z0-9.-]+)?';
  const assertion = new RegExp(hostPattern + '(?:' + subjectList + reserved + '|' + impersonating + ')\\b', 'iu');
  const uncertain = /\b(if|unless|whether|could|might|maybe|may|would|hypothetical|suppose|false|falsely|incorrect|incorrectly|rumou?r|alleg(?:e[ds]?|ation)|den(?:y|ies|ied)|disput(?:e[sd]?|ing)|unconfirmed|unverified|no evidence|no indication|not true|no longer|was once)\b|\?/iu;
  const quote = clean(item.quote);
  if (!assertion.test(quote)) return false;
  const sentences = new Intl.Segmenter('en', { granularity: 'sentence' }).segment(clean(doc.text));
  for (const { segment } of sentences) {
    if (!assertion.test(segment) || !(segment.includes(quote) || quote.includes(segment.trim()))) continue;
    if (uncertain.test(segment) || uncertain.test(quote)) continue;
    return true;
  }
  return false;
}

/** Accept documents only from the trusted collector. Proposals never add sources. */
export function assess(inputUrl, raw) {
  const inputHost = hostOf(inputUrl);
  const productName = clean(raw.productName).slice(0, 180);
  const documents = new Map((raw.documents ?? []).filter(doc =>
    doc.id && hostOf(doc.url) && ['submitted', 'web_search'].includes(doc.origin) &&
    clean(doc.text)).map(doc => [doc.id, doc]));
  const limitations = new Set((raw.limitations ?? []).map(clean).filter(Boolean));
  const used = new Map();
  const context = { host: inputHost, productName, identitySources: [],
    vendorDocs: [...documents.values()].filter(doc => site(hostOf(doc.url)) === site(inputHost)) };
  let materialQuote = '';
  const checks = criteria.map(criterion => {
    const proposal = (raw.checks ?? []).find(entry => entry.id === criterion.id);
    const evidence = [];
    for (const item of proposal?.evidence ?? []) {
      const doc = documents.get(item.sourceId);
      if (!doc || !supports(proposal, item, doc, context)) {
        limitations.add('A proposed citation could not be validated for the ' + criterion.label.toLowerCase() + ' check.');
        continue;
      }
      const quote = clean(item.quote);
      if (evidence.some(entry => entry.sourceId === doc.id && entry.quote === quote)) continue;
      evidence.push({ sourceId: doc.id, quote });
      if (criterion.id === 'identity' && proposal.status === 'confirmed') context.identitySources.push(doc);
      used.set(doc.id, { id: doc.id, url: doc.url, title: clean(doc.title) || hostOf(doc.url) });
      if (proposal.id === 'identity' && proposal.status === 'contradicted' &&
          proposal.material === true && documentedContradiction(item, doc, inputHost)) materialQuote = quote;
    }
    const status = evidence.length && ['confirmed', 'contradicted'].includes(proposal?.status)
      ? proposal.status : 'unverified';
    const summary = status === 'confirmed' ? confirmedSummaries[criterion.id] :
      status === 'contradicted' ? 'The cited source conflicts with the claim under review.' :
      'Available evidence did not establish this check.';
    return { ...criterion, status, points: status === 'confirmed' ? criterion.maxPoints : 0, summary,
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
  } else if (materialQuote) {
    verdict = 'red';
    interpretation = 'The cited authority reports “' + materialQuote + '” Review that statement before relying on this domain.';
  } else if (!raw.incomplete && !disagreement && identity.points && independent.points && score >= 70) {
    verdict = 'green';
    interpretation = 'Independent evidence connects this product to ' + inputHost + '. The source states “' +
      independent.evidence[0].quote + '” Review the cited records and product security documentation before adoption. This evidence score does not constitute an endorsement or security audit.';
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
