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

---

## Understanding the Complete Authentication Flow

This section explains how authentication works in rMirror Cloud using Clerk in simple terms.

### The Big Picture

Think of Clerk as a "security guard" that sits between your users and your application. When someone wants to use rMirror Cloud, they need to prove who they are. Instead of managing passwords ourselves (which is complex and risky), we let Clerk handle all the security details.

### The Three Main Flows

There are three important flows to understand:

1. **Initial Sign-Up Flow** - What happens when someone creates an account
2. **Sign-In Flow** - What happens when they come back later
3. **API Access Flow** - What happens when they try to use the application

---

### 1. Initial Sign-Up Flow (First Time User)

```
┌─────────────┐
│   Gabriele  │  "I want to use rMirror Cloud"
└──────┬──────┘
       │
       │ 1. Visits https://rmirror.io/beta
       ▼
┌─────────────────────────────┐
│   rMirror Beta Page         │  Shows "Sign in with Google" button
│   (Your Website)            │
└──────┬──────────────────────┘
       │
       │ 2. Clicks "Sign in with Google"
       ▼
┌─────────────────────────────┐
│   Clerk                     │  "Let me handle this securely"
│   (Authentication Service)  │
└──────┬──────────────────────┘
       │
       │ 3. Redirects to Google
       ▼
┌─────────────────────────────┐
│   Google OAuth              │  "Do you want to allow rMirror Cloud
│   (Google's Login System)   │   to access your email and name?"
└──────┬──────────────────────┘
       │
       │ 4. User clicks "Allow"
       │
       ├─────────────────────────────────────────┐
       │                                         │
       │ 5a. Google confirms identity            │ 5b. Google sends info
       ▼                                         ▼
┌─────────────────────────────┐        ┌────────────────────────┐
│   Clerk                     │        │   Clerk                │
│   "Great! I'll create a     │        │   Creates user profile │
│    session for Gabriele"    │        │   - Clerk user ID      │
└──────┬──────────────────────┘        │   - Email              │
       │                                │   - Name               │
       │                                └────────┬───────────────┘
       │                                         │
       │ 6. Creates JWT token                    │ 7. Sends webhook
       │    (like a secure ID badge)             │    "New user created!"
       ▼                                         ▼
┌─────────────────────────────┐        ┌────────────────────────┐
│   rMirror Beta Page         │        │  rMirror Backend       │
│   "Welcome, Gabriele!"      │        │  Receives webhook      │
│   - Shows user's name       │        │  Creates user in DB:   │
│   - Stores token in browser │        │  - clerk_user_id       │
└─────────────────────────────┘        │  - email               │
                                        │  - full_name           │
                                        └────────────────────────┘
```

**What Just Happened (Step by Step):**

