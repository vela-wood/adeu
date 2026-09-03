import importlib.metadata as metadata
import importlib.util
import sys

FORBIDDEN_DISTRIBUTIONS = ("fastmcp", "fastmcp-slim", "langchain", "langchain-core")


def test_forbidden_frameworks_are_not_installed_or_importable():
    for name in FORBIDDEN_DISTRIBUTIONS:
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            version = None
        assert version is None, f"{name} must not be installed in the slim environment"
        assert importlib.util.find_spec(name.replace("-", "_")) is None


def test_cli_import_does_not_load_forbidden_frameworks():
    import adeu.cli  # noqa: F401

    assert "fastmcp" not in sys.modules
    assert "langchain" not in sys.modules
