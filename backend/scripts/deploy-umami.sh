#!/bin/bash
# Deploy Umami analytics to Hetzner VPS
#
# Usage: Run as root on the server
#   scp scripts/deploy-umami.sh deploy@167.235.74.51:/tmp/
#   ssh deploy@167.235.74.51
#   sudo bash /tmp/deploy-umami.sh
#
# After running:
# 1. Run: sudo certbot --nginx -d analytics.rmirror.io
# 2. Visit https://analytics.rmirror.io
# 3. Log in with default credentials: admin / umami
# 4. Change admin password immediately
# 5. Add website "rmirror.io", copy the website-id UUID
# 6. Add GitHub Actions secrets:
#    NEXT_PUBLIC_UMAMI_URL=https://analytics.rmirror.io
#    NEXT_PUBLIC_UMAMI_WEBSITE_ID=<uuid>
#    STAGING_UMAMI_WEBSITE_ID=<uuid>

set -euo pipefail

# ── Check running as root ──────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
  echo "Error: Run this script as root (sudo bash $0)"
  exit 1
fi

# ── Helper: run command as deploy user with NVM loaded ────────────
run_as_deploy() {
  sudo -u deploy bash -lc "source ~/.nvm/nvm.sh && $*"
}

run_as_deploy "node --version && npm --version && pm2 --version"

# ── Step 1: PostgreSQL database ───────────────────────────────────
echo ""
echo "=== Step 1: Create PostgreSQL database ==="

UMAMI_PW=$(openssl rand -base64 24 | tr -d '/+=')

if sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='umami'" | grep -q 1; then
  echo "User 'umami' already exists, updating password..."
  sudo -u postgres psql -c "ALTER USER umami WITH PASSWORD '$UMAMI_PW';"
else
  echo "Creating user 'umami'..."
  sudo -u postgres psql -c "CREATE USER umami WITH PASSWORD '$UMAMI_PW';"
fi

if sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='umami'" | grep -q 1; then
  echo "Database 'umami' already exists."
else
  echo "Creating database 'umami'..."
  sudo -u postgres psql -c "CREATE DATABASE umami OWNER umami;"
fi

DATABASE_URL="postgresql://umami:${UMAMI_PW}@localhost:5432/umami"
echo "Database URL saved for .env"

# ── Step 2: Clone Umami ──────────────────────────────────────────
echo ""
echo "=== Step 2: Install Umami ==="

if [ ! -d /var/www/umami ]; then
  git clone https://github.com/umami-software/umami.git /var/www/umami
  chown -R deploy:deploy /var/www/umami
  echo "Cloned to /var/www/umami"
else
  echo "/var/www/umami already exists, pulling latest..."
  cd /var/www/umami
  run_as_deploy "cd /var/www/umami && git pull"
fi

# ── Step 3: Configure .env ────────────────────────────────────────
echo ""
echo "=== Step 3: Configure .env ==="

cat > /var/www/umami/.env << EOF
DATABASE_URL=${DATABASE_URL}
EOF
chown deploy:deploy /var/www/umami/.env
chmod 600 /var/www/umami/.env
echo ".env written with database credentials"

# ── Step 4: Build ─────────────────────────────────────────────────
echo ""
echo "=== Step 4: Build Umami ==="

cd /var/www/umami
run_as_deploy "cd /var/www/umami && npm install --legacy-peer-deps"
run_as_deploy "cd /var/www/umami && npm install prop-types --legacy-peer-deps"
run_as_deploy "cd /var/www/umami && npm run build"

# ── Step 5: Start with PM2 ───────────────────────────────────────
echo ""
echo "=== Step 5: Start with PM2 ==="

run_as_deploy "pm2 delete umami 2>/dev/null || true"
run_as_deploy "cd /var/www/umami && pm2 start npm --name umami -- start -- -p 3200"
run_as_deploy "pm2 save"
echo "Umami running on port 3200"

# ── Step 6: Nginx reverse proxy ──────────────────────────────────
echo ""
echo "=== Step 6: Configure Nginx ==="

cat > /etc/nginx/sites-available/umami << 'NGINX'
server {
    listen 80;
    server_name analytics.rmirror.io;

    location / {
        proxy_pass http://127.0.0.1:3200;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/umami /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
echo "Nginx configured for analytics.rmirror.io"

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "========================================="
echo "  Umami deployment complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. sudo certbot --nginx -d analytics.rmirror.io"
echo "  2. Visit https://analytics.rmirror.io"
echo "  3. Log in: admin / umami"
echo "  4. Change admin password"
echo "  5. Add website 'rmirror.io' → copy website-id UUID"
echo "  6. Add GitHub Actions secrets:"
echo "     NEXT_PUBLIC_UMAMI_URL=https://analytics.rmirror.io"
echo "     NEXT_PUBLIC_UMAMI_WEBSITE_ID=<uuid>"
echo "     STAGING_UMAMI_WEBSITE_ID=<uuid>"
