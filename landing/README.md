# rMirror Landing Page

Simple waitlist landing page for rmirror.io

## Features

- Clean, responsive design inspired by best SaaS landing pages
- Email waitlist form with backend integration
- GitHub repository link
- Mobile-friendly

## Deployment

The landing page deploys automatically via GitHub Actions when changes are pushed to `main`:

```bash
git add landing/
git commit -m "update landing page"
git push origin main
```

## Local Testing

Open `index.html` in your browser:

```bash
cd landing
open index.html  # macOS
# or
python3 -m http.server 8080  # Then visit http://localhost:8080
```

## Nginx Configuration

The landing page is served from `/var/www/rmirror-landing/` on the server.

Create `/etc/nginx/sites-available/rmirror-landing`:

```nginx
server {
    listen 80;
    server_name rmirror.io www.rmirror.io;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name rmirror.io www.rmirror.io;

    ssl_certificate /etc/letsencrypt/live/rmirror.io/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rmirror.io/privkey.pem;

    # Landing page
    location / {
        root /var/www/rmirror-landing;
        index index.html;
        try_files $uri $uri/ =404;
    }

    # API proxy (backend)
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/rmirror-landing /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Backend Integration

The waitlist form submits to `/api/v1/waitlist` which is handled by the backend.

Ensure the backend migration has been run:

```bash
cd /var/www/rmirror-cloud/backend
alembic upgrade head
```

## Structure

```
landing/
├── index.html          # Main landing page (public)
├── beta.html          # Beta access page (hidden, not linked)
├── logo.png           # rMirror logo
└── README.md          # This file
```

## Beta Access Page

A hidden page at `https://rmirror.io/beta` for beta testers:
- Not linked from the main landing page
- Not indexed by search engines (`noindex` meta tag)
- Shows placeholder for login functionality
- Will be updated with Clerk authentication UI once configured

Access: Share the `/beta` URL directly with beta testers.

## Future Enhancements

See comments in `index.html` for the full-featured landing page concept that includes:
- Feature showcase with screenshots
- Pricing tiers
- Integration showcase
- Testimonials
- FAQ section
- Demo video
