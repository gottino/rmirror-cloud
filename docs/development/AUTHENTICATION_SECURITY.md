# Authentication & Security Guide

## Overview

rMirror Cloud uses **Clerk** for OAuth-based authentication in production, with a secure local development mode that maintains production security while enabling efficient local development.

## Authentication Architecture

### Production Authentication

**Provider:** Clerk OAuth
**Endpoints:** All API endpoints require authentication
**Token Type:** JWT (JSON Web Tokens)
**Token Validation:** Clerk SDK with signature verification

**Flow:**
```
User → Dashboard → Clerk OAuth → Backend API (JWT verification) → Resources
```

**Security Features:**
- Industry-standard OAuth 2.0 flow
- JWT tokens with cryptographic signatures
- Automatic token refresh
- Secure session management
- No passwords stored in backend

### Local Development Mode

**Purpose:** Enable local development without network-dependent Clerk authentication
**Activation:** Only when `DEBUG=true` in backend `.env`
**Safety:** Production remains fully secure - dev mode is DEBUG-gated

**Configuration:**

**Backend (.env):**
```bash
DEBUG=true  # Enables dev-mode-bypass token
```

**Dashboard (.env.local):**
```bash
NEXT_PUBLIC_DEV_MODE=true  # Enables development authentication
```

**Important:** These settings have **no effect** in production where `DEBUG` is always `false`.

---

## Authentication Implementation

### Backend: Clerk Authentication

**File:** `backend/app/auth/clerk.py`

```python
from clerk_backend_api import Clerk
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Initialize Clerk client
clerk = Clerk(bearer_auth=settings.clerk_secret_key)
security = HTTPBearer()

async def get_clerk_active_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
):
    """
    Verify Clerk JWT token and return authenticated user.

    In production: Full Clerk verification
    In development (DEBUG=true): Accept dev-mode-bypass token
    """
    token = credentials.credentials

    # Development mode bypass (DEBUG=true only)
    if settings.debug and token == "dev-mode-bypass":
        # Return development user
        return get_or_create_dev_user(db)

    # Production: Verify JWT with Clerk
    try:
        session = clerk.verify_token(token)
        user_id = session.get("sub")

        # Get or create user from Clerk ID
        user = get_or_create_user_from_clerk(db, user_id)
        return user

    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token"
        )
```

**Security Measures:**
1. ✅ Dev mode only works when `DEBUG=true`
2. ✅ Production always has `DEBUG=false`
3. ✅ Dev token is unique and not guessable in production
4. ✅ All production endpoints use full Clerk verification

---

### Dashboard: Clerk Integration

**File:** `dashboard/middleware.ts`

```typescript
import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

// Public routes (no authentication required)
const isPublicRoute = createRouteMatcher([
  '/',
  '/beta.html',
  '/sign-in(.*)',
  '/sign-up(.*)',
])

export default clerkMiddleware(async (auth, request) => {
  // Development mode: Skip Clerk for local development
  if (process.env.NEXT_PUBLIC_DEV_MODE === 'true') {
    return
  }

  // Production: Require authentication for protected routes
  if (!isPublicRoute(request)) {
    await auth.protect()
  }
})

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
}
```

**Development vs Production:**

| Feature | Development (DEBUG=true) | Production (DEBUG=false) |
|---------|-------------------------|--------------------------|
| Auth Provider | dev-mode-bypass token | Clerk OAuth |
| Token Validation | Skipped | Full JWT verification |
| User Creation | Auto dev user | Clerk user creation |
| Session Management | None | Clerk session handling |
| Security | Minimal (local only) | Full production security |

---

## Endpoints Requiring Authentication

### All Protected Endpoints

**Notebooks:**
- `GET /v1/notebooks/` - List user's notebooks
- `GET /v1/notebooks/uuid/{uuid}` - Get notebook by UUID
- `GET /v1/notebooks/{id}` - Get notebook by ID
- `GET /v1/notebooks/{id}/pages` - Get notebook pages
- `GET /v1/notebooks/{id}/content` - Get notebook content

**Processing:**
- `POST /v1/processing/rm-file` - Process .rm file (OCR)

**Sync:**
- `POST /v1/sync/content` - Upload .content file
- `POST /v1/sync/notebooks` - Sync notebook metadata

**Agent:**
- `POST /v1/agent/register` - Register agent
- `GET /v1/agent/status` - Get agent status

**Todos:**
- `GET /v1/todos/` - List todos
- `GET /v1/todos/{id}` - Get todo
- `PATCH /v1/todos/{id}` - Update todo
- `DELETE /v1/todos/{id}` - Delete todo

**Integrations:**
- All `/v1/integrations/*` endpoints

### Public Endpoints

These endpoints do **not** require authentication:

- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /v1/auth/webhooks/clerk` - Clerk webhooks (signature verified)

---

## Security Best Practices

### 1. Token Management

**Storage:**
- Never store tokens in localStorage (XSS vulnerable)
- Use httpOnly cookies when possible
- Clerk handles secure token storage automatically

**Transmission:**
- Always use HTTPS in production
- Include token in Authorization header: `Bearer YOUR_TOKEN`
- Never log tokens or include in URLs

**Expiration:**
- Tokens expire after configured period (default: 7 days)
- Clerk automatically refreshes tokens
- Handle 401 responses by redirecting to sign-in

### 2. Development Mode Safety

**Never deploy with DEBUG=true:**
```bash
# Production .env must have:
DEBUG=false
```

**Environment separation:**
```bash
# Local .env (development)
DEBUG=true
CLERK_SECRET_KEY=dev_key

# Production .env
DEBUG=false  # CRITICAL!
CLERK_SECRET_KEY=prod_key_with_real_secret
```

**Verification:**
```bash
# Check production environment
ssh production-server
cd /var/www/rmirror-cloud/backend
grep DEBUG .env
# Should output: DEBUG=false
```

### 3. Clerk Configuration

**Environment Variables:**

```bash
# Backend (.env)
CLERK_SECRET_KEY=sk_live_xxxxxxxxxxxx  # Production secret key
CLERK_WEBHOOK_SECRET=whsec_xxxxxxxxxx  # Webhook signature verification

# Dashboard (.env.local)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_xxxxxxxxxxxx
CLERK_SECRET_KEY=sk_live_xxxxxxxxxxxx
```

**Security Settings in Clerk Dashboard:**

1. **Session Duration:** Set to 7 days (168 hours)
2. **Allowed Redirect URLs:**
   - Production: `https://rmirror.io/*`
   - Development: `http://localhost:3000/*`
3. **Webhook URL:** `https://rmirror.io/v1/auth/webhooks/clerk`
4. **JWT Template:** Default settings (includes `sub`, `email`, etc.)

### 4. Webhook Security

**Signature Verification:**

```python
from svix.webhooks import Webhook

def verify_clerk_webhook(payload: bytes, headers: dict):
    """Verify Clerk webhook signature using Svix."""
    webhook = Webhook(settings.clerk_webhook_secret)

    try:
        webhook.verify(payload, headers)
        return True
    except Exception as e:
        logger.error(f"Webhook verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid signature")
```

**Why Svix?**
- Industry-standard webhook verification
- Prevents replay attacks
- Ensures webhook authenticity
- Clerk's official verification library

---

## Common Scenarios

### Scenario 1: Local Development

**Goal:** Develop frontend/backend locally without Clerk authentication overhead

**Setup:**

1. Backend `.env`:
   ```bash
   DEBUG=true
   ```

2. Dashboard `.env.local`:
   ```bash
   NEXT_PUBLIC_DEV_MODE=true
   ```

3. API calls use dev token:
   ```javascript
   const response = await fetch('/v1/notebooks/', {
     headers: {
       'Authorization': 'Bearer dev-mode-bypass'
     }
   })
   ```

**Result:** Backend accepts `dev-mode-bypass` token, creates/uses dev user automatically.

---

### Scenario 2: Production Deployment

**Goal:** Deploy with full Clerk authentication security

**Setup:**

1. Backend `.env`:
   ```bash
   DEBUG=false  # CRITICAL!
   CLERK_SECRET_KEY=sk_live_your_production_key
   ```

2. Dashboard `.env.production`:
   ```bash
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_your_key
   CLERK_SECRET_KEY=sk_live_your_production_key
   ```

3. Verify in deployment:
   ```bash
   curl https://rmirror.io/v1/notebooks/ \
     -H "Authorization: Bearer dev-mode-bypass"
   # Should return 401 Unauthorized
   ```

**Result:** Only valid Clerk JWT tokens are accepted. Dev tokens are rejected.

---

### Scenario 3: Agent Authentication

**Goal:** macOS agent authenticates with backend using Clerk OAuth

**Flow:**

1. Agent opens browser for Clerk OAuth
2. User signs in via Clerk
3. Clerk redirects back with authorization code
4. Agent exchanges code for access token
5. Agent uses token for all API requests

**Implementation:**

```python
# In macOS agent
class AuthManager:
    async def authenticate(self):
        """Authenticate via Clerk OAuth."""
        # Open browser to Clerk OAuth URL
        auth_url = f"{CLERK_FRONTEND_URL}/sign-in"
        webbrowser.open(auth_url)

        # Wait for callback with token
        token = await self.wait_for_oauth_callback()

        # Store token securely in keychain
        self.store_token_securely(token)

        return token
```

