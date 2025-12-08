# SendGrid Setup Guide for rMirror Cloud

This guide covers setting up SendGrid for both application emails (user notifications) and system monitoring emails (logwatch, alerts).

## Overview

SendGrid will be used for:
1. **Application Emails**: Welcome emails, sync notifications, user alerts
2. **System Monitoring**: Daily logwatch reports, server alerts
3. **Unified Email Infrastructure**: One service for all email needs

## Prerequisites

- SendGrid account (sign up at https://sendgrid.com)
- SSH access to server
- sudo privileges on server

## Step-by-Step Setup

### 1. Get SendGrid API Key

1. Sign up at https://sendgrid.com
   - Free tier: 100 emails/day (sufficient for monitoring + early users)
   - Paid plans available when you scale

2. Create API Key:
   - Go to **Settings → API Keys**
   - Click **Create API Key**
   - Name: `rmirror-cloud-production`
   - Permission Level: **Full Access** (or Restricted with "Mail Send" permission)
   - **Copy the API key** (shown only once!)

### 2. Verify Sender Identity

SendGrid requires sender verification before sending emails:

1. Go to **Settings → Sender Authentication**
2. Choose one of:
   - **Single Sender Verification** (quick, for testing)
     - Add `noreply@rmirror.io`
     - Verify via email link

   - **Domain Authentication** (recommended for production)
     - Authenticate `rmirror.io` domain
     - Add DNS records provided by SendGrid
     - More professional, better deliverability

### 3. Run Setup Script on Server

Upload and run the setup script:

```bash
# Upload setup script
scp scripts/setup_sendgrid.sh deploy@167.235.74.51:/tmp/

# SSH to server
ssh deploy@167.235.74.51

# Run setup script
chmod +x /tmp/setup_sendgrid.sh
/tmp/setup_sendgrid.sh
```

The script will:
- Install SendGrid Python library in backend
- Configure environment variables
- Set up Postfix to relay via SendGrid
- Configure logwatch for daily reports
- Send test email

### 4. Update Backend Code (Local Development)

The following files have been added/updated:

1. **`backend/app/config.py`**
   - Added SendGrid configuration settings

2. **`backend/app/utils/email.py`** (NEW)
   - Email service with helper methods
   - Pre-built templates for common emails

3. **`backend/pyproject.toml`**
   - Will be updated by setup script with `sendgrid` dependency

### 5. Deploy Updated Backend

After running the setup script, deploy your updated code:

```bash
# From local machine
cd /Users/gabriele/Documents/Development/rmirror-cloud
git add backend/app/config.py backend/app/utils/email.py
git commit -m "feat: add SendGrid email integration"
git push

# On server (or use deployment script)
cd /var/www/rmirror-cloud/backend
git pull
poetry install
systemctl restart rmirror  # or pm2 restart
```

## Usage Examples

### In Your Backend Code

```python
from app.utils.email import get_email_service

email_service = get_email_service()

# Send welcome email
email_service.send_welcome_email(
    user_email="user@example.com",
    user_name="John Doe"
)

# Send sync notification
email_service.send_sync_notification(
    user_email="user@example.com",
    user_name="John Doe",
    notebook_count=5
)

# Send admin alert
email_service.send_admin_alert(
    subject="High Memory Usage",
    message="Server memory usage at 90%",
    severity="warning"  # info, warning, error, critical
)

# Send custom email
email_service.send_email(
    to_email="user@example.com",
    subject="Custom Email",
    html_content="<h1>Hello!</h1><p>This is a custom email.</p>",
    plain_text_content="Hello! This is a custom email."
)
```

### Testing Email Delivery

```bash
# Test via command line (after setup)
echo "Test email body" | mail -s "Test Subject" your-email@example.com

# Check Postfix logs
sudo tail -f /var/log/mail.log

# Check SendGrid Activity
# Go to SendGrid dashboard → Activity
```

### Monitoring Emails

Logwatch will automatically send daily reports to your admin email at:
- Time: Early morning (configured in `/etc/cron.daily/00logwatch`)
- Content: Security events, SSH logins, errors, warnings

To test logwatch manually:
```bash
sudo /usr/sbin/logwatch --output mail --mailto your-email@example.com
```

## Environment Variables

Add these to `backend/.env`:

```bash
# SendGrid Email Configuration
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxx
SENDGRID_FROM_EMAIL=noreply@rmirror.io
SENDGRID_FROM_NAME=rMirror Cloud
ADMIN_EMAIL=your-email@example.com
```

## SendGrid Dashboard

Monitor your email activity:
- **Activity Feed**: See all sent emails, opens, clicks
- **Stats**: Delivery rates, bounce rates, spam reports
- **Alerts**: Set up alerts for delivery issues
- **Suppressions**: Manage bounces, unsubscribes, spam reports

Access at: https://app.sendgrid.com/

## Troubleshooting

### Emails Not Sending

1. **Check API Key**
   ```bash
   # On server
   grep SENDGRID_API_KEY /var/www/rmirror-cloud/backend/.env
   ```

2. **Check Postfix Logs**
   ```bash
   sudo tail -50 /var/log/mail.log
   ```

3. **Verify Sender**
   - Go to SendGrid → Settings → Sender Authentication
   - Ensure noreply@rmirror.io is verified

4. **Test SendGrid API**
   ```bash
   curl -X POST https://api.sendgrid.com/v3/mail/send \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "personalizations": [{"to": [{"email": "test@example.com"}]}],
       "from": {"email": "noreply@rmirror.io"},
       "subject": "Test",
       "content": [{"type": "text/plain", "value": "Test"}]
     }'
   ```

### Emails Going to Spam

1. **Complete Domain Authentication** in SendGrid
2. **Add SPF/DKIM records** to your DNS
3. **Warm up your sending** - start with low volume
4. **Avoid spam triggers** - don't use ALL CAPS, excessive links

### Rate Limiting

Free tier: 100 emails/day
- Monitor usage in SendGrid dashboard
- Upgrade plan if needed
- Implement email batching for user notifications

## Scaling Considerations

When you get more users:

1. **Upgrade SendGrid Plan**
   - Essential: $15/mo for 40,000 emails
   - Pro: $90/mo for 100,000 emails

2. **Implement Email Queues**
   - Use Redis (already in your stack)
   - Queue emails instead of sending immediately
   - Process in background worker

3. **Add Email Templates**
   - Use SendGrid's template feature
   - Easier to update without code changes

4. **Track Email Events**
   - Set up webhooks for opens, clicks, bounces
   - Store in database for analytics

## Security Best Practices

1. **Protect API Key**
   - Never commit to git
   - Use environment variables only
   - Rotate periodically

2. **Limit Permissions**
   - Use restricted API key (Mail Send only)
   - Don't use full access in production

3. **Monitor for Abuse**
   - Watch for unusual sending patterns
   - Implement rate limiting per user
   - Log all email sends

## Cost Estimates

- **Free Tier**: 100 emails/day = 3,000/month (sufficient for 10-20 active users + monitoring)
- **Essential ($15/mo)**: 40,000 emails/month (300+ users)
- **Pro ($90/mo)**: 100,000 emails/month (1,000+ users)

## Support

- SendGrid Docs: https://docs.sendgrid.com/
- SendGrid Support: https://support.sendgrid.com/
- rMirror Issues: https://github.com/your-repo/issues
