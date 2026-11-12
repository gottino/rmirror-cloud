# GitHub Actions Deployment Guide

This guide walks you through setting up automated deployment to your Hetzner production server using GitHub Actions.

> **Current setup:** the repository ships two workflows instead of the single `deploy.yml` shown below. `deploy-staging.yml` runs CI and deploys **staging** on every push to `main`; `deploy-production.yml` deploys **production** only when started by hand ("Run workflow"), after CI and a staging health check. Both build the dashboard in Actions (never on the server). The `deploy.yml` in Step 4 is a simplified example of the pattern, and its `push` trigger would deploy production on every push, which the project does not do.

## Overview

When a deployment runs (on push to `main` for staging, or a manual run for production), GitHub Actions will:
1. Connect to your Hetzner server via SSH
2. Check out the exact commit of the workflow run (production) and check the config
3. Install dependencies
4. Run database migrations
5. (no tests on the server; CI runs them before the deploy)
6. Restart the application
7. Perform health checks

## Prerequisites

- [x] GitHub repository with your code
- [x] Hetzner server with SSH access
- [x] `deploy` user on the server with sudo privileges
- [x] Deployment scripts in place (`backend/scripts/deploy.sh`)

## Step 1: Generate SSH Key for GitHub Actions

GitHub Actions needs to connect to your server via SSH. Generate a dedicated SSH key pair for this:

```bash
# On your local machine
ssh-keygen -t ed25519 -C "github-actions@rmirror" -f ~/.ssh/github_actions_rmirror

# This creates two files:
# - ~/.ssh/github_actions_rmirror (private key - keep secret!)
# - ~/.ssh/github_actions_rmirror.pub (public key)
```

**Important**: Use a strong passphrase or leave it empty for automated deployments.

## Step 2: Add Public Key to Server

Copy the **public key** to your server so GitHub Actions can authenticate:

```bash
# Copy public key to clipboard (macOS)
cat ~/.ssh/github_actions_rmirror.pub | pbcopy

# Or display it
cat ~/.ssh/github_actions_rmirror.pub
```

Then add it to your server's authorized_keys:

```bash
# SSH into your server
ssh deploy@<server-ip>

# Add the public key
echo "YOUR_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys

# Set correct permissions
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh

# Exit
exit
```

**Test the connection** from your local machine:

```bash
ssh -i ~/.ssh/github_actions_rmirror deploy@<server-ip> "echo 'Connection successful!'"
```

## Step 3: Store Secrets in GitHub

GitHub Actions needs your private SSH key and server details. Store them as **encrypted secrets**.

### 3.1 Navigate to Repository Settings

1. Go to your GitHub repository
2. Click **Settings** (top right)
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret**

### 3.2 Add the Following Secrets

Create these secrets one by one:

| Secret Name | Description | How to Get Value |
|-------------|-------------|------------------|
| `SSH_PRIVATE_KEY` | GitHub Actions SSH key | `cat ~/.ssh/github_actions_rmirror` |
| `SERVER_HOST` | Production server IP | Your Hetzner IP (e.g., `<server-ip>`) |
| `SERVER_USER` | SSH user for deployment | `deploy` |
| `SERVER_PORT` | SSH port | `22` (default) |

**Adding SSH_PRIVATE_KEY:**

```bash
# Display private key (macOS/Linux)
cat ~/.ssh/github_actions_rmirror

# Copy the ENTIRE output including:
# -----BEGIN OPENSSH PRIVATE KEY-----
# ...key content...
# -----END OPENSSH PRIVATE KEY-----
```

Paste this into GitHub as the `SSH_PRIVATE_KEY` secret.

**Security Notes:**
- ✅ Never commit private keys to git
- ✅ GitHub encrypts all secrets
- ✅ Secrets are only accessible in GitHub Actions workflows
- ✅ Use dedicated keys for CI/CD (easier to rotate)

## Step 4: Create GitHub Actions Workflow

