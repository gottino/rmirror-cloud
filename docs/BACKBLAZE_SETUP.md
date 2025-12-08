# Backblaze B2 Setup Guide

This guide walks through setting up Backblaze B2 for rMirror Cloud file storage.

## Overview

We use Backblaze B2 for two purposes:
1. **User Data Storage** - Stores .rm files, PDFs, and notebook data
2. **Installer Downloads** - Hosts the macOS .dmg installer (separate bucket)

This guide covers the **User Data Storage** setup.

## Step 1: Backblaze B2 Bucket Setup

You should already have:
- ✅ A Backblaze B2 account
- ✅ A bucket created for user data storage
- ✅ Application key with read/write access to the bucket

## Step 2: GitHub Secrets Configuration

Add the following secrets to your GitHub repository:

**Navigate to:** `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

Add these 5 secrets:

### 1. B2_ENDPOINT_URL
**Value:** `https://s3.us-west-004.backblazeb2.com`

This is Backblaze's S3-compatible endpoint. The region code (`us-west-004`) depends on where your bucket is located. Find yours at:
- Go to Backblaze B2 dashboard
- Click on your bucket
- Look for "Endpoint" or "S3 Endpoint"
- Common endpoints:
  - `https://s3.us-west-000.backblazeb2.com` (US West)
  - `https://s3.us-west-001.backblazeb2.com` (US West)
  - `https://s3.us-west-002.backblazeb2.com` (US West)
  - `https://s3.us-west-004.backblazeb2.com` (US West)
  - `https://s3.eu-central-003.backblazeb2.com` (EU Central)

### 2. B2_ACCESS_KEY_ID
**Value:** Your Backblaze Application Key ID (e.g., `004abc123def456789`)

This is the "keyID" you received when creating the application key.

### 3. B2_SECRET_ACCESS_KEY
**Value:** Your Backblaze Application Key (the long secret string)

⚠️ **Important:** This is only shown once when you create the key. If you lost it, you'll need to create a new application key.

### 4. B2_BUCKET_NAME
**Value:** Your bucket name (e.g., `rmirror-user-data`)

This is the name you gave your bucket in the Backblaze dashboard.

