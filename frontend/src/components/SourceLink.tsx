import type { ReactNode } from 'react'

export function SourceLink({
  url,
  children,
}: {
  url: string
  children: ReactNode
}) {
  let allowed = false
  try {
    const parsed = new URL(url)
    allowed = parsed.protocol === 'https:' || parsed.protocol === 'http:'
  } catch {
    /* Invalid provider links are displayed as text. */
  }
  return allowed ? (
    <a href={url} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ) : (
    <span>{children}</span>
  )
}