Create the workflow file that defines your deployment pipeline:

```bash
# On your local machine, in the project root
mkdir -p .github/workflows
```

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  # Trigger on push to main branch
  push:
    branches:
      - main
    paths:
      - 'backend/**'
      - '.github/workflows/deploy.yml'

  # Allow manual deployment from GitHub UI
  workflow_dispatch:
    inputs:
      branch:
        description: 'Branch to deploy'
        required: false
        default: 'main'

jobs:
  deploy:
    name: Deploy to Hetzner
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup SSH
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/deploy_key
          chmod 600 ~/.ssh/deploy_key

          # Add server to known_hosts to avoid prompt
          ssh-keyscan -p ${{ secrets.SERVER_PORT }} ${{ secrets.SERVER_HOST }} >> ~/.ssh/known_hosts

      - name: Deploy to server
        env:
          SERVER_HOST: ${{ secrets.SERVER_HOST }}
          SERVER_USER: ${{ secrets.SERVER_USER }}
          SERVER_PORT: ${{ secrets.SERVER_PORT }}
          BRANCH: ${{ github.event.inputs.branch || 'main' }}
        run: |
          ssh -i ~/.ssh/deploy_key \
              -p $SERVER_PORT \
              $SERVER_USER@$SERVER_HOST \
              "cd /var/www/rmirror-cloud && ./backend/scripts/deploy.sh $BRANCH"

      - name: Check deployment status
        if: success()
        run: |
          echo "✅ Deployment successful!"
          echo "🔍 Check status: ssh ${{ secrets.SERVER_USER }}@${{ secrets.SERVER_HOST }} 'sudo systemctl status rmirror'"

      - name: Deployment failed
        if: failure()
        run: |
          echo "❌ Deployment failed! Check the logs above."
          echo "📊 Server logs: ssh ${{ secrets.SERVER_USER }}@${{ secrets.SERVER_HOST }} 'sudo journalctl -u rmirror -n 50'"

      - name: Cleanup
        if: always()
        run: |
          rm -f ~/.ssh/deploy_key
```

## Step 5: Commit and Push Workflow

```bash
# Add the workflow file
git add .github/workflows/deploy.yml

# Commit (following your commit guidelines - no personal info!)
git commit -m "feat: add GitHub Actions deployment workflow

Automated deployment pipeline for production server.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

# Push to GitHub
git push origin main
```

## Step 6: Monitor First Deployment

### 6.1 Watch the Workflow Run

1. Go to your GitHub repository
2. Click the **Actions** tab
3. You should see "Deploy to Production" running
4. Click on the workflow run to see live logs

### 6.2 Workflow Stages

The deployment will go through these stages:
1. ✅ **Checkout code**: Clone your repository
2. ✅ **Setup SSH**: Configure SSH authentication
3. ✅ **Deploy to server**: Run deployment script on server
4. ✅ **Check deployment status**: Verify success

### 6.3 What Happens on the Server

The `deploy.sh` script will:
1. Check the config of the commit it was given (`deploy.sh <sha>`; aborts before any change if a required setting is missing)
2. Backup database
3. Check out that commit (detached)
4. Install dependencies (poetry)
5. Run database migrations (alembic)
6. Restart application (systemd)
7. Health check (polls /health for up to 60s); on failure it checks the previous commit out again and restarts it (migrations are not undone)

## Step 7: Manual Deployment (Optional)

You can also trigger deployments manually:

1. Go to **Actions** tab on GitHub
2. Select "Deploy to Production" workflow
3. Click **Run workflow** button
4. Choose branch (default: main)
5. Click **Run workflow**

## Troubleshooting

### SSH Connection Issues

**Problem**: `Permission denied (publickey)`

**Solution**:
```bash
# Verify public key is on server
ssh deploy@<server-ip> "cat ~/.ssh/authorized_keys"

