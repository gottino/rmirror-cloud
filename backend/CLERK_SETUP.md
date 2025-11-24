# Clerk Authentication Setup Guide

This comprehensive guide walks you through setting up Clerk authentication for rMirror Cloud, enabling Google and Apple social logins.

## What is Clerk?

Clerk is a complete user management and authentication service that provides:
- Social logins (Google, Apple, GitHub, etc.)
- Email/password authentication
- Multi-factor authentication
- User management dashboard
- Webhooks for user lifecycle events
- JWT token validation

---

## Part 1: Google Cloud Console Setup

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top
3. Click "**New Project**"
4. Enter project name: **"rMirror Cloud"** (or similar)
5. Click "**Create**"
6. Wait for the project to be created, then select it

### Step 2: Enable Google+ API (if needed)

1. In the left sidebar, go to **APIs & Services** → **Library**
2. Search for "Google+ API"
3. Click on it and click "**Enable**" (might already be enabled)

### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Choose **External** (unless you have a Google Workspace organization)
3. Click "**Create**"

**Fill in the consent screen information:**

| Field | Value |
|-------|-------|
| **App name** | rMirror Cloud |
| **User support email** | your email |
| **App logo** | Upload your rMirror logo (optional) |
| **Application home page** | https://rmirror.io |
| **Application privacy policy** | https://rmirror.io/privacy (create later) |
| **Application terms of service** | https://rmirror.io/terms (create later) |
| **Authorized domains** | rmirror.io |
| **Developer contact** | your email |

4. Click "**Save and Continue**"

**Configure Scopes:**
5. Click "**Add or Remove Scopes**"
6. Select these scopes:
   - ✅ `userinfo.email`
   - ✅ `userinfo.profile`
   - ✅ `openid`
7. Click "**Update**" then "**Save and Continue**"

**Add Test Users (for testing before publishing):**
8. Click "**+ Add Users**"
9. Add your email and any beta testers' emails
10. Click "**Save and Continue**"
11. Review and click "**Back to Dashboard**"

### Step 4: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click "**+ Create Credentials**" at the top
3. Select "**OAuth client ID**"
4. Choose application type: **Web application**

**Configure the OAuth client:**

| Field | Value |
|-------|-------|
| **Name** | rMirror Cloud Web Client |
| **Authorized JavaScript origins** | (leave empty - Clerk handles this) |
| **Authorized redirect URIs** | *Add Clerk callback URL (see Step 5)* |

