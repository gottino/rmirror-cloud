# Contributing to rMirror Cloud

Thank you for your interest in contributing! We welcome contributions from everyone.

## Code of Conduct

Be respectful, inclusive, and professional. We're all here to build something great together.

## Ways to Contribute

### 🐛 Report Bugs
Found a bug? [Open an issue](https://github.com/gottino/rmirror-cloud/issues/new?template=bug_report.md) with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Your environment (OS, versions)

### 💡 Suggest Features
Have an idea? [Start a discussion](https://github.com/gottino/rmirror-cloud/discussions/new?category=ideas) first to gauge interest before building.

### 📝 Improve Documentation
Documentation PRs are always welcome! Look for typos, unclear sections, or missing guides.

### 🔌 Add Connectors
Want to integrate a new service? Check out [docs/connectors.md](docs/connectors.md) for the connector interface.

### 🧪 Write Tests
Improving test coverage is hugely valuable. See the `tests/` directories in each component.

### 🎨 Design & UX
Design skills? Help improve the dashboard UI/UX. Share mockups in discussions first.

## Development Setup

### Prerequisites
- **For Backend:** Python 3.11+, Poetry
- **For Agent:** Rust 1.70+, Node.js 18+
- **For Dashboard:** Node.js 18+
- **For All:** Docker & Docker Compose

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/gottino/rmirror-cloud
   cd rmirror-cloud
   ```

2. **Set up environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Claude API key
   ```

3. **Start infrastructure**
   ```bash
   docker-compose up -d postgres redis minio
   ```

4. **Backend development**
   ```bash
   cd backend
   poetry install
   poetry run alembic upgrade head  # Run migrations
   poetry run uvicorn app.main:app --reload
   ```

5. **Dashboard development**
   ```bash
   cd dashboard
   npm install
   npm run dev
   ```

6. **Agent development**
   ```bash
   cd agent
   npm install
   npm run tauri dev
   ```

### Running Tests

```bash
# Backend tests
cd backend
poetry run pytest

# Dashboard tests
cd dashboard
npm test

# Agent tests
cd agent
npm test
cargo test
```

## Code Style

### Python (Backend)
- **Style:** Follow PEP 8, use Black formatter
- **Type hints:** Required for all functions
- **Docstrings:** Use Google style
- **Imports:** Sort with isort

```python
def process_page(page_id: str, user_id: str) -> dict:
    """Process a single page with OCR.

    Args:
        page_id: UUID of the page to process
        user_id: UUID of the user who owns the page

    Returns:
        Dictionary containing OCR results

    Raises:
        PageNotFoundError: If page doesn't exist
        QuotaExceededError: If user exceeded limits
    """
    pass
```

### TypeScript (Dashboard & Agent)
- **Style:** Prettier with default config
- **Linting:** ESLint
- **Types:** Avoid `any`, use proper types

```typescript
interface PageResult {
  id: string;
  text: string;
  confidence: number;
}

async function processPage(pageId: string): Promise<PageResult> {
  // Implementation
}
```

### Rust (Agent)
- **Style:** rustfmt with default config
- **Linting:** clippy

```rust
pub async fn upload_file(path: PathBuf, api_key: &str) -> Result<UploadResponse, Error> {
    // Implementation
}
```

## Pull Request Process

1. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write tests for new functionality
   - Update documentation if needed
   - Follow code style guidelines

3. **Test thoroughly**
   ```bash
   # Run all tests
   ./scripts/test-all.sh
   ```

4. **Commit with clear messages**
   ```
   feat: add PDF export functionality

   - Implemented PDF generation
   - Added export API endpoint
   - Updated dashboard UI with export button

   Closes #123
   ```

   **Commit types:**
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation changes
   - `test:` Test additions/changes
   - `refactor:` Code refactoring
   - `perf:` Performance improvements
   - `chore:` Build/tooling changes

5. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

   Open a PR with:
   - Clear title and description
   - Link to related issues
   - Screenshots/videos if UI changes
   - Notes about testing done

6. **Address review feedback**
   - Be responsive to reviewers
   - Make requested changes
   - Ask questions if unclear

## Architecture Guidelines

### Backend
- **Async first:** Use `async/await` for all I/O
- **Type safety:** Pydantic models for all data
- **Error handling:** Use custom exceptions, never catch-all
- **Database:** Use SQLAlchemy async, always use transactions
- **Testing:** Unit tests for services, integration tests for endpoints

### Agent
- **Cross-platform:** Test on Mac, Windows, Linux
- **Resource efficient:** < 100MB RAM, < 5% CPU
- **Offline resilient:** Queue operations when offline
- **Security:** Never log sensitive data
- **Testing:** Mock file system and network

### Dashboard
- **Performance:** Code-split routes, lazy load components
- **Accessibility:** Semantic HTML, ARIA labels, keyboard navigation
- **Responsive:** Mobile-first design
- **State:** React Query for server state, Zustand for client state
- **Testing:** React Testing Library, Playwright for E2E

## Database Migrations

Always create migrations for schema changes:

```bash
cd backend
poetry run alembic revision --autogenerate -m "add highlights table"
poetry run alembic upgrade head
```

## Security

### Reporting Vulnerabilities
**Do not** open public issues for security vulnerabilities. Email security@rmirror.io with:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We'll respond within 48 hours.

### Security Best Practices
- Never commit secrets or API keys
- Always encrypt sensitive data
- Use parameterized queries (SQLAlchemy handles this)
- Validate all user input
- Implement rate limiting on API endpoints
- Use HTTPS everywhere in production

## Community

- **Discord:** [Join our server](https://discord.gg/rmirror)
- **Discussions:** [GitHub Discussions](https://github.com/gottino/rmirror-cloud/discussions)
- **Twitter:** [@rmirror_cloud](https://twitter.com/rmirror_cloud)

## Questions?

Don't hesitate to ask! Open a discussion or ping in Discord. We're here to help.

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 license.
