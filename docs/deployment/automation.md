# Deployment Automation Guide

This guide covers the three ways to automate deployments to your production server after the initial setup.

> **Current setup:** a push to `main` deploys **staging** (`staging.rmirror.io`, `.github/workflows/deploy-staging.yml`). **Production** is deployed only by running the "Deploy to Production" workflow by hand (`deploy-production.yml`; it requires green CI and a healthy staging). Where this guide says that a push to `main` deploys production, read "deploys staging".

## Quick Reference

| Method | Trigger | Use Case | Setup Time |
|--------|---------|----------|------------|
| **GitHub Actions** | Push to `main` (staging); manual run (production) | Automated CI/CD | 5 min |
| **Remote Script** | Manual command | Quick manual deploys | 2 min |
| **Server Script** | SSH into server | On-server maintenance | 1 min |

---

## Method 1: GitHub Actions (Recommended)

**Automated deployment of staging on every push to `main`; production by running the workflow manually.**

### Setup (One-time)

#### 1. Add SSH Key to GitHub Secrets

Generate a deployment SSH key on your server:

```bash
# On your server
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/github_deploy  # Copy this (private key)
```

Add to GitHub:
1. Go to your repo → Settings → Secrets and variables → Actions
2. Add these secrets:
   - `SERVER_HOST`: Your server IP (e.g., `95.217.123.45`)
   - `SERVER_USER`: `deploy`
   - `SSH_PRIVATE_KEY`: The private key from above
   - `SERVER_PORT`: The SSH port

#### 2. Copy Deployment Script to Server

```bash
# On your server
cd /var/www/rmirror-cloud
cp backend/scripts/deploy.sh ./deploy.sh
chmod +x deploy.sh
```

#### 3. That's it!

Now every push to `main` automatically deploys to staging (production: run the "Deploy to Production" workflow):

```bash
# On your local machine
git add .
git commit -m "Add new feature"
git push origin main
# 🚀 Staging deployment starts!
```

Watch deployment progress:
- GitHub → Your Repo → Actions tab

### Manual Trigger

You can also trigger deployment manually:
1. Go to GitHub → Actions → "Deploy to Production"
2. Click "Run workflow"
3. Select branch → Run

---

## Method 2: Remote Deployment Script

**Trigger deployment from your local machine with one command.**

### Setup

1. Configure your server details:

```bash
# Add to your ~/.bashrc or ~/.zshrc
export RMIRROR_SERVER_HOST="95.217.123.45"  # Your server IP
export RMIRROR_SERVER_USER="deploy"
```

Or edit `backend/scripts/deploy-remote.sh` and replace `YOUR_SERVER_IP`.

### Usage

```bash
# Deploy main branch (default)
./backend/scripts/deploy-remote.sh

# Deploy specific branch
./backend/scripts/deploy-remote.sh develop
```

The script will:
1. ✅ Push local changes to git
2. ✅ SSH into server
3. ✅ Run deployment script
4. ✅ Show you the results

**Example output:**
```
========================================
🚀 Remote Deployment Trigger
========================================

📡 Server: deploy@95.217.123.45
🔀 Branch: main

Deploy to production? [y/N]: y

1/2 Pushing local changes to git...
   Pushing to origin/main...
✅ Git push complete

2/2 Triggering remote deployment...

========================================
🚀 rMirror Cloud Deployment
========================================

1/8 Creating database backup...
✅ Database backed up to: /var/backups/rmirror/rmirror_20250107_143022.sql.gz

2/8 Pulling latest code from git...
   Current commit: f14371a
   New commit: a1b2c3d
✅ Updated from f14371a to a1b2c3d

[...continues through all 8 steps...]

========================================
✅ Deployment Complete!
========================================
```

---

## Method 3: On-Server Deployment

**SSH into server and run deployment directly.**

### Usage

```bash
# SSH into your server
ssh deploy@YOUR_SERVER_IP

# Run deployment
cd /var/www/rmirror-cloud
./deploy.sh

# Or deploy a specific commit (must be on origin/main)
./backend/scripts/deploy.sh <commit-sha>
```

**Use this when:**
- Troubleshooting deployment issues
- Making configuration changes on server
- Running migrations manually

---

## What the Deployment Script Does

### 8-Step Deployment Process

1. **Check Config** - `scripts/check_config.py`; aborts before any change if a required setting is missing
2. **Database Backup** - Creates timestamped PostgreSQL backup
3. **Check Out Commit** - The given SHA (detached), or origin/main with a warning
4. **Install Dependencies** - Runs `poetry install`
5. **Run Migrations** - Applies database changes with Alembic
6. **Restart Service** - Restarts systemd service
7. **Health Check** - Polls /health for up to 60s; on failure the previous commit is restored and restarted
8. **Dashboard** - Installs the prebuilt dashboard (no tests run on the server; CI gates the workflow)

### Safety Features

- ✅ **Zero-downtime**: Service restart is fast (~2 seconds)
- ✅ **Automatic rollback**: Previous commit restored if migration, restart or health check fails (migrations are not undone)
- ✅ **Database backup**: Before every deployment
- ✅ **Health checks**: Fails if app doesn't start

---

## Rollback

If something goes wrong, rollback is simple:

### Option 1: Rollback via Script

