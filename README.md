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
│  Desktop Agent  │  ← Tauri app (Rust + React)
│  Watches folder │     10MB installer, cross-platform
└────────┬────────┘
         │ HTTPS
         ↓
┌─────────────────────────────────────┐
│       Cloud Infrastructure          │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │  FastAPI     │  │ PostgreSQL  │ │
│  │  Backend     │  │ Database    │ │
│  └──────┬───────┘  └─────────────┘ │
│         │                           │
│  ┌──────▼───────┐  ┌─────────────┐ │
│  │ OCR Workers  │  │  Redis      │ │
│  │ Claude API   │  │  Queue      │ │
│  └──────────────┘  └─────────────┘ │
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
- **Agent** (`agent/`) - Tauri desktop app for file watching and upload
- **Backend** (`backend/`) - FastAPI server with OCR workers
- **Dashboard** (`dashboard/`) - Next.js web interface
- **Infrastructure** (`infrastructure/`) - Docker, Kubernetes, Terraform configs

---

## 🛠️ Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Agent | Tauri 2.0 | Small (~10MB), cross-platform, native performance |
| Backend | FastAPI | Async Python, type-safe, auto-docs |
| Database | PostgreSQL 15 | Robust, JSON support, row-level security |
| Queue | Redis + RQ | Simple, Python-native, reliable |
| Storage | S3-compatible | Scalable object storage |
| Dashboard | Next.js 14 | SSR, great DX, Vercel deployment |
| Auth | Supabase Auth | Secure, managed OAuth |

---

## 🎯 Roadmap

**Phase 1: Foundation (Months 1-2)** ✅ In Progress
- [x] Repository setup
- [ ] Core API (upload, auth, jobs)
- [ ] OCR processing pipeline
- [ ] Basic web dashboard

**Phase 2: Agent (Months 2-3)**
- [ ] Tauri agent with file watching
- [ ] Cross-platform installers (Mac, Windows, Linux)
- [ ] Auto-update mechanism

**Phase 3: Connectors (Month 4)**
- [ ] Notion integration
- [ ] Readwise integration
- [ ] Generic webhook support

**Phase 4: Polish & Launch (Months 5-6)**
- [ ] Advanced search
- [ ] Usage analytics
- [ ] Performance optimization
- [ ] Public beta launch

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

- [Architecture Overview](docs/architecture.md)
- [Self-Hosting Guide](docs/self-hosting/)
- [API Reference](docs/api-reference.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)

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
- [Tauri](https://tauri.app) for the desktop agent
- [FastAPI](https://fastapi.tiangolo.com) for the backend
- [Next.js](https://nextjs.org) for the dashboard

Special thanks to the reMarkable community for inspiration and feedback.

---

## 📞 Support

**Self-hosting questions?** Check [docs/self-hosting](docs/self-hosting) or [Discussions](https://github.com/gottino/rmirror-cloud/discussions)

**Found a bug?** [Open an issue](https://github.com/gottino/rmirror-cloud/issues)

**Need enterprise support?** Email enterprise@rmirror.io

---

**Made with reMarkable 📝**
