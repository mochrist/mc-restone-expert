from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
LICENSED = FIXTURES / "licensed"
EXTERNAL = FIXTURES / "external"


def external(name: str) -> Path:
    path = EXTERNAL / name
    if not path.exists():
        pytest.skip(f"{name} missing, run: uv run python scripts/fetch_external_fixtures.py")
    return path
