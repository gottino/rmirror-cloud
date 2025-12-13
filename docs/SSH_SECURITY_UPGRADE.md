# SSH Security Upgrade Guide

This guide will help you strengthen SSH security by:
1. Increasing fail2ban ban times to 1 week
2. Moving SSH from port 22 to port 2222

## Prerequisites

- Access to the server via SSH
- Sudo password ready
- GitHub access to update secrets

## Step-by-Step Instructions

### Phase 1: Strengthen fail2ban (Low Risk)

1. **SSH into the server:**
   ```bash
   ssh -p 22 deploy@167.235.74.51
   ```

2. **Run the fail2ban update script:**
   ```bash
   /tmp/update_fail2ban.sh
   ```

   This will:
   - Backup current config
   - Increase ban time from 24 hours to 1 week
   - Decrease find time from 10 minutes to 5 minutes
   - Reload fail2ban

3. **Verify fail2ban is working:**
   ```bash
   sudo fail2ban-client status sshd
   ```

### Phase 2: Change SSH Port (Requires Care)

**⚠️ IMPORTANT:** Follow these steps carefully to avoid getting locked out!

1. **Make sure you're still connected to the server from Phase 1**
   - Keep this terminal window open throughout the process

2. **Run the SSH port change script:**
   ```bash
   /tmp/change_ssh_port.sh
   ```

   This will:
   - Backup SSH config
   - Change SSH port to 2222 in `/etc/ssh/sshd_config`
   - Update fail2ban to monitor port 2222
   - Add firewall rule for port 2222
   - Test the SSH configuration

3. **Restart SSH service:**
   ```bash
   sudo systemctl restart sshd
   ```

4. **Test the new port (open a NEW terminal window):**
   ```bash
   ssh -p 2222 deploy@167.235.74.51
   ```

   ✅ If this works, continue to step 5
   ❌ If this fails, use your ORIGINAL terminal (still on port 22) to debug

5. **Reload fail2ban (in the NEW terminal on port 2222):**
   ```bash
   sudo fail2ban-client reload
   sudo fail2ban-client status sshd
   ```

   Verify it shows: `port = 2222`

6. **Optional: Remove old SSH port from firewall**

   After confirming everything works on port 2222:
   ```bash
   sudo ufw delete allow 22/tcp
   sudo ufw status
   ```

### Phase 3: Update GitHub Secrets

1. **Go to GitHub repository secrets:**
   https://github.com/gabrieleottino/rmirror-cloud/settings/secrets/actions

2. **Update the `SERVER_PORT` secret:**
   - Click on `SERVER_PORT`
   - Change value from `22` to `2222`
   - Click "Update secret"

3. **Verify deployment workflows will use new port:**
   - The workflows already reference `${{ secrets.SERVER_PORT }}`
   - No code changes needed
   - Next deployment will automatically use port 2222

## Verification

After completing all phases:

1. **Test SSH connection:**
   ```bash
   ssh -p 2222 deploy@167.235.74.51
   ```

2. **Check fail2ban status:**
   ```bash
   sudo fail2ban-client status sshd
   ```

   Should show:
   - `port = 2222`
   - `bantime = 604800` (1 week in seconds)
   - `findtime = 300` (5 minutes in seconds)
   - `maxretry = 3`

3. **Test deployment (optional):**
   - Make a small change to the repo
   - Push to trigger deployment
   - Verify GitHub Actions can still connect

## Rollback Procedure

If something goes wrong:

### Rollback SSH Port:
```bash
# Restore SSH config backup
sudo cp /etc/ssh/sshd_config.backup.YYYYMMDD-HHMMSS /etc/ssh/sshd_config
sudo systemctl restart sshd

# Restore fail2ban config backup
sudo cp /etc/fail2ban/jail.local.backup.YYYYMMDD-HHMMSS /etc/fail2ban/jail.local
sudo fail2ban-client reload
```

### Rollback GitHub Secret:
- Change `SERVER_PORT` back to `22`

## Expected Security Improvements

### Before:
- SSH on standard port 22 (heavily targeted by bots)
- Ban attackers for 24 hours
- ~500+ attack attempts per day

### After:
- SSH on port 2222 (90% reduction in automated attacks)
- Ban attackers for 1 week (7x longer)
- Expected: ~10-50 attack attempts per day
- Attackers who find the port get banned much longer

## Files Modified

- `/etc/ssh/sshd_config` - SSH daemon configuration
- `/etc/fail2ban/jail.local` - fail2ban rules
- UFW firewall rules - New rule for port 2222

## Support

If you get locked out:
1. Access server via hosting provider's console/VNC
2. Restore backups created by the scripts
3. Restart services

Scripts are located at:
- `/tmp/update_fail2ban.sh`
- `/tmp/change_ssh_port.sh`
