"""Root conftest: the --sim-core option must be registered here to work without an explicit test path."""


def pytest_addoption(parser):
    parser.addoption("--sim-core", choices=("python", "rust", "auto"), default=None,
                     help="simulator core for the tests (default: RSX_SIM_CORE or auto)")
    parser.addoption("--slow", action="store_true", help="also run tests marked slow (long design searches)")


def pytest_configure(config):
    from redstone.sim import core

    choice = config.getoption("--sim-core")
    if choice:
        core.use(choice)


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    import pytest

    skip = pytest.mark.skip(reason="slow (run with --slow)")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


def pytest_report_header(config):
    from redstone.sim import core

    return f"simulator core: {core.active()}"
