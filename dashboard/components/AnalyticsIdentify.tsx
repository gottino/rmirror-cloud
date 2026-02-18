'use client'

import { useAuth } from '@clerk/nextjs'
import { useEffect } from 'react'
import { identifyUser } from '@/lib/analytics'

export function AnalyticsIdentify() {
  const { userId, isSignedIn } = useAuth()

  useEffect(() => {
    if (isSignedIn && userId) {
      identifyUser(userId)
    }
  }, [isSignedIn, userId])

  return null
}
