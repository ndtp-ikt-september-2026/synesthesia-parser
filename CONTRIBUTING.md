# Contributing to Synesthesia Parser

Thank you for your interest in contributing to **Synesthesia Parser**! We welcome bug reports, feature suggestions, documentation improvements, and code contributions.

---

## Development Setup

1. **Prerequisites**:
   - Python 3.13 or newer
   - [uv](https://github.com/astral-sh/uv) (recommended) or standard `pip` / `venv`
   - [FFmpeg](https://ffmpeg.org/) (required for converting audio previews in the music pipeline)

2. **Clone & Install**:
   ```bash
   git clone https://github.com/your-username/synesthesia-parser.git
   cd synesthesia-parser

   # Install dependencies using uv
   uv sync

   # Or using standard venv:
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

3. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env and set your DISCOGS_TOKEN
   ```

---

## Running Tests

Before submitting changes, run the automated test suite to verify everything passes:

```bash
uv run python -m unittest discover -s tests -p "test_*.py"
```

To run optional live network tests (requires Internet connectivity):
```bash
RUN_LIVE_TESTS=1 uv run python -m unittest discover -s tests -p "test_*.py"
```

---

## Code Style & Guidelines

- Follow [PEP 8](https://peps.python.org/pep-0008/) naming and style guidelines.
- Use explicit type hints for public functions and dataclass/pydantic models.
- Ensure all new features are accompanied by corresponding unit tests in `tests/`.
- Never commit credentials, tokens, or personal access keys.

---

## Submitting Pull Requests

1. Fork the repository and create your branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Make your changes and commit with clear, descriptive commit messages.
3. Verify that all automated tests pass.
4. Push to your fork and submit a Pull Request against the `main` branch.
