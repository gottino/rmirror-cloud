# rMirror Cloud

**Open source cloud service for reMarkable tablet integration.**

Mirror your reMarkable notes to the cloud with AI-powered handwriting recognition. Self-host or use our managed service.

---

## ✨ Features

- 🔄 **Automatic Sync** - Lightweight agent monitors your reMarkable and syncs to the cloud
- 🤖 **AI Handwriting Recognition** - Claude Vision OCR for superior accuracy
- 🔌 **Connect Everything** - Notion, Readwise, Obsidian, and more
- 🌐 **Access Anywhere** - Web dashboard to browse and search your notes
- 🔓 **Fully Open Source** - AGPL-3.0 licensed, audit the code yourself
- 🛡️ **Privacy First** - End-to-end encryption option, or self-host completely

---

## 🚀 Quick Start

### Option 1: Managed Cloud Service

Visit [rmirror.io](https://rmirror.io) to sign up.

**Free tier:** 100 pages/month
**Pro:** $10/month for unlimited processing

### Option 2: Self-Hosting (5 minutes)

**Requirements:** Docker & Docker Compose

```bash
git clone https://github.com/gottino/rmirror-cloud
cd rmirror-cloud
cp .env.example .env
# Edit .env with your Claude API key
docker-compose up -d
```

Visit `http://localhost:3000` to get started.

See [docs/self-hosting](docs/self-hosting) for detailed instructions.

---

## 📦 Architecture

```
┌─────────────────┐
│   Mac Agent     │  ← Python background service
│  (Background)   │     File watching + localhost web UI
└────────┬────────┘
         │ HTTPS
         ↓
┌─────────────────────────────────────┐
│       Cloud Backend                 │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │  FastAPI     │  │  SQLite/    │ │
│  │  REST API    │  │  PostgreSQL │ │
│  └──────┬───────┘  └─────────────┘ │
│         │                           │
│  ┌──────▼───────┐                  │
│  │ OCR Pipeline │                  │
│  │ Claude Vision│                  │
│  └──────────────┘                  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  Next.js Web Dashboard       │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
         │
         ↓
   External APIs
   (Notion, Readwise, etc.)
```

**Components:**
- **Agent** (`agent/`) - Python background service for Mac with localhost web UI
- **Backend** (`backend/`) - FastAPI server with OCR workers
- **Dashboard** (`dashboard/`) - Next.js web interface (planned)
- **Infrastructure** (`infrastructure/`) - Docker, deployment configs

---

## 🛠️ Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Agent | Python + Flask | Simple, lightweight, same stack as backend |
| Backend | FastAPI | Async Python, type-safe, auto-docs |
| Database | SQLite/PostgreSQL | Simple for dev, robust for production |
| OCR | Claude Vision API | Best-in-class handwriting recognition |
| Storage | S3-compatible (Backblaze B2) | Scalable, cost-effective object storage |
| Dashboard | Next.js 14 | SSR, great DX (planned) |
| Auth | JWT | Simple, stateless, secure |

---

## 🎯 Roadmap

**Core Backend**
- [x] Repository setup & project structure
- [x] FastAPI REST API with authentication (JWT)
- [x] User management & authorization
- [x] Notebook & page storage
- [x] Database migrations (Alembic)
- [x] Production deployment (Hetzner Cloud)
- [x] CI/CD with GitHub Actions

**OCR & Processing**
- [x] Claude Vision API integration
- [x] OCR processing pipeline
- [x] Handwriting recognition from reMarkable files

**Todo Management**
- [x] Intelligent todo extraction from checkboxes
- [x] Fuzzy matching deduplication
- [x] Todo CRUD API endpoints
- [x] Statistics and filtering
- [ ] Sync todos to Notion

**Integrations**
- [x] Notion sync with markdown formatting
- [x] OAuth integration framework
- [x] Background sync processing
- [ ] Readwise integration
- [ ] Obsidian sync
- [ ] Todo app integration (other than Notion)

**Documentation**
- [x] Comprehensive API reference
- [x] Deployment guides
- [x] Development setup documentation

**Mac Agent**
- [ ] Python background service
- [ ] File watching & automatic sync to cloud
- [ ] Web UI for configuration (localhost)
- [ ] System tray icon for status
- [ ] Signed & notarized macOS installer (.pkg)
- [ ] Auto-start on login

**Web Dashboard**
- [ ] Next.js web interface
- [ ] Integration configuration
- [ ] Notebook browsing & search

**Polish**
- [ ] Performance optimization
- [ ] End-to-end encryption option
- [ ] Multi-language support

**Launch**
- [ ] Public beta
- [ ] Managed cloud service
- [ ] Pricing & subscription tiers

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Areas needing help:**
- 🎨 UI/UX design for dashboard
- 🧪 Testing on Windows/Linux
- 📝 Documentation improvements
- 🔌 New connector integrations
- 🌍 Internationalization

---

## 📚 Documentation

- **[📖 Complete Documentation](docs/)** - Comprehensive project documentation
- **[Architecture Overview](docs/architecture.md)** - System design and components
- **[API Reference](docs/api/backend-api.md)** - Complete REST API documentation
- **[Development Setup](docs/development/setup.md)** - Get started with development
- **[Deployment Guide](docs/deployment/hetzner.md)** - Production deployment
- **[Contributing Guidelines](CONTRIBUTING.md)** - How to contribute

---

## 🔗 Related Projects

- **[remarkable-integration](https://github.com/gottino/remarkable-integration)** - Local CLI tool for advanced users
  - Perfect if you want full local control
  - Python-based, SQLite database
  - No cloud service required

**Which should you use?**
- **rMirror Cloud**: Easier setup, access from anywhere, web dashboard
- **remarkable-integration CLI**: Local control, no cloud dependency, scriptable

Both are open source. Both work great. Pick what fits your workflow!

---

## 💬 Community

- **Discord**: [Join our server](https://discord.gg/rmirror)
- **Discussions**: [GitHub Discussions](https://github.com/gottino/rmirror-cloud/discussions)
- **Issues**: [Report bugs](https://github.com/gottino/rmirror-cloud/issues)
- **Twitter**: [@rmirror_cloud](https://twitter.com/rmirror_cloud)

---

## 📄 License

**AGPL-3.0** - See [LICENSE](LICENSE)

This means:
- ✅ Free to use, modify, and self-host
- ✅ Commercial use allowed
- ⚠️ Must open source any modifications if you run a public service
- ⚠️ Cannot create closed-source competing cloud service

**Why AGPL?** Protects the open source nature while allowing self-hosting. Companies wanting private modifications can contact us about commercial licensing.

---

## 🙏 Acknowledgments

Built with ❤️ using:
- [Claude](https://anthropic.com) for AI-powered OCR
- [FastAPI](https://fastapi.tiangolo.com) for the backend
- [Python](https://python.org) for the Mac agent
- [Next.js](https://nextjs.org) for the web dashboard

Special thanks to the reMarkable community for inspiration and feedback.

---

## 📞 Support

**Self-hosting questions?** Check [docs/self-hosting](docs/self-hosting) or [Discussions](https://github.com/gottino/rmirror-cloud/discussions)

**Found a bug?** [Open an issue](https://github.com/gottino/rmirror-cloud/issues)

**Need enterprise support?** Email enterprise@rmirror.io

---

**Made with reMarkable 📝**
