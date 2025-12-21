import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

const isPublicRoute = createRouteMatcher(['/sign-in(.*)', '/sign-up(.*)'])

// Skip Clerk in local development if it can't connect
const isDevelopment = process.env.NODE_ENV === 'development'

export default clerkMiddleware(async (auth, request) => {
  // In development, allow bypassing Clerk if connection fails
  if (isDevelopment) {
    try {
      if (!isPublicRoute(request)) {
        await auth.protect()
      }
    } catch (error) {
      console.warn('Clerk auth failed in development, allowing request:', error)
      // Allow the request to continue in dev mode even if Clerk fails
      return NextResponse.next()
    }
  } else {
    // In production, enforce authentication
    if (!isPublicRoute(request)) {
      await auth.protect()
    }
  }
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
}