5. For now, click "**Create**" (we'll add the redirect URI after setting up Clerk)

6. **IMPORTANT: Save these credentials** (you'll need them for Clerk):
   - **Client ID**: `123456789-abc123.apps.googleusercontent.com`
   - **Client Secret**: `GOCSPX-abc123xyz...`
   - Click "**Download JSON**" or copy them to a safe place

---

## Part 2: Clerk Setup

### Step 1: Create Clerk Account & Application

1. Go to [clerk.com](https://clerk.com) and sign up
2. Click "**+ Create application**"
3. Enter application name: **"rMirror Cloud"**
4. Select any authentication methods you want enabled initially
5. Click "**Create application**"

### Step 2: Get Your Clerk Callback URL

1. In Clerk Dashboard, navigate to:
   - **User & Authentication** → **Social Connections**
2. Find "**Google**" in the list
3. Click on it to expand the settings
4. **Copy the redirect URI** shown there:
   - Format: `https://your-app-name.clerk.accounts.dev/v1/oauth_callback`
   - Or: `https://your-custom-domain.com/v1/oauth_callback` (if using custom domain)

### Step 3: Add Clerk Callback to Google Cloud Console

1. Go back to **Google Cloud Console** → **APIs & Services** → **Credentials**
2. Click on your OAuth client ID (created in Part 1, Step 4)
3. Under "**Authorized redirect URIs**":
   - Click "**+ Add URI**"
   - Paste the Clerk callback URL
4. Click "**Save**"

### Step 4: Configure Google in Clerk

1. Back in **Clerk Dashboard** → **Social Connections** → **Google**
2. Toggle the switch to "**Enable**"
3. Select "**Use custom credentials**"
4. Enter your Google OAuth credentials from Part 1:
   - **Client ID**: Paste from Google Cloud Console
   - **Client Secret**: Paste from Google Cloud Console
5. Click "**Save**"

### Step 5: Test the Integration

1. In Clerk Dashboard, click "**Testing**" in the left sidebar
2. You should see a test sign-in interface
3. Click "**Sign in with Google**"
4. You should be redirected to Google's consent screen
5. Approve the permissions
6. You should be redirected back to Clerk successfully

✅ **If this works, Google OAuth is configured correctly!**

---

## Part 3: Get Your Clerk API Keys

In Clerk Dashboard → **API Keys**:

1. **Publishable Key**: Copy this (starts with `pk_test_` or `pk_live_`)
2. **Secret Key**: Copy this (starts with `sk_test_` or `sk_live_`)
3. **Frontend API URL**: Note this (e.g., `https://your-app.clerk.accounts.dev`)
4. **JWKS URL**: Construct from Frontend API:
   - Format: `https://your-app.clerk.accounts.dev/.well-known/jwks.json`

---

## Part 4: Configure Your Backend

### Step 1: Add Environment Variables

Create or update `.env` file on your server (`/var/www/rmirror-cloud/backend/.env`):

```bash
# Clerk Configuration
CLERK_PUBLISHABLE_KEY=pk_test_xxxxx
CLERK_SECRET_KEY=sk_test_xxxxx
CLERK_JWKS_URL=https://your-app.clerk.accounts.dev/.well-known/jwks.json
```

### 5. Configure Webhooks (Optional but Recommended)

Clerk webhooks keep your database in sync with Clerk user data.

1. In Clerk Dashboard → "Webhooks"
2. Add endpoint: `https://rmirror.io/api/v1/webhooks/clerk`
3. Subscribe to events:
   - `user.created`
   - `user.updated`
   - `user.deleted`
4. Copy the **Signing Secret** and add to `.env`:

```bash
CLERK_WEBHOOK_SECRET=whsec_xxxxx
```

## How It Works

### Authentication Flow

1. **User logs in** via Clerk UI component (on landing page or app)
2. **Clerk issues JWT** token containing user ID and claims
3. **Agent/Frontend sends JWT** in Authorization header: `Bearer <token>`
4. **Backend validates JWT** against Clerk's JWKS endpoint
5. **Backend looks up user** by Clerk user ID
6. **Backend returns data** if user exists and is authorized

### User Sync Flow

1. **User signs up** via Clerk
2. **Clerk sends webhook** to `https://rmirror.io/api/v1/webhooks/clerk`
3. **Backend creates/updates** user record with Clerk ID
4. **User data stays in sync** via subsequent webhooks

## Implementation Details

### Backend Components

```
backend/
├── app/
│   ├── config.py                    # Clerk env vars
│   ├── auth/
│   │   ├── clerk.py                 # Clerk auth dependency
│   │   └── dependencies.py          # Unified auth (Clerk + API key)
│   └── api/
│       └── webhooks/
│           └── clerk.py             # Webhook handler
```

### User Model Changes

The `User` model now supports both authentication methods:

```python
class User(Base):
    id: int
    email: str

    # Authentication - either Clerk or password-based
    clerk_user_id: str | None       # NEW: Clerk user ID
    hashed_password: str | None     # Now optional

    # ... other fields
```

### Protected Endpoints

Endpoints can require Clerk authentication:

```python
from app.auth.clerk import get_clerk_user

@app.get("/api/v1/notebooks")
async def get_notebooks(
    user: User = Depends(get_clerk_user),
    db: Session = Depends(get_db)
):
    return user.notebooks
```

## Testing

### Test Authentication Locally

1. Get a test JWT from Clerk Dashboard → "JWT Templates"
2. Use in API requests:

```bash
curl -H "Authorization: Bearer <jwt_token>" \
  https://rmirror.io/api/v1/notebooks
```

### Test Webhooks

Use Clerk's webhook testing tool in the dashboard to send test events to your endpoint.

## Migration Guide

### For Existing Users

Existing users with email/password can:
1. Continue using their password
2. Link their account to Clerk via email matching
3. Use social login if email matches

### For New Users

New users:
1. Sign up via Clerk (Google/Apple)
2. Get automatic account creation via webhook
3. Access API immediately with JWT

---

## Common Issues & Troubleshooting

### "Redirect URI mismatch" Error

**Problem**: Google shows "Error 400: redirect_uri_mismatch"

**Solutions**:
- ✅ Verify the redirect URI in Google Cloud exactly matches the one from Clerk
- ✅ Check for no trailing slashes
- ✅ Ensure using HTTPS (not HTTP)
- ✅ Wait 5-10 minutes after saving changes in Google Cloud Console

### "Access blocked: This app's request is invalid"

**Problem**: Google blocks the sign-in attempt

**Solutions**:
- ✅ Make sure you've configured the OAuth consent screen in Google Cloud
- ✅ Add your email as a test user in the OAuth consent screen
- ✅ Verify "Authorized domains" includes `rmirror.io`

### "unauthorized_client" Error

**Problem**: Authorization fails with unauthorized_client

**Solutions**:
- ✅ Check that Client ID and Secret are correctly copied (no extra spaces)
- ✅ Verify you're using the correct OAuth client (Web application type)
- ✅ Make sure the OAuth client is enabled in Google Cloud

### JWT Validation Fails

**Problem**: Backend rejects valid Clerk JWTs

**Solutions**:
- ✅ Check `CLERK_JWKS_URL` is correct and accessible
- ✅ Ensure JWT hasn't expired (Clerk JWTs expire after 1 hour)
- ✅ Verify clock sync between server and Clerk
- ✅ Check for typos in environment variables

### User Not Found After Login

**Problem**: User can log in to Clerk but backend says "user not found"

**Solutions**:
- ✅ Check webhook is configured and receiving events
- ✅ Manually create user record if needed
- ✅ Verify `clerk_user_id` in database matches JWT `sub` claim
- ✅ Check backend logs for webhook errors

### Webhook Signature Verification Fails

**Problem**: Clerk webhooks are rejected by backend

**Solutions**:
- ✅ Verify `CLERK_WEBHOOK_SECRET` is correct
- ✅ Check webhook endpoint is receiving raw request body
- ✅ Ensure no middleware is modifying request before verification
- ✅ Verify webhook URL in Clerk dashboard is correct

### Can't Access Beta Page

**Problem**: `https://rmirror.io/beta` shows 404

**Solutions**:
- ✅ Deploy the beta page: `scp landing/beta.html deploy@167.235.74.51:/var/www/rmirror-landing/`
- ✅ Check nginx configuration includes the landing page directory
- ✅ Verify file permissions: `chmod 644 /var/www/rmirror-landing/beta.html`

## Security Best Practices

1. **Always validate JWTs** - Never trust client-sent user IDs
2. **Use HTTPS only** - Clerk requires HTTPS for production
3. **Rotate secrets** - Periodically rotate Clerk secret keys
4. **Monitor webhooks** - Set up alerts for webhook failures
5. **Implement rate limiting** - Protect webhook endpoint from abuse

## Next Steps

After setup:
1. Add Clerk UI components to landing page
2. Update agent to obtain and use Clerk tokens
3. Test complete authentication flow
4. Monitor webhook delivery in Clerk dashboard
5. Consider enabling MFA for enhanced security

## Resources

- [Clerk Documentation](https://clerk.com/docs)
- [FastAPI-Clerk-Auth](https://pypi.org/project/fastapi-clerk-auth/)
- [Clerk Python Backend SDK](https://pypi.org/project/clerk-backend-sdk/)
- [Clerk Dashboard](https://dashboard.clerk.com/)
