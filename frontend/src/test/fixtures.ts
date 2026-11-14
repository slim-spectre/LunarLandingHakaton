/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type {
  CSAResources,
  Job,
  JobAccepted,
  NowRequest,
  NowResult,
  SiteList,
} from '../api/types'

// Test-only synthetic examples; these are not measured scientific results.
function example<T>(name: string): T {
  return JSON.parse(
    readFileSync(
      resolve(
        dirname(fileURLToPath(import.meta.url)),
        '../../../contracts/examples',
        `${name}.json`,
      ),
      'utf8',
    ),
  ) as T
}
export const accepted = example<JobAccepted>('job-accepted-now')
export const observationResult = example<NowResult>('observation-result')
export const queued: Job = { ...example<Job>('job-queued'), kind: 'now' }
export const running: Job = { ...example<Job>('job-running'), kind: 'now' }
export const failed: Job = { ...example<Job>('job-failed'), kind: 'now' }
export const succeeded: Job = {
  ...running,
  status: 'succeeded',
  finished_at: '2027-07-15T00:00:02Z',
}
export const request: NowRequest = {
  site: { latitude: -89.44, longitude: 222.1 },
  target_time: '2027-07-15T00:00:00Z',
  horizon_mode: 'geometric',
  observer_height_m: 2,
  visibility_margin_deg: 0,
}
export const catalog: SiteList = {
  items: [
    {
      id: 'development-site',
      name: 'Synthetic catalog site',
      category: 'artemis',
      latitude: -89.44,
      longitude: -137.9,
      description: 'Development catalog fixture.',
      source_url: 'https://example.org/site-fixture',
      quickmap_url: 'https://example.org/quickmap-fixture',
      terrain_region_id: null,
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
}
export const resources: CSAResources = {
  items: [],
  fetched_at: '2027-07-15T00:00:00Z',
  data_status: 'fresh',
}
export const resourceItem = {
  id: 'synthetic-news',
  title: 'Synthetic Moon news',
  summary: 'Test-only summary.',
  url: 'https://example.org/news-fixture',
  published_at: '2027-07-14T12:00:00Z',
  topics: ['Moon'],
}

export function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
