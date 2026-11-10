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


def pytest_addoption(parser):
    parser.addoption("--sim-core", choices=("python", "rust", "auto"), default=None,
                     help="simulator core for the tests (default: RSX_SIM_CORE or auto)")


def pytest_configure(config):
    from redstone.sim import core

    choice = config.getoption("--sim-core")
    if choice:
        core.use(choice)


def pytest_report_header(config):
    from redstone.sim import core

    return f"simulator core: {core.active()}"