1. **You visit the beta page**: Your browser loads the website with Clerk's sign-in button
2. **You click "Sign in with Google"**: Clerk takes over and redirects you to Google
3. **Google asks for permission**: "Do you want to share your email with rMirror Cloud?"
4. **You click "Allow"**: Google confirms your identity
5. **Clerk creates your account**:
   - Assigns you a unique Clerk user ID (like `user_abc123`)
   - Stores your email and name
   - Creates a "session" (you're now logged in)
6. **You get a token**: Clerk gives your browser a JWT token (think of it as a temporary VIP pass)
7. **Webhook syncs your data**: Clerk sends a message to our backend saying "New user!" and we create your user profile in our database

**Result**: You're now signed in on the website AND your account exists in our database.

---

### 2. Sign-In Flow (Returning User)

```
┌─────────────┐
│   Gabriele  │  "I'm back!"
└──────┬──────┘
       │
       │ 1. Visits https://rmirror.io/beta
       ▼
┌─────────────────────────────┐
│   rMirror Beta Page         │  Checks browser for existing session
│   (Your Website)            │
└──────┬──────────────────────┘
       │
       │ 2. No valid session found → Shows "Sign in with Google"
       │    (If session exists and valid → Skip to step 7)
       ▼
┌─────────────────────────────┐
│   Clerk                     │  Checks if you're already logged in
└──────┬──────────────────────┘
       │
       │ 3. Recognizes you from browser cookie
       │    (or redirects to Google if not)
       ▼
┌─────────────────────────────┐
│   Clerk                     │  "Welcome back, Gabriele!"
│   Issues fresh JWT token    │  Creates new session token
└──────┬──────────────────────┘
       │
       │ 4. Returns to beta page with token
       ▼
┌─────────────────────────────┐
│   rMirror Beta Page         │  "Welcome back, Gabriele!"
│   - Displays your name      │
│   - Stores token            │
│   - Ready to use app        │
└─────────────────────────────┘
```

**What Just Happened:**

1. **You visit the beta page again**: The website checks if you're already logged in
2. **Clerk recognizes you**: Either from a browser cookie or you re-authenticate with Google
3. **You get a fresh token**: Clerk issues a new JWT token (your VIP pass is renewed)
4. **You're signed in**: The website shows your welcome message

**Result**: You're signed in quickly without re-entering credentials every time.

---

### 3. API Access Flow (Using the Application)

Now that you're signed in, you want to actually USE rMirror Cloud - view notebooks, run OCR, etc.

```
┌─────────────┐
│   User's    │  "I want to see my notebooks"
│   Browser   │
│   or Agent  │
└──────┬──────┘
       │
       │ 1. Sends API request with JWT token:
       │    GET /api/v1/notebooks
       │    Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
       ▼
┌─────────────────────────────┐
│   rMirror Backend           │  "Let me verify this token"
│   (FastAPI Server)          │
└──────┬──────────────────────┘
       │
       │ 2. Extracts token from Authorization header
       ▼
┌─────────────────────────────┐
│   Clerk Auth Dependency     │  Step 2a: Calls Clerk to verify token
│   (app/auth/clerk.py)       │  Step 2b: Checks token signature
└──────┬──────────────────────┘  Step 2c: Ensures token not expired
       │
       │ 3. Clerk confirms: "Yes, valid token for user_abc123"
       ▼
┌─────────────────────────────┐
│   Database Lookup           │  Searches for user:
│   (PostgreSQL)              │  WHERE clerk_user_id = 'user_abc123'
└──────┬──────────────────────┘
       │
       │ 4. Found user: Gabriele (ID: 42)
       ▼
┌─────────────────────────────┐
│   API Endpoint              │  "User is authenticated!"
│   (get_notebooks)           │  Fetches Gabriele's notebooks
└──────┬──────────────────────┘
       │
       │ 5. Returns data
       ▼
┌─────────────────────────────┐
│   User's Browser/Agent      │  Receives notebooks:
│                             │  - Notebook 1
│                             │  - Notebook 2
└─────────────────────────────┘  - ...
```

**What Just Happened (Detailed):**

1. **You make a request**: Your browser (or agent) sends an API request with your JWT token in the header
2. **Backend checks the token**:
   - Extracts the token from the `Authorization: Bearer <token>` header
   - Calls our Clerk authentication dependency (`get_clerk_user`)
   - Clerk verifies the token signature (proves it came from Clerk)
   - Checks if the token has expired (tokens are only valid for 1 hour)
3. **Clerk confirms identity**: Returns the Clerk user ID (`user_abc123`)
4. **Database lookup**: We find your user record using the Clerk user ID
5. **Access granted**: The API returns your notebooks

**Result**: You can securely access your data. The backend knows it's really you because Clerk verified the token.

---

### Security: How JWT Tokens Work

Think of a JWT token like a tamper-proof concert wristband:

```
JWT Token Structure:
┌─────────────────────────────────────────────────────────────┐
│ Header        │ Payload             │ Signature              │
│ (Algorithm)   │ (Your Info)         │ (Proof of Authenticity)│
├───────────────┼─────────────────────┼────────────────────────┤
│ {             │ {                   │ [Cryptographic         │
│   "alg": "RS" │   "sub": "user_abc" │  signature that        │
│   "typ": "JWT"│   "email": "g@..."  │  proves Clerk          │
│ }             │   "exp": 1234567890 │  issued this token]    │
│               │ }                   │                        │
└───────────────┴─────────────────────┴────────────────────────┘
```

**Key Points:**

- **Payload contains your info**: User ID, email, expiration time
- **Signature proves it's real**: Like a watermark that can't be forged
- **Tokens expire**: After 1 hour, you need a fresh token
- **Can't be modified**: Changing any part breaks the signature
- **Transmitted securely**: Always sent over HTTPS

**Why This Is Secure:**

1. Even if someone intercepts the token, they can only use it for 1 hour
2. The backend verifies every token with Clerk before granting access
3. We never store the token on our backend (stateless authentication)
4. Only Clerk can create valid tokens (we can't forge them)

---

### Complete Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────────┐
│                          CLERK ECOSYSTEM                              │
│  ┌──────────────────┐         ┌────────────────────┐                 │
│  │  Clerk Dashboard │         │   Clerk Backend    │                 │
│  │  (Configuration) │         │   (Token Issuer)   │                 │
│  └──────────────────┘         └────────┬───────────┘                 │
│                                         │                              │
│                                         │ Issues JWT Tokens            │
│                                         │ Sends Webhooks               │
└─────────────────────────────────────────┼──────────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    │                     │                     │
          Webhooks  │           Tokens    │           Tokens    │
          (user     │           (browser) │           (agent)   │
          events)   │                     │                     │
                    ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         RMIRROR CLOUD                                │
│                                                                      │
│  ┌────────────────────┐      ┌──────────────────────────────────┐  │
│  │  Landing/Beta Page │      │  rMirror Agent (macOS)           │  │
│  │  https://rmirror.io│      │  - Syncs reMarkable files        │  │
│  │                    │      │  - Uses JWT for API calls        │  │
│  │  Clerk UI:         │      └──────────────┬───────────────────┘  │
│  │  - Sign in         │                     │                      │
│  │  - Sign out        │                     │ API calls with       │
│  │  - User profile    │                     │ JWT token            │
│  └────────┬───────────┘                     │                      │
│           │                                 │                      │
│           │ API calls with JWT token        │                      │
│           ▼                                 ▼                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              FastAPI Backend (rmirror.io/api)                │  │
│  │                                                               │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │  Authentication Middleware                          │   │  │
│  │  │  1. Extract JWT from Authorization header           │   │  │
│  │  │  2. Verify with Clerk (check signature + expiry)    │   │  │
│  │  │  3. Extract clerk_user_id from token                │   │  │
│  │  │  4. Look up user in database                        │   │  │
│  │  └──────────────────┬───────────────────────────────────┘   │  │
│  │                     │                                        │  │
│  │                     ▼                                        │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │  Protected API Endpoints                            │   │  │
│  │  │  - GET /notebooks (list user's notebooks)           │   │  │
│  │  │  - POST /processing/ocr (run OCR)                   │   │  │
│  │  │  - GET /integrations (list connected services)      │   │  │
│  │  │  ... all require valid JWT                          │   │  │
│  │  └──────────────────────────────────────────────────────┘   │  │
│  │                                                               │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │  Webhook Endpoint                                    │   │  │
│  │  │  POST /webhooks/clerk                                │   │  │
│  │  │  - Receives user.created events                      │   │  │
│  │  │  - Receives user.updated events                      │   │  │
│  │  │  - Receives user.deleted events                      │   │  │
│  │  │  - Syncs user data to database                       │   │  │
│  │  └──────────────────┬───────────────────────────────────┘   │  │
│  │                     │                                        │  │
│  │                     ▼                                        │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │  PostgreSQL Database                                 │   │  │
│  │  │                                                       │   │  │
│  │  │  users table:                                        │   │  │
│  │  │    - id (primary key)                                │   │  │
│  │  │    - email                                           │   │  │
│  │  │    - full_name                                       │   │  │
│  │  │    - clerk_user_id (from Clerk)                      │   │  │
│  │  │    - hashed_password (NULL for Clerk users)          │   │  │
│  │  │    - is_active                                       │   │  │
│  │  │    - created_at                                      │   │  │
│  │  │                                                       │   │  │
│  │  │  notebooks, pages, ocr_results, etc...               │   │  │
│  │  └──────────────────────────────────────────────────────┘   │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘

External Services:
┌───────────────────┐
│  Google OAuth     │  Used by Clerk for social login
└───────────────────┘
```

---

### Real-World Example: Gabriele's Journey

Let's follow a complete user journey:

**Day 1: First Sign-Up**

1. **9:00 AM**: Gabriele visits `https://rmirror.io/beta`
2. **9:00:10 AM**: Clicks "Sign in with Google"
3. **9:00:15 AM**: Google asks "Allow rMirror Cloud to access your info?"
4. **9:00:20 AM**: Clicks "Allow"
5. **9:00:25 AM**:
   - Clerk creates Gabriele's account with ID `user_2abc123xyz`
   - Issues JWT token (expires at 10:00 AM)
   - Sends webhook to rMirror backend
6. **9:00:26 AM**: rMirror backend receives webhook, creates user:
   ```sql
   INSERT INTO users (clerk_user_id, email, full_name)
   VALUES ('user_2abc123xyz', 'gabriele@example.com', 'Gabriele Gottino');
   ```
7. **9:00:27 AM**: Gabriele sees "Welcome, Gabriele!" on the beta page

**Day 1: Using the Mac Agent**

1. **9:05 AM**: Gabriele installs rMirror Mac agent
2. **9:06 AM**: Agent needs to authenticate - opens browser to Clerk
3. **9:06:30 AM**: Clerk recognizes Gabriele is already signed in, issues new token
4. **9:06:35 AM**: Agent stores token and begins syncing notebooks:
   ```http
   POST /api/v1/sync/upload
   Authorization: Bearer eyJhbGc...
   ```
5. **9:06:36 AM**: Backend verifies token with Clerk ✓
6. **9:06:37 AM**: Backend looks up user by `clerk_user_id` ✓
7. **9:06:38 AM**: Upload succeeds, notebooks saved to Gabriele's account

**Day 2: Coming Back**

1. **10:15 AM**: Gabriele opens laptop, visits `https://rmirror.io/beta`
2. **10:15:05 AM**: Old JWT has expired (they last 1 hour)
3. **10:15:06 AM**: Clerk sees Gabriele's browser cookie, issues fresh token automatically
4. **10:15:07 AM**: "Welcome back, Gabriele!" - signed in without re-entering password

**Day 2: Agent Keeps Working**

1. **10:20 AM**: Agent tries to sync new notebook
2. **10:20:01 AM**: Backend rejects old expired token (401 Unauthorized)
3. **10:20:02 AM**: Agent automatically gets fresh token from Clerk
4. **10:20:03 AM**: Retry succeeds with new token

---

### Key Takeaways

1. **Clerk handles all authentication complexity**
   - You never see passwords, tokens are issued automatically
   - Social login "just works" (Google, Apple, etc.)

2. **JWT tokens are temporary passes**
   - Valid for 1 hour
   - Automatically refreshed when needed
   - Can't be forged or tampered with

3. **Webhooks keep everything in sync**
   - When you sign up in Clerk → User created in our database
   - When you update profile → Changes synced to our database
   - When you delete account → Account deactivated in our database

4. **Your data is secure**
   - Every API call is verified with Clerk
   - Tokens expire quickly
   - All communication over HTTPS
   - We can revoke access instantly via Clerk dashboard

5. **Seamless experience**
   - Sign in once, use everywhere (web, agent, mobile eventually)
   - No passwords to remember
   - Fast authentication with session caching

---

This architecture means you get enterprise-grade security without the complexity of building it yourself!
