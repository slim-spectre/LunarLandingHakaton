import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import { ApiClientError } from '../../api/errors'
import type { CSAResources as Resources } from '../../api/types'
import { SourceLink } from '../../components/SourceLink'
import { RequestError } from '../../components/RequestError'

export function CSAResources() {
  const [data, setData] = useState<Resources | null>(null)
  const [error, setError] = useState<ApiClientError | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    apiClient
      .getResources({ signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setData(value)
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof ApiClientError
              ? reason
              : new ApiClientError({
                  message: 'Unable to load CSA resources.',
                }),
          )
      })
    return () => controller.abort()
  }, [attempt])
  return (
    <section className="workspace-card" aria-labelledby="csa-heading">
      <div className="card-heading">
        <h2 id="csa-heading">CSA resources</h2>
        <button
          type="button"
          className="secondary-button"
          onClick={() => {
            setData(null)
            setError(null)
            setAttempt((value) => value + 1)
          }}
        >
          Refresh resources
        </button>
      </div>
      <p className="muted">
        Moon, Artemis, Gateway and Canadarm3 news from the official CSA feed.
      </p>
      {!data && !error && <p role="status">Loading CSA resources…</p>}
      {error && <RequestError error={error} />}
      {data && (
        <>
          <p className="resource-meta">
            <span className={`data-badge ${data.data_status}`}>
              {data.data_status}
            </span>{' '}
            Retrieved{' '}
            <time dateTime={data.fetched_at}>{data.fetched_at} (UTC)</time>
          </p>
          {data.data_status === 'stale' && (
            <p className="notice">
              The source is unavailable. Showing previously retrieved resources.
            </p>
          )}
          {data.items.length === 0 && (
            <p>No matching articles in the available feed.</p>
          )}
          <ul className="resource-list">
            {data.items.map((item) => (
              <li key={item.id}>
                <h3>
                  <SourceLink url={item.url}>{item.title}</SourceLink>
                </h3>
                {item.published_at && (
                  <time className="muted" dateTime={item.published_at}>
                    {new Date(item.published_at)
                      .toISOString()
                      .replace('T', ' ')
                      .replace('.000Z', ' UTC')}
                  </time>
                )}
                <p>{item.summary}</p>
                <small className="muted">{item.topics.join(' · ')}</small>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