### 5. B2_REGION
**Value:** `us-west-004` (or your bucket's region)

Extract the region code from your endpoint URL. For example:
- Endpoint: `https://s3.us-west-004.backblazeb2.com` → Region: `us-west-004`
- Endpoint: `https://s3.eu-central-003.backblazeb2.com` → Region: `eu-central-003`

## Step 3: Verify Setup

After adding all secrets to GitHub, the deployment workflow will automatically inject these values into the backend `.env` file on the next deployment.

### Trigger Deployment

Option 1: Push a change to trigger automatic deployment:
```bash
git add .
git commit -m "chore: add Backblaze B2 configuration"
git push origin main
```

Option 2: Manually trigger deployment from GitHub:
- Go to Actions → Deploy to Production → Run workflow

### Verify on Server

After deployment completes, SSH to the server and verify:

```bash
ssh deploy@167.235.74.51

# Check that S3 variables are set
cd /var/www/rmirror-cloud/backend
grep S3_ .env

# Expected output:
# S3_ENDPOINT_URL=https://s3.us-west-004.backblazeb2.com
# S3_ACCESS_KEY=004abc123def456789
# S3_SECRET_KEY=K004abc...
# S3_BUCKET_NAME=rmirror-user-data
# S3_REGION=us-west-004

# Check backend logs for storage initialization
sudo journalctl -u rmirror -n 50
```

## Step 4: Test File Upload

To verify Backblaze integration is working:

1. Use the rMirror agent to sync a notebook
2. Check backend logs for successful uploads:
   ```bash
   sudo journalctl -u rmirror -f
   # Look for: "Stored .rm file at: users/.../notebooks/.../pages/..."
   ```
3. Verify files appear in Backblaze dashboard:
   - Go to B2 Cloud Storage → Buckets → [your bucket] → Browse Files
   - You should see folders: `users/[user-id]/notebooks/...`

## Step 5: Migrate Existing Files (Optional)

If you have existing files stored locally on the server, you can migrate them to B2:

```bash
# SSH to server
ssh deploy@167.235.74.51

# Check current local storage size
du -sh /var/www/rmirror-cloud/backend/storage/

# Install B2 CLI
pip3 install b2

# Configure B2 CLI
b2 authorize-account <keyID> <applicationKey>

# Sync local storage to B2
cd /var/www/rmirror-cloud/backend
b2 sync --replaceNewer storage/ b2://rmirror-user-data/

# Verify upload
b2 ls b2://rmirror-user-data/users/

# Optional: Remove local files after confirming B2 has everything
# rm -rf storage/users/
```

⚠️ **Warning:** Only delete local files after thoroughly verifying all data is in B2.

## Troubleshooting

### "Invalid credentials" or "Access denied" errors

**Check:**
- Application key has read/write access to the bucket
- Key is not restricted to a specific path that conflicts
- Bucket name matches exactly

**Fix:** Create a new application key with full bucket access.

### "Endpoint not found" errors

**Check:**
- Endpoint URL matches your bucket's region
- URL format: `https://s3.REGION.backblazeb2.com` (no trailing slash)

**Fix:** Get correct endpoint from Backblaze dashboard → Bucket details.

### Files still going to local storage

**Check:**
- Deployment succeeded
- `.env` file has S3 variables set
- Backend service restarted after deployment

**Fix:**
```bash
ssh deploy@167.235.74.51
cd /var/www/rmirror-cloud/backend
cat .env | grep S3_
sudo systemctl restart rmirror
sudo journalctl -u rmirror -f  # Watch for startup messages
```

### Can't see files in Backblaze dashboard

**Check:**
- Files are uploaded to correct bucket
- Using "Browse Files" not "Upload/Download"
- Folder structure: `users/[user-id]/notebooks/[uuid]/pages/[uuid].rm`

**Fix:** Use B2 CLI to list files:
```bash
b2 ls --recursive b2://rmirror-user-data/
```

## Cost Estimation

Backblaze B2 pricing (as of 2024):
- **Storage:** $0.005/GB/month (first 10 GB free)
- **Download:** $0.01/GB (first 1 GB/day free)
- **Upload:** Free
- **API calls:** Free

**Example costs:**
- 1,000 users with 50 MB each = 50 GB storage = **$0.20/month**
- 10,000 users with 100 MB each = 1 TB storage = **$5.00/month**
- Downloads mostly covered by 1 GB/day free tier

## Security Best Practices

1. ✅ **Use application keys, not master key**
2. ✅ **Restrict key to specific bucket**
3. ✅ **Store credentials in GitHub Secrets, never in code**
4. ✅ **Enable lifecycle rules to archive old data**
5. ✅ **Monitor bucket usage via Backblaze dashboard**

## Bucket Configuration Recommendations

### Lifecycle Rules
Set up rules to optimize costs:
- Archive pages older than 90 days to cheaper storage
- Delete notebooks marked as deleted after 30 days

### CORS Configuration (if needed for direct uploads)
```json
[
  {
    "corsRuleName": "downloadFiles",
    "allowedOrigins": [
      "https://rmirror.cloud",
      "https://app.rmirror.cloud"
    ],
    "allowedOperations": [
      "s3_get"
    ],
    "allowedHeaders": ["*"],
    "exposeHeaders": [],
    "maxAgeSeconds": 3600
  }
]
```

## Next Steps

After Backblaze B2 is set up for user data:
1. ✅ Files automatically stored in B2 instead of local disk
2. 📦 Set up separate bucket for installer downloads
3. 🌐 Configure CDN (Cloudflare) for `downloads.rmirror.io`
4. 🔄 Implement backup strategy (B2 snapshot or replication)

## Resources

- [Backblaze B2 Documentation](https://www.backblaze.com/b2/docs/)
- [S3-compatible API](https://www.backblaze.com/b2/docs/s3_compatible_api.html)
- [B2 CLI Guide](https://www.backblaze.com/b2/docs/quick_command_line.html)
- [boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
