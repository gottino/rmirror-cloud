# Commit Message Guidelines

## Security & Privacy

**Never include in commit messages:**
- ❌ IP addresses
- ❌ Domain names (unless public/example)
- ❌ Server names
- ❌ API keys or secrets
- ❌ Usernames or email addresses
- ❌ Database passwords
- ❌ File paths with personal information

**Use generic placeholders instead:**
- ✅ `production server` instead of specific IP
- ✅ `deployment target` instead of server name
- ✅ `configured endpoint` instead of actual URL

## Format

```
type: brief description (max 50 chars)

Optional longer description if needed.
Focus on WHAT changed and WHY, not personal details.
```

## Examples

**Bad:**
```
fix: update deploy script for 167.235.74.51
```

**Good:**
```
fix: update deployment scripts for production
```

**Bad:**
```
feat: add user john@example.com to database
```

**Good:**
```
feat: add user creation functionality
```