**Agent API Calls:**
```python
async def upload_page(self, page_file):
    """Upload page with authentication."""
    headers = {
        'Authorization': f'Bearer {self.get_token()}'
    }
    response = await self.client.post(
        f"{API_URL}/v1/processing/rm-file",
        files={'rm_file': page_file},
        headers=headers
    )
```

---

## Security Checklist

### Pre-Deployment

- [ ] `DEBUG=false` in production `.env`
- [ ] No `NEXT_PUBLIC_DEV_MODE` in production dashboard
- [ ] Real Clerk keys (not test keys) in production
- [ ] HTTPS enabled on all domains
- [ ] Webhook secret configured
- [ ] JWT token expiration set appropriately
- [ ] CORS origins configured correctly

### Post-Deployment

- [ ] Test authentication with real Clerk account
- [ ] Verify dev token is rejected: `curl -H "Authorization: Bearer dev-mode-bypass" https://api.rmirror.io/v1/notebooks/`
- [ ] Check webhook signature verification works
- [ ] Monitor failed authentication attempts
- [ ] Review Clerk dashboard for suspicious activity

### Regular Maintenance

- [ ] Rotate Clerk secret keys annually
- [ ] Review and remove inactive users
- [ ] Monitor token usage patterns
- [ ] Check for unauthorized API access
- [ ] Update Clerk SDK regularly

---

## Troubleshooting

### 401 Unauthorized in Development

**Problem:** Getting 401 errors even with dev-mode-bypass token

**Solutions:**

1. Check backend DEBUG setting:
   ```bash
   cd backend
   grep DEBUG .env
   # Should show: DEBUG=true
   ```

2. Verify token format:
   ```javascript
   // Correct
   Authorization: 'Bearer dev-mode-bypass'

   // Incorrect
   Authorization: 'dev-mode-bypass'  // Missing "Bearer"
   ```

3. Check backend logs:
   ```bash
   poetry run uvicorn app.main:app --reload
   # Look for authentication-related errors
   ```

---

### 401 Unauthorized in Production

**Problem:** Users getting 401 errors in production

**Possible Causes:**

1. **Expired tokens:**
   - Clerk tokens expire after configured duration
   - Frontend should handle refresh automatically
   - Check Clerk session settings

2. **Invalid Clerk configuration:**
   ```bash
   # Verify Clerk keys are set
   echo $CLERK_SECRET_KEY
   # Should output: sk_live_...
   ```

3. **CORS issues:**
   - Check CORS settings in backend
   - Verify allowed origins include your dashboard domain

4. **Webhook signature failures:**
   ```bash
   # Check webhook secret is set
   echo $CLERK_WEBHOOK_SECRET
   # Should output: whsec_...
   ```

**Debug Steps:**

```bash
# 1. Check backend logs
sudo journalctl -u rmirror.service -f | grep "401\|Unauthorized"

# 2. Test with Clerk test token
# Get token from Clerk Dashboard → Testing → Generate Token
curl https://rmirror.io/v1/notebooks/ \
  -H "Authorization: Bearer <clerk_test_token>"

# 3. Verify Clerk configuration
curl https://rmirror.io/v1/auth/status
# Should return current Clerk configuration (without secrets)
```

---

### Agent Can't Authenticate

**Problem:** macOS agent fails to authenticate with backend

**Solutions:**

1. **Check agent logs:**
   ```bash
   # macOS
   tail -f ~/Library/Logs/rmirror-agent/agent.log | grep auth
   ```

2. **Verify OAuth redirect URL:**
   - Clerk Dashboard → Settings → URLs
   - Should include: `http://localhost:5555/auth/callback`

3. **Test manual authentication:**
   ```bash
   # Open browser to sign-in page
   open "https://rmirror.io/sign-in"
   # Complete sign-in and copy token from browser dev tools
   ```

4. **Reset agent authentication:**
   ```bash
   # Delete stored credentials
   rm -rf ~/.rmirror-agent/credentials
   # Restart agent - will prompt for authentication
   ```

---

## Related Documentation

- [Clerk Setup Guide](CLERK_SETUP.md) - Detailed Clerk configuration
- [Backend README](README.md) - General backend documentation
- [CHANGELOG](../CHANGELOG.md) - Authentication-related changes

## References

- [Clerk Documentation](https://clerk.com/docs)
- [OAuth 2.0 Specification](https://oauth.net/2/)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)
- [Svix Webhook Verification](https://docs.svix.com/receiving/verifying-payloads/how)

## Support

For authentication issues:

1. Check this guide's Troubleshooting section
2. Review backend logs for authentication errors
3. Verify Clerk configuration in dashboard
4. Test with Clerk's test tokens
5. Open a GitHub issue with:
   - Error message and logs
   - Environment (dev/production)
   - Steps to reproduce
   - Clerk configuration (without secrets)
