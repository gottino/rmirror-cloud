# Nginx Configuration for rMirror Cloud

## Files

- `rmirror-production.conf` - **Current production config** (dashboard + API + landing pages)
- `rmirror-combined.conf` - Old config (API only)
- `rmirror.conf` - Initial setup template

## Deploying Nginx Config Changes

### Option 1: Manual Deployment (Immediate)

```bash
# Copy config to server
scp backend/config/nginx/rmirror-production.conf deploy@167.235.74.51:/tmp/

# SSH to server and apply
ssh deploy@167.235.74.51
sudo cp /tmp/rmirror-production.conf /etc/nginx/sites-available/rmirror
sudo nginx -t  # Test configuration
sudo systemctl reload nginx  # Apply changes
```

### Option 2: Add to Deploy Script (Automated)

Add nginx config update to `backend/scripts/deploy.sh`:

```bash
# Update nginx configuration if changed
if [ -f "$ROOT_DIR/backend/config/nginx/rmirror-production.conf" ]; then
    echo -e "${YELLOW}Updating nginx configuration...${NC}"
    sudo cp "$ROOT_DIR/backend/config/nginx/rmirror-production.conf" /etc/nginx/sites-available/rmirror
    sudo nginx -t && sudo systemctl reload nginx
    echo -e "${GREEN}✅ Nginx configuration updated${NC}"
fi
```

## Recent Changes

### 2025-12-08: Added beta.html Support

**Change:** Added `beta.html` to static files regex pattern (line 51)

**Before:**
```nginx
location ~* ^/(index\.html|styles\.css|images/|.*\.(png|jpg|jpeg|gif|svg|ico))$ {
```

**After:**
```nginx
location ~* ^/(index\.html|beta\.html|styles\.css|images/|.*\.(png|jpg|jpeg|gif|svg|ico))$ {
```

**Why:** Beta landing page at `/beta.html` was being proxied to Next.js dashboard (404) instead of served as static HTML.

## Configuration Structure

### Current Routing

1. **Static Landing Pages** (`/var/www/rmirror-landing/`)
   - `/` → `index.html`
   - `/beta.html` → `beta.html`
   - `/agent` → `agent.html`
   - Images, CSS

2. **Backend API** (FastAPI on port 8000)
   - `/api/*` → Backend
   - `/v1/*` → Backend

3. **Dashboard** (Next.js on port 3000)
   - All other routes → Dashboard

### Landing Pages Location

**Note:** Landing pages are served from `/var/www/rmirror-landing/` (NOT `/var/www/rmirror-cloud/landing/`)

To update landing pages, copy to the correct location:
```bash
scp landing/beta.html deploy@167.235.74.51:/var/www/rmirror-landing/
```

Or update the deploy script to sync:
```bash
rsync -av landing/ /var/www/rmirror-landing/
```

## Troubleshooting

### beta.html returns 404
- Check nginx config has `beta\.html` in the static files pattern
- Verify file exists: `ls -la /var/www/rmirror-landing/beta.html`
- Check nginx error logs: `sudo tail -f /var/log/nginx/error.log`

### Changes not taking effect
- Test config: `sudo nginx -t`
- Reload nginx: `sudo systemctl reload nginx`
- Check which config is active: `sudo nginx -T | grep server_name`

### Landing pages show old content
- Files might be in `/var/www/rmirror-cloud/landing/` instead of `/var/www/rmirror-landing/`
- Copy to correct location or update nginx `root` directive
