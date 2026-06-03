import tomllib
from pathlib import Path


def test_package_imports():
    import print_concierge

    assert print_concierge.__version__


def test_mcp_console_script_is_declared():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    assert (
        pyproject["project"]["scripts"]["print-concierge-mcp"]
        == "print_concierge.interfaces.mcp_server:main"
    )