```bash
# On server
cd /var/www/rmirror-cloud
git log --oneline -5  # Find commit to rollback to
./backend/scripts/deploy.sh COMMIT_HASH
```

### Option 2: Rollback Database Only

```bash
# Restore from backup
sudo -u postgres gunzip < /var/backups/rmirror/rmirror_TIMESTAMP.sql.gz | sudo -u postgres psql rmirror
sudo systemctl restart rmirror
```

### Option 3: Emergency Rollback (GitHub Actions)

1. Revert commit on GitHub
2. Push to main
3. Automatic deployment reverts changes

---

## Deployment Workflow Examples

### Daily Development Flow

```bash
# Make changes locally
vim app/api/something.py

# Test locally
poetry run pytest

# Commit and push
git add .
git commit -m "Add feature X"
git push origin main

# 🚀 GitHub Actions deploys staging; run "Deploy to Production" when staging is healthy
# Watch: https://github.com/YOUR_USERNAME/rmirror-cloud/actions
```

### Hotfix Flow

```bash
# Quick fix needed!
vim app/core/bug.py

# Use remote script for immediate deploy
./backend/scripts/deploy-remote.sh

# Done in 1-2 minutes!
```

### Maintenance Flow

```bash
# SSH into server
ssh deploy@YOUR_SERVER_IP

# Check logs
sudo journalctl -u rmirror -n 50

# Deploy manually
cd /var/www/rmirror-cloud
./deploy.sh

# Monitor
sudo journalctl -u rmirror -f
```

---

## Monitoring Deployments

### View Live Logs

```bash
# From local machine
ssh deploy@YOUR_SERVER_IP 'sudo journalctl -u rmirror -f'

# Or on server
sudo journalctl -u rmirror -f
```

### Check Service Status

```bash
sudo systemctl status rmirror
```

### Check Recent Deployments

```bash
cd /var/www/rmirror-cloud
git log --oneline -10
```

### Check Database Backups

```bash
ls -lh /var/backups/rmirror/
```

---

## Advanced Configuration

### Deployment Notifications

Add Slack/Discord notifications to GitHub Actions:

```yaml
# .github/workflows/deploy-production.yml
- name: Notify Slack
  if: always()
  uses: 8398a7/action-slack@v3
  with:
    status: ${{ job.status }}
    webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

### Deploy Specific Branch

```bash
# Deploy develop branch to staging
./backend/scripts/deploy-remote.sh develop
```

### Skip Tests in Emergency

`deploy.sh` no longer runs tests on the server; CI runs them before the deploy workflows.

### Custom Post-Deployment Tasks

Add custom steps to `deploy.sh`:

```bash
# After step 8, add:
echo -e "${YELLOW}9/9 Clearing cache...${NC}"
poetry run python -c "from app.cache import clear_all; clear_all()"
echo -e "${GREEN}✅ Cache cleared${NC}"
```

---

## Troubleshooting

### Deployment Fails at Step X

```bash
# SSH into server
ssh deploy@YOUR_SERVER_IP

# Check logs
sudo journalctl -u rmirror -n 100

# Try manual deployment with verbose output
cd /var/www/rmirror-cloud
bash -x ./deploy.sh 2>&1 | tee deploy.log
```

### GitHub Actions Fails

1. Check Actions tab for error logs
2. Verify secrets are set correctly:
   - Settings → Secrets → Actions
3. Test SSH connection manually:
   ```bash
   ssh -i ~/.ssh/your_key deploy@YOUR_SERVER_IP
   ```

### Service Won't Start After Deploy

```bash
# Check service status
sudo systemctl status rmirror

# Check config
cd /var/www/rmirror-cloud/backend
cat .env  # Verify environment variables

# Test app directly
poetry run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Database Migration Fails

```bash
# Check migration status
cd /var/www/rmirror-cloud/backend
poetry run alembic current
poetry run alembic history

# Try migration manually
poetry run alembic upgrade head

# Rollback one migration
poetry run alembic downgrade -1
```

---

## Best Practices

### 1. Always Test Locally First

```bash
# Run tests locally
poetry run pytest

# Test the migration
poetry run alembic upgrade head
```

### 2. Deploy During Low-Traffic Hours

- Schedule deployments for off-peak times
- Notify users of maintenance windows

### 3. Monitor After Deployment

```bash
# Watch logs for 5 minutes after deploy
ssh deploy@YOUR_SERVER_IP 'sudo journalctl -u rmirror -f'
```

### 4. Keep Backups

Database backups are automatic, but also backup:
- `.env` file (encrypted)
- S3 access keys (secure location)

### 5. Use Staging Environment (Optional)

```bash
# Deploy to staging first
./backend/scripts/deploy-remote.sh main staging.yourdomain.com

# Then deploy to production
./backend/scripts/deploy-remote.sh main yourdomain.com
```

---

## Summary

| Method | Command | When to Use |
|--------|---------|-------------|
| **Automatic (staging)** | `git push origin main` | Daily development |
| **Manual (local)** | `./backend/scripts/deploy-remote.sh` | Quick hotfixes |
| **Manual (server)** | `ssh deploy@server && cd /var/www/rmirror-cloud && ./deploy.sh` | Troubleshooting |

**Recommended workflow:**
1. Set up GitHub Actions for automatic deployments
2. Keep remote script for emergencies
3. SSH into server only when needed

🚀 Happy deploying!