# Test SSH key locally
ssh -i ~/.ssh/github_actions_rmirror deploy@<server-ip> "echo 'Test'"
```

### Secret Not Found

**Problem**: `Error: Secret SSH_PRIVATE_KEY not found`

**Solution**:
- Go to **Settings** → **Secrets and variables** → **Actions**
- Verify all secrets are created with exact names (case-sensitive)
- Re-create the secret if needed

### Deployment Script Fails

**Problem**: Tests fail, migrations fail, or service won't start

**Solution**:
```bash
# SSH into server manually
ssh deploy@<server-ip>

# Check what went wrong
cd /var/www/rmirror-cloud/backend
sudo journalctl -u rmirror -n 100

# Check recent deployments
ls -lah /var/backups/rmirror/
```

### Workflow Doesn't Trigger

**Problem**: Pushed to main but workflow didn't run

**Solutions**:
- Check if you modified files in `backend/**` (workflow filters by path)
- Go to **Actions** tab and check if workflows are enabled
- Check **Settings** → **Actions** → **General** - ensure workflows are allowed

### Known Hosts Error

**Problem**: `Host key verification failed`

**Solution**: The workflow includes `ssh-keyscan` to automatically trust your server. If it still fails:
```yaml
# Add to deploy step in workflow:
run: |
  ssh -i ~/.ssh/deploy_key \
      -o StrictHostKeyChecking=no \  # Skip host verification
      -p $SERVER_PORT \
      $SERVER_USER@$SERVER_HOST \
      "cd /var/www/rmirror-cloud && ./backend/scripts/deploy.sh"
```

## Advanced: Deploy to Staging First

For safer deployments, add a staging environment:

```yaml
# .github/workflows/deploy-staging.yml
name: Deploy to Staging

on:
  push:
    branches:
      - develop

jobs:
  deploy:
    # ... same as production but with different secrets:
    # STAGING_SSH_PRIVATE_KEY
    # STAGING_SERVER_HOST
    # STAGING_SERVER_USER
```

## Advanced: Deployment Notifications

Get notified when deployments complete:

```yaml
# Add to deploy.yml after deployment step
- name: Notify deployment success
  if: success()
  run: |
    # Add Slack, Discord, or email notification here
    echo "Deployment successful!"

- name: Notify deployment failure
  if: failure()
  run: |
    echo "Deployment failed! Check logs."
```

## Security Best Practices

1. ✅ **Use dedicated SSH keys** for GitHub Actions (not your personal key)
2. ✅ **Limit key permissions** - deploy user should have minimal privileges
3. ✅ **Rotate keys regularly** - update keys every 90 days
4. ✅ **Use branch protection** - require PR reviews before merging to main
5. ✅ **Monitor deployments** - check GitHub Actions logs regularly
6. ✅ **Never commit secrets** - always use GitHub Secrets

## Monitoring Deployments

### View Recent Deployments

```bash
# On GitHub
Actions tab → Deploy to Production → Click any run

# On server
ssh deploy@<server-ip> "sudo journalctl -u rmirror -n 50"
```

### Rollback a Deployment

If a deployment breaks something:

```bash
# SSH to server
ssh deploy@<server-ip>

cd /var/www/rmirror-cloud/backend

# Find the previous working commit
git log --oneline -n 10

# Rollback to that commit
git checkout <commit-hash>
./scripts/deploy.sh

# Or restore database backup
ls -lah /var/backups/rmirror/
```

## Next Steps

- [ ] Test the deployment workflow with a small change
- [ ] Set up branch protection rules on GitHub
- [ ] Configure deployment notifications
- [ ] Create a staging environment
- [ ] Document rollback procedures
- [ ] Set up monitoring/alerting for production

## Questions?

If something doesn't work:
1. Check GitHub Actions logs (Actions tab)
2. Check server logs (`ssh deploy@<server-ip> 'sudo journalctl -u rmirror -n 100'`)
3. Verify all secrets are set correctly
4. Test SSH connection manually

---

**Happy deploying!** 🚀
