# Deploying rMirror Cloud to Hetzner VPS

This guide covers deploying rMirror Cloud to a Hetzner VPS with PostgreSQL, without using Docker.

## Architecture Overview

```
┌─────────────────────────────────────────┐
│  Hetzner VPS (CX21: €5.83/month)        │
│  ├─ Nginx (reverse proxy + HTTPS)       │
│  ├─ FastAPI (systemd service)           │
│  ├─ PostgreSQL (local database)         │
│  └─ Redis (optional, for jobs)          │
└─────────────────────────────────────────┘
         │
         ├─ Backblaze B2 / Wasabi (S3 storage)
         └─ Claude API (OCR processing)
```

**Estimated costs:**
- VPS: €5.83/month (Hetzner CX21: 2 vCPU, 4GB RAM, 40GB SSD)
- Storage: ~€0.50/month (100GB @ Backblaze B2)
- **Total: ~€6-7/month**

---

## Prerequisites

- Hetzner Cloud account
- Domain name (optional, but recommended)
- SSH key for server access

---

## Step 1: Create Hetzner VPS

### 1.1 Create Server

1. Go to [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Create new project: "rmirror-cloud"
3. Add server:
   - **Location**: Nuremberg (Germany) or Falkenstein
   - **Image**: Ubuntu 24.04 LTS
   - **Type**: CX21 (2 vCPU, 4GB RAM, 40GB SSD)
   - **Networking**: Enable IPv4 + IPv6
   - **SSH Key**: Add your SSH public key
   - **Name**: rmirror-prod

4. Note the server IP address

### 1.2 Configure Firewall (Optional but Recommended)

Create firewall rules:
- **Inbound**:
  - SSH (port 22) - from your IP only
  - HTTP (port 80) - from anywhere
  - HTTPS (port 443) - from anywhere
- **Outbound**: Allow all

---

## Step 2: Initial Server Setup

### 2.1 Connect to Server

```bash
ssh root@YOUR_SERVER_IP
```

### 2.2 Create Deploy User

```bash
# Create user
adduser deploy
usermod -aG sudo deploy

# Copy SSH keys
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Test login (from your local machine)
ssh deploy@YOUR_SERVER_IP
```

### 2.3 Update System

```bash
sudo apt update && sudo apt upgrade -y
```

---

## Step 3: Install Dependencies

### 3.1 Install PostgreSQL

```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

### 3.2 Install Python 3.11+

```bash
sudo apt install -y python3.11 python3.11-venv python3-pip python3.11-dev
```

### 3.3 Install Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="/home/deploy/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 3.4 Install Nginx

```bash
sudo apt install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

### 3.5 Install System Dependencies (for .rm processing)

```bash
# For rmscene/rmc (PDF conversion)
sudo apt install -y librsvg2-bin

# For OCR dependencies
sudo apt install -y libmagic1
```

### 3.6 Install Redis (Optional - for background jobs)

```bash
sudo apt install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

---

## Step 4: Setup PostgreSQL Database

### 4.1 Create Database and User

```bash
sudo -u postgres psql << EOF
CREATE DATABASE rmirror;
CREATE USER rmirror WITH PASSWORD 'CHANGE_ME_SECURE_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE rmirror TO rmirror;
\c rmirror
GRANT ALL ON SCHEMA public TO rmirror;
EOF
```

### 4.2 Configure PostgreSQL for Local Connections

PostgreSQL should already allow local connections. Verify:

```bash
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

Ensure this line exists:
```
local   all             all                                     peer
host    all             all             127.0.0.1/32            scram-sha-256
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

---

## Step 5: Deploy Application

### 5.1 Create Application Directory

```bash
sudo mkdir -p /var/www/rmirror-cloud
sudo chown deploy:deploy /var/www/rmirror-cloud
cd /var/www/rmirror-cloud
```

### 5.2 Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/rmirror-cloud.git .
cd backend
```

### 5.3 Install Dependencies

```bash
poetry install --no-dev
```

### 5.4 Setup Environment Configuration

```bash
cp .env.production.template .env
nano .env
```

Fill in your production values:
```bash
# Database
POSTGRES_USER=rmirror
POSTGRES_PASSWORD=your_secure_password_from_step_4
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=rmirror

# Storage (Backblaze B2 or Wasabi)
S3_ENDPOINT_URL=https://s3.eu-central-003.backblazeb2.com
S3_ACCESS_KEY=your_b2_key
S3_SECRET_KEY=your_b2_secret
S3_BUCKET_NAME=rmirror-prod
S3_REGION=eu-central-003

# Claude API
CLAUDE_API_KEY=your_claude_api_key

# Auth (generate with: openssl rand -hex 32)
SECRET_KEY=your_generated_secret_key

# Application
DEBUG=false
```

### 5.5 Run Database Migrations

```bash
poetry run alembic upgrade head
```

### 5.6 Create Admin User (Optional)

```bash
# You can create a script or use the API after deployment
# Or create directly in PostgreSQL:
sudo -u postgres psql rmirror << EOF
INSERT INTO users (email, hashed_password, is_active, is_superuser, created_at, updated_at)
VALUES (
  'admin@example.com',
  '\$2b\$12\$YOUR_BCRYPT_HASHED_PASSWORD',
  true,
  true,
  NOW(),
  NOW()
);
EOF
```

---

## Step 6: Setup Systemd Service

### 6.1 Create Service File

```bash
sudo nano /etc/systemd/system/rmirror.service
```

Add:
```ini
[Unit]
Description=rMirror Cloud API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=notify
User=deploy
Group=deploy
WorkingDirectory=/var/www/rmirror-cloud/backend
Environment="PATH=/home/deploy/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/deploy/.local/bin/poetry run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2

# Restart policy
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rmirror

[Install]
WantedBy=multi-user.target
```

### 6.2 Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable rmirror
sudo systemctl start rmirror

# Check status
sudo systemctl status rmirror

# View logs
sudo journalctl -u rmirror -f
```

---

## Step 7: Configure Nginx

### 7.1 Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/rmirror
```

Add:
```nginx
# rMirror Cloud API - HTTP (will redirect to HTTPS after cert setup)
server {
    listen 80;
    listen [::]:80;
    server_name rmirror.yourdomain.com;  # Change this to your domain

    # For Let's Encrypt verification
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all other traffic to HTTPS (after cert is issued)
    # location / {
    #     return 301 https://$server_name$request_uri;
    # }

    # Temporary: proxy to app (remove after HTTPS setup)
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # For WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts for long OCR processing
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;

        # File upload size
        client_max_body_size 100M;
    }
}

# HTTPS configuration (uncomment after getting SSL certificate)
# server {
#     listen 443 ssl http2;
#     listen [::]:443 ssl http2;
#     server_name rmirror.yourdomain.com;
#
#     ssl_certificate /etc/letsencrypt/live/rmirror.yourdomain.com/fullchain.pem;
#     ssl_certificate_key /etc/letsencrypt/live/rmirror.yourdomain.com/privkey.pem;
#
#     # SSL configuration
#     ssl_protocols TLSv1.2 TLSv1.3;
#     ssl_ciphers HIGH:!aNULL:!MD5;
#     ssl_prefer_server_ciphers on;
#
#     location / {
#         proxy_pass http://127.0.0.1:8000;
#         proxy_set_header Host $host;
#         proxy_set_header X-Real-IP $remote_addr;
#         proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#         proxy_set_header X-Forwarded-Proto $scheme;
#
#         proxy_http_version 1.1;
#         proxy_set_header Upgrade $http_upgrade;
#         proxy_set_header Connection "upgrade";
#
#         proxy_connect_timeout 600s;
#         proxy_send_timeout 600s;
#         proxy_read_timeout 600s;
#
#         client_max_body_size 100M;
#     }
# }
```

### 7.2 Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/rmirror /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 8: Setup SSL with Let's Encrypt

### 8.1 Install Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 8.2 Obtain Certificate

```bash
sudo certbot --nginx -d rmirror.yourdomain.com
```

Follow prompts:
- Enter email for renewal notifications
- Agree to terms
- Choose to redirect HTTP to HTTPS

### 8.3 Auto-Renewal

Certbot automatically sets up renewal. Test it:

```bash
sudo certbot renew --dry-run
```

---

## Step 9: Setup S3 Storage

### 9.1 Create Backblaze B2 Account (Recommended)

1. Go to [Backblaze B2](https://www.backblaze.com/b2/cloud-storage.html)
2. Create account (first 10GB free)
3. Create bucket: "rmirror-prod" (private)
4. Create Application Key:
   - Go to "App Keys"
   - Create new key with read/write access
   - Save Key ID and Application Key
5. Update `.env` with credentials

### 9.2 Alternative: Wasabi

1. Go to [Wasabi](https://wasabi.com/)
2. Create account
3. Create bucket in eu-central-1
4. Get access keys
5. Update `.env`

---

## Step 10: Deployment Automation

### 10.1 Create Deploy Script

```bash
nano /var/www/rmirror-cloud/deploy.sh
```

Add:
```bash
#!/bin/bash
set -e

echo "🚀 Deploying rMirror Cloud..."

# Pull latest code
cd /var/www/rmirror-cloud
git pull origin main

# Install dependencies
cd backend
poetry install --no-dev

# Run migrations
poetry run alembic upgrade head

# Restart service
sudo systemctl restart rmirror

echo "✅ Deployment complete!"
echo "Check status: sudo systemctl status rmirror"
echo "View logs: sudo journalctl -u rmirror -f"
```

Make executable:
```bash
chmod +x /var/www/rmirror-cloud/deploy.sh
```

### 10.2 Deploy Updates

```bash
cd /var/www/rmirror-cloud
./deploy.sh
```

---

## Monitoring and Maintenance

### View Logs

```bash
# Application logs
sudo journalctl -u rmirror -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-16-main.log
```

### Database Backup

```bash
# Manual backup
sudo -u postgres pg_dump rmirror > backup_$(date +%Y%m%d).sql

# Automated daily backups (add to cron)
sudo crontab -e
```

Add:
```
0 2 * * * sudo -u postgres pg_dump rmirror | gzip > /var/backups/rmirror_$(date +\%Y\%m\%d).sql.gz
```

### Monitor Resource Usage

```bash
# CPU and memory
htop

# Disk space
df -h

# PostgreSQL connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check service status
sudo systemctl status rmirror

# View detailed logs
sudo journalctl -u rmirror -n 100 --no-pager

# Check if port 8000 is available
sudo netstat -tulpn | grep 8000

# Restart service
sudo systemctl restart rmirror
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
sudo -u postgres psql -c "\l"

# Check if PostgreSQL is running
sudo systemctl status postgresql

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### Nginx Issues

```bash
# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx

# Check logs
sudo tail -f /var/log/nginx/error.log
```

---

## Security Checklist

- [ ] Change default PostgreSQL password
- [ ] Generate secure SECRET_KEY
- [ ] Setup firewall (UFW or Hetzner Cloud Firewall)
- [ ] Disable root SSH login
- [ ] Setup fail2ban for SSH protection
- [ ] Keep system updated (unattended-upgrades)
- [ ] Setup monitoring (optional: Uptime Robot, Healthchecks.io)
- [ ] Regular database backups
- [ ] SSL certificate auto-renewal working

---

## Cost Breakdown

| Service | Cost | Notes |
|---------|------|-------|
| Hetzner VPS CX21 | €5.83/month | 2 vCPU, 4GB RAM, 40GB SSD |
| Backblaze B2 Storage (100GB) | ~€0.50/month | First 10GB free |
| Domain (optional) | ~€10/year | Any registrar |
| **Total** | **~€6-7/month** | Scales with storage usage |

---

## Next Steps

1. **Setup monitoring**: Add health check endpoint and use Uptime Robot (free)
2. **Add logging**: Consider Papertrail or Logtail for centralized logging
3. **Backup automation**: Setup automated backups to Hetzner Storage Box
4. **CI/CD**: Setup GitHub Actions for automated deployment
5. **Scaling**: Add Redis for background job processing when needed

---

## Support

For issues:
- Check application logs: `sudo journalctl -u rmirror -f`
- Check Nginx logs: `/var/log/nginx/error.log`
- Verify environment variables in `/var/www/rmirror-cloud/backend/.env`
- Test database connection: `poetry run python -c "from app.database import engine; engine.connect()"`
