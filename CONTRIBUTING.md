# CONTRIBUTING.md — Developer Contribution Guidelines

Thank you for contributing to the **Context Memory System**!

---

## Code of Conduct

All contributors are expected to adhere to team standards and maintain professional, respectful communication.

---

## Development Workflow

### 1. Branching Strategy
- Main branch: `main` (production-ready code).
- Feature branches: `feature/<feature-name>`
- Bugfix branches: `fix/<bug-name>`

### 2. Environment Setup
```bash
git clone https://github.com/Devopstrio/-context-memory.git
cd context-memory
python -m venv .venv
source .venv/bin/activate
make install-dev
```

### 3. Code Quality Standards
Prior to submitting a pull request, ensure all linters, type checkers, and tests pass:
```bash
# Format code
make format

# Run static analysis
make lint

# Execute unit and integration tests
make test
```

### Pull Request Guidelines
- Ensure all tests pass cleanly without errors or warnings.
- Maintain strict Mypy type annotations across all new Python functions and modules.
- Keep pull requests focused on a single logical change.
- Include clear commit messages following Conventional Commits (`feat:`, `fix:`, `docs:`, `ci:`).
