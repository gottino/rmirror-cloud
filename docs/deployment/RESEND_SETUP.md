# Resend Email Service Setup Guide

## Overview

rMirror Cloud uses [Resend](https://resend.com) for transactional email delivery. Resend provides a modern, developer-friendly API for sending emails with excellent deliverability and detailed analytics.

## Why Resend?

- Modern API with excellent developer experience
- Built-in email verification and authentication (SPF, DKIM, DMARC)
- Generous free tier (3,000 emails/month for free forever)
- High deliverability rates
- Real-time analytics and webhooks
- No credit card required for free tier

## Getting Started

### 1. Create a Resend Account

1. Visit [resend.com](https://resend.com)
2. Click "Sign Up" or "Start Building"
3. Sign up with your email or GitHub account
4. Verify your email address

### 2. Get Your API Key

1. Log in to your Resend dashboard
2. Navigate to **API Keys** in the sidebar
3. Click **Create API Key**
4. Give it a descriptive name (e.g., "rMirror Production")
5. Choose permissions:
   - **Sending access**: Full access (required for sending emails)
   - **Domain settings**: Read-only (optional)
6. Click **Create**
7. Copy the API key (starts with `re_`)
   - **Important**: Save this immediately - you won't be able to see it again!

**Example API Key:**
```
re_123456789abcdefghijklmnopqrstuvw
```

### 3. Configure Your Domain (Recommended)

For production use, you should configure your own domain to send emails from (e.g., `notifications@rmirror.io`).

#### Add Your Domain

1. In Resend dashboard, go to **Domains**
2. Click **Add Domain**
3. Enter your domain name (e.g., `rmirror.io`)
4. Click **Add**

#### Configure DNS Records

Resend will provide DNS records to add to your domain. You need to add these records to verify ownership and enable email authentication.

**Required DNS Records:**

1. **SPF Record** (TXT record):
   ```
   Name: @
   Type: TXT
   Value: v=spf1 include:_spf.resend.com ~all
   ```

2. **DKIM Records** (CNAME records):
   ```
   Name: resend._domainkey
   Type: CNAME
   Value: [provided by Resend]

   Name: resend2._domainkey
   Type: CNAME
   Value: [provided by Resend]
   ```

3. **DMARC Record** (TXT record):
   ```
   Name: _dmarc
   Type: TXT
   Value: v=DMARC1; p=none; rua=mailto:dmarc@resend.com
   ```

**How to add DNS records:**

For **Cloudflare**:
1. Log in to Cloudflare
2. Select your domain
3. Go to **DNS** → **Records**
4. Click **Add record**
5. Add each DNS record from Resend
6. Wait for DNS propagation (usually 15-60 minutes)

For **Other DNS Providers**:
- Follow your provider's documentation for adding DNS records
- Common providers: GoDaddy, Namecheap, Route53, Google Domains

#### Verify Your Domain

1. After adding DNS records, return to Resend dashboard
2. Go to **Domains**
3. Click **Verify** on your domain
4. If verification fails, wait a few minutes and try again (DNS propagation can take time)
5. Once verified, you'll see a green checkmark

### 4. Choose Your Sender Email

After verifying your domain, you can send from any email address at that domain:

- `noreply@rmirror.io` - For transactional emails
- `notifications@rmirror.io` - For notifications
- `support@rmirror.io` - For support emails

**For Testing (without custom domain):**
- You can use `onboarding@resend.dev` for testing
- This works immediately without DNS setup
- Not recommended for production

---

## Backend Configuration

### Environment Variables

Add these environment variables to your backend `.env` file:

**Local Development (`.env`):**
```bash
# Resend Email Service
RESEND_API_KEY=re_your_api_key_here
RESEND_FROM_EMAIL=onboarding@resend.dev  # Use this for testing
```

**Production (`.env` or environment variables):**
```bash
# Resend Email Service
RESEND_API_KEY=re_your_production_api_key_here
RESEND_FROM_EMAIL=noreply@rmirror.io  # Use your verified domain
```

**Environment Variable Details:**

- **RESEND_API_KEY**: Your Resend API key (required)
  - Starts with `re_`
  - Keep this secret - never commit to git
  - Use different keys for dev/staging/production

- **RESEND_FROM_EMAIL**: Email address to send from (required)
  - Must be from a verified domain (or use `onboarding@resend.dev` for testing)
  - Format: `name@domain.com` or `Name <name@domain.com>`

### Install Resend SDK

The Resend Python SDK should already be installed via Poetry. If not:

```bash
cd backend
poetry add resend
```

### Backend Code Example

The backend uses Resend to send emails via the `EmailService` class:

```python
from app.core.email_service import EmailService

# Initialize email service (reads from env vars)
email_service = EmailService()

# Send welcome email
await email_service.send_welcome_email(
    to_email="user@example.com",
    user_name="John Doe"
)

# Send notification
await email_service.send_notification(
    to_email="user@example.com",
    subject="Your notebook is ready",
    html_content="<p>Your notebook has been processed.</p>"
)
```

---

## Testing Email Sending

### Test with Python Script

Create a test script to verify your Resend configuration:

**File:** `backend/test_email.py`

```python
#!/usr/bin/env python3
"""Test Resend email configuration."""

import asyncio
import os
from dotenv import load_dotenv
import resend

load_dotenv()

async def test_email():
    """Send a test email via Resend."""
    # Configure Resend
    resend.api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    # Send test email
    params = {
        "from": from_email,
        "to": ["your-email@example.com"],  # Replace with your email
        "subject": "rMirror Resend Test",
        "html": "<strong>It works!</strong> Your Resend configuration is correct."
    }

    try:
        email = resend.Emails.send(params)
        print(f"✅ Email sent successfully!")
        print(f"Email ID: {email['id']}")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_email())
```

**Run the test:**

```bash
cd backend
poetry run python test_email.py
```

### Test via API Endpoint

If your backend has an email test endpoint:

```bash
curl -X POST https://your-domain.com/v1/test/send-email \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to_email": "your-email@example.com",
    "subject": "Test Email",
    "message": "This is a test from rMirror"
  }'
```

### Check Email Delivery

1. **Check your inbox** for the test email
2. **Check spam folder** if you don't see it
3. **Check Resend dashboard**:
   - Go to **Logs** in Resend dashboard
   - View delivery status, opens, clicks
   - Check for bounces or errors

---

## Production Deployment

### 1. Set Environment Variables

**Using systemd (Linux):**

Edit `/etc/systemd/system/rmirror.service`:

```ini
[Service]
Environment="RESEND_API_KEY=re_your_production_key"
Environment="RESEND_FROM_EMAIL=noreply@rmirror.io"
```

Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart rmirror.service
```

**Using Docker:**

In `docker-compose.yml`:
```yaml
services:
  backend:
    environment:
      - RESEND_API_KEY=${RESEND_API_KEY}
      - RESEND_FROM_EMAIL=${RESEND_FROM_EMAIL}
```

Or pass via command line:
```bash
docker run -e RESEND_API_KEY=re_your_key \
           -e RESEND_FROM_EMAIL=noreply@rmirror.io \
           rmirror-backend
```

### 2. Verify Configuration

After deployment, verify environment variables are set:

```bash
# SSH to production server
ssh user@your-server.com

# Check environment variables (use appropriate method for your deployment)
sudo systemctl show rmirror.service | grep RESEND

# Or check running process
sudo cat /proc/$(pgrep -f uvicorn)/environ | tr '\0' '\n' | grep RESEND
```

### 3. Test in Production

Send a test email from production:

```bash
curl -X POST https://rmirror.io/v1/test/send-email \
  -H "Authorization: Bearer PROD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_email": "admin@rmirror.io"}'
```

---

## Monitoring & Analytics

### Resend Dashboard

Monitor email delivery in the Resend dashboard:

1. **Logs**: View all sent emails, delivery status, opens, clicks
2. **Analytics**: Track email performance over time
3. **Webhooks**: Set up webhooks for delivery events (optional)

**Key Metrics to Monitor:**
- **Delivered**: Percentage of emails successfully delivered
- **Bounce Rate**: Emails that failed to deliver (should be <5%)
- **Open Rate**: Emails opened by recipients
- **Click Rate**: Links clicked in emails

### Set Up Webhooks (Optional)

Resend can send webhooks for email events:

1. Go to **Webhooks** in Resend dashboard
2. Click **Add Endpoint**
3. Enter your webhook URL (e.g., `https://rmirror.io/v1/webhooks/resend`)
4. Select events to receive:
   - `email.delivered`
   - `email.bounced`
   - `email.opened`
   - `email.clicked`
5. Click **Create**

**Backend webhook handler example:**

```python
@router.post("/webhooks/resend")
async def resend_webhook(request: Request):
    """Handle Resend webhook events."""
    payload = await request.json()
    event_type = payload.get("type")

    if event_type == "email.delivered":
        # Email was delivered successfully
        logger.info(f"Email delivered: {payload['data']['email_id']}")
    elif event_type == "email.bounced":
        # Email bounced - handle accordingly
        logger.warning(f"Email bounced: {payload['data']['email_id']}")

    return {"status": "ok"}
```

---

## Troubleshooting

### Common Issues

#### 1. "API key not found" or "Invalid API key"

**Problem:** Resend returns 401 Unauthorized.

**Solution:**
- Verify API key is set: `echo $RESEND_API_KEY`
- Ensure key starts with `re_`
- Check for extra spaces or newlines in `.env` file
- Regenerate API key in Resend dashboard if needed

#### 2. "Email not sent - domain not verified"

**Problem:** Trying to send from unverified domain.

**Solution:**
- Use `onboarding@resend.dev` for testing
- Or verify your domain in Resend dashboard
- Check DNS records are correctly added
- Wait for DNS propagation (up to 24 hours)

#### 3. Emails going to spam

**Problem:** Emails delivered but landing in spam folder.

**Solution:**
- Verify your domain and add all DNS records (SPF, DKIM, DMARC)
- Avoid spam trigger words in subject/body
- Use a consistent "From" email address
- Warm up your domain (start with low volume, increase gradually)
- Check Resend deliverability score in dashboard

#### 4. Environment variables not loaded

**Problem:** Backend can't find RESEND_API_KEY.

**Solution:**
```bash
# Check if .env is loaded
cd backend
poetry run python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('RESEND_API_KEY'))"

# Verify .env file exists and is readable
cat .env | grep RESEND

# Restart backend service
sudo systemctl restart rmirror.service
```

#### 5. Rate limiting errors

**Problem:** Resend returns 429 Too Many Requests.

**Solution:**
- Free tier: 100 emails/day, 3,000/month
- Upgrade to paid plan if needed
- Implement email queueing/batching
- Add retry logic with exponential backoff

---

## Best Practices

### 1. Use Different Keys for Different Environments

```bash
# Development
RESEND_API_KEY=re_dev_key_123
RESEND_FROM_EMAIL=onboarding@resend.dev

# Staging
RESEND_API_KEY=re_staging_key_456
RESEND_FROM_EMAIL=staging@rmirror.io

# Production
RESEND_API_KEY=re_prod_key_789
RESEND_FROM_EMAIL=noreply@rmirror.io
```

### 2. Never Commit API Keys

Add to `.gitignore`:
```
.env
.env.local
.env.*.local
```

Use environment variables or secret managers in production.

### 3. Implement Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def send_email_with_retry(email_params):
    """Send email with automatic retries."""
    return resend.Emails.send(email_params)
```

### 4. Monitor Deliverability

- Check bounce rates weekly
- Remove bounced email addresses from your list
- Monitor spam complaints
- Keep engagement high (opens, clicks)

### 5. Email Content Guidelines

- Use clear, concise subject lines
- Avoid spam trigger words ("FREE", "ACT NOW", etc.)
- Include unsubscribe link for marketing emails
- Test emails before sending to users
- Use responsive HTML templates

---

## Pricing

### Free Tier
- **3,000 emails/month** - Free forever
- All features included
- No credit card required

### Pro Tier ($20/month)
- **50,000 emails/month**
- Priority support
- Custom sending limits
- Advanced analytics

### Enterprise
- Custom volume
- Dedicated IP addresses
- SLA guarantees
- Premium support

**For most rMirror deployments, the free tier is sufficient.**

---

## Migration from SendGrid

If you're migrating from SendGrid:

### 1. Update Environment Variables

Replace:
```bash
SENDGRID_API_KEY=SG.xxx
SENDGRID_FROM_EMAIL=noreply@rmirror.io
```

With:
```bash
RESEND_API_KEY=re_xxx
RESEND_FROM_EMAIL=noreply@rmirror.io
```

### 2. Update Code

Replace SendGrid SDK calls with Resend:

**Before (SendGrid):**
```python
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

message = Mail(
    from_email='noreply@rmirror.io',
    to_emails='user@example.com',
    subject='Welcome',
    html_content='<p>Welcome!</p>'
)
sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
response = sg.send(message)
```

**After (Resend):**
```python
import resend

resend.api_key = os.environ.get('RESEND_API_KEY')

params = {
    "from": "noreply@rmirror.io",
    "to": ["user@example.com"],
    "subject": "Welcome",
    "html": "<p>Welcome!</p>"
}
email = resend.Emails.send(params)
```

### 3. Update Dependencies

```bash
# Remove SendGrid
poetry remove sendgrid

# Add Resend
poetry add resend
```

---

## Additional Resources

- **Resend Documentation**: https://resend.com/docs
- **API Reference**: https://resend.com/docs/api-reference
- **Python SDK**: https://github.com/resendlabs/resend-python
- **Support**: support@resend.com

---

## Summary Checklist

- [ ] Create Resend account
- [ ] Get API key from dashboard
- [ ] (Production) Add and verify custom domain
- [ ] (Production) Configure DNS records (SPF, DKIM, DMARC)
- [ ] Add `RESEND_API_KEY` to `.env`
- [ ] Add `RESEND_FROM_EMAIL` to `.env`
- [ ] Test email sending locally
- [ ] Deploy to production with environment variables
- [ ] Send test email in production
- [ ] Monitor deliverability in Resend dashboard
- [ ] Set up webhooks (optional)

---

**Last Updated:** December 26, 2025

For issues or questions, please refer to the [rMirror documentation](../../README.md) or contact support.
