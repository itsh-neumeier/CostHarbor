# Contributing to CostHarbor

## Development Setup

1. Clone the repository
2. Copy `.env.example` to `.env` and configure
3. Run `docker-compose up -d db` to start PostgreSQL
4. Install dependencies: `pip install -e ".[dev]"`
5. Run migrations: `alembic upgrade head`
6. Start the app: `uvicorn app.main:app --reload`

## Code Standards

- Python 3.12+
- Linting: `ruff check .`
- Type checking: `mypy app/`
- Tests: `pytest`
- Follow existing code patterns and conventions

## Pull Requests

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all checks pass (`ruff`, `mypy`, `pytest`)
4. Update CHANGELOG.md if applicable
5. Submit a pull request with a clear description

## Versioning

This project uses [Semantic Versioning 2.0.0](https://semver.org/).
