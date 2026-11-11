# Nginx Configuration for rMirror Cloud

## Files

- `rmirror-production.conf` - **Current production config** (dashboard + API)
- `rmirror-combined.conf` - Old config (API only)
- `rmirror.conf` - Initial setup template

## Deploying Nginx Config Changes

### Option 1: Manual Deployment (Immediate)

```bash
# Copy config to server
scp backend/config/nginx/rmirror-production.conf deploy@<server-ip>:/tmp/

# SSH to server and apply
ssh deploy@<server-ip>
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

## Configuration Structure

### Current Routing

1. **Backend API** (FastAPI on port 8000)
   - `/api/*` → Backend
   - `/v1/*` → Backend

2. **Dashboard** (Next.js on port 3000)
   - All other routes → Dashboard

## Troubleshooting

### Changes not taking effect
- Test config: `sudo nginx -t`
- Reload nginx: `sudo systemctl reload nginx`
- Check which config is active: `sudo nginx -T | grep server_name`
