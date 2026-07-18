import { useEffect, useState } from 'react'

export const MOBILE_VIEWPORT_QUERY = '(max-width: 900px)'

export function readMobileViewport(media: Pick<MediaQueryList, 'matches'>): boolean {
  return media.matches
}

function currentMatch(): boolean {
  return typeof window !== 'undefined' && readMobileViewport(window.matchMedia(MOBILE_VIEWPORT_QUERY))
}

export function useMobileViewport(): boolean {
  const [mobile, setMobile] = useState(currentMatch)

  useEffect(() => {
    const media = window.matchMedia(MOBILE_VIEWPORT_QUERY)
    const update = () => setMobile(readMobileViewport(media))
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])

  return mobile
}
