export function describeActionableRequestFailure({
  requestUrl,
  errorText,
  firstPartyOrigins,
}) {
  const origin = new URL(requestUrl).origin
  if (!firstPartyOrigins.has(origin) || errorText === 'net::ERR_ABORTED') return null
  return `request failed: ${requestUrl} (${errorText})`
}
