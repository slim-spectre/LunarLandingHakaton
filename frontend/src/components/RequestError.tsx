import type { ApiClientError } from '../api/errors'

export function RequestError({ error }: { error: ApiClientError }) {
  const explanation: Record<string, string> = {
    TERRAIN_UNAVAILABLE:
      'Terrain observations are unavailable. Stage 1 supports geometric observations only.',
    JOB_EXPIRED: 'This job has expired. Submit a new observation.',
    JOB_NOT_FOUND: 'This job could not be found. Submit a new observation.',
    JOB_NOT_READY:
      'The result is not ready. Submit again to start a new observation.',
  }
  return (
    <div className="request-error" role="alert">
      <strong>{error.code}</strong>
      <p>{explanation[error.code] ?? error.message}</p>
      {error.details.map((detail, i) => (
        <p key={i}>
          {detail.field}: {detail.reason}
        </p>
      ))}
      {error.requestId && <small>Request ID: {error.requestId}</small>}
    </div>
  )
}
