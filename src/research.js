export async function requestAssessment(url, fixtureCase) {
  const headers = { 'Content-Type': 'application/json' }
  if (fixtureCase) headers['X-Fixture-Case'] = fixtureCase
  const response = await fetch('/api/investigate', {
    method: 'POST',
    headers,
    body: JSON.stringify({ url }),
    signal: AbortSignal.timeout(180_000),
  })
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new Error('The research server is unavailable. Try again in a moment.')
  }
  const report = await response.json()
  if (!response.ok) throw new Error(report.error || 'The investigation could not finish.')
  return report
}
