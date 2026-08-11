import inspect
import io
import logging
import sys

import pytest
import structlog
from docx import Document

from adeu.utils.console import dynamic_stderr

# This fork deliberately excludes the Python MCP server and live-Word adapter
# from its distribution. Keep upstream's server tests in the tree for easier
# future merges, but do not collect them in the framework-free test environment.
collect_ignore = [
    "test_atomic_batch_pipeline.py",
    "test_changes_ledger.py",
    "test_cli_init.py",
    "test_doc_cache.py",
    "test_failure_envelope.py",
    "test_failure_recovery_protocol.py",
    "test_fastmcp4_compat.py",
    "test_flat_opc_to_docx.py",
    "test_live_word.py",
    "test_live_word_dispatch.py",
    "test_live_word_structured_insertion.py",
    "test_mcp_reasoning_optional.py",
    "test_page_ranges.py",
    "test_regressions.py",
    "test_report_minimal.py",
    "test_repro_accept_all_changes_leak.py",
    "test_repro_benchmark_schema_failures.py",
    "test_repro_customxml_missing_part.py",
    "test_repro_feedback_observations.py",
    "test_repro_qa_customer_assessment_2026_07_23.py",
    "test_repro_qa_mcp_2026_07_23_mcp.py",
    "test_repro_qa_mcp_2026_07_23_reports.py",
    "test_repro_qa_report_v2.py",
    "test_repro_qa_round3_2026_07_24.py",
    "test_repro_round16_bugs.py",
    "test_response_budget_guard.py",
    "test_search_paging.py",
    "test_search_write_engine.py",
    "test_server.py",
    "test_stringified_json_search_page.py",
]

# Unconfigured structlog prints DEBUG lines to STDOUT, so any test that calls
# engine/ingest helpers in its setup pollutes captured stdout (a `--json` CLI
# test then fails json.loads on "2026-…" log lines). The CLI and server both
# bind structlog to stderr at entry; tests only got that binding if some
# earlier test happened to trigger it — an order dependence pytest-xdist's
# fresh workers expose. Configure it here, once per worker, exactly the way
# the CLI does (WARNING level, dynamic stderr proxy so capsys replacement and
# teardown are honored — never pin the sys.stderr object itself).
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    logger_factory=structlog.PrintLoggerFactory(file=dynamic_stderr),  # type: ignore[arg-type]
)

try:
    from hypothesis import HealthCheck
    from hypothesis import settings as _hyp_settings

    # Property-test profiles (tests/test_property_invariants.py). Registered
    # here so `--hypothesis-profile=hunt` resolves at pytest configure time.
    _hyp_settings.register_profile(
        "default", deadline=None, max_examples=25, suppress_health_check=[HealthCheck.too_slow]
    )
    _hyp_settings.register_profile(
        "hunt", deadline=None, max_examples=300, suppress_health_check=[HealthCheck.too_slow]
    )
    _hyp_settings.load_profile("default")
except ImportError:
    pass


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Serialize live-Word tests under pytest-xdist.

    tryfirst matters: in each xdist worker, WorkerInteractor's own
    pytest_collection_modifyitems consumes the xdist_group marker (it rewrites
    the nodeid to "…@group" for the loadgroup scheduler). Our marker must be
    attached before that hook runs, or the grouping silently does nothing.

    Tests that drive the real Word COM instance (the `active_word_app`
    fixture, plus everything in test_live_word*.py) all bind to the single
    active Word application — two xdist workers doing that concurrently
    corrupt each other's document state. `xdist_group` + `--dist loadgroup`
    (set in pyproject addopts) pins them to ONE worker, where they run
    sequentially; every other test still distributes freely.
    """
    for item in items:
        try:
            source = inspect.getsource(item.obj)
        except (OSError, TypeError):
            source = ""
        unsupported_python_server_surface = any(
            marker in source
            for marker in (
                "fastmcp",
                "adeu.server",
                "mcp_components.tools",
                "handle_init",
                "_get_claude_config_path",
                'run_cli(["init"',
                "--live",
            )
        )
        if unsupported_python_server_surface and item.name != "test_extract_never_imports_fastmcp":
            item.add_marker(pytest.mark.skip(reason="Python MCP/live-Word surface is excluded from the slim fork"))

        is_live_word = "active_word_app" in getattr(item, "fixturenames", ())
        if not is_live_word:
            basename = item.path.name if getattr(item, "path", None) else ""
            is_live_word = basename.startswith("test_live_word")
        if is_live_word:
            item.add_marker(pytest.mark.xdist_group("live_word"))


@pytest.fixture(scope="session", autouse=True)
def _isolate_windows_appdata(tmp_path_factory):
    """On Windows, `adeu init` resolves the Claude Desktop config via %APPDATA%.
    A test that runs init without patching _get_claude_config_path would rewrite
    the developer's real claude_desktop_config.json (this happened 2026-07-20:
    two QA-repro tests injected fake uvx entries into a live config). Pointing
    APPDATA at a throwaway directory for the whole session makes that class of
    accident impossible; tests that assert on the config still patch the path
    getter explicitly."""
    if sys.platform != "win32":
        yield
        return
    mp = pytest.MonkeyPatch()
    mp.setenv("APPDATA", str(tmp_path_factory.mktemp("appdata")))
    yield
    mp.undo()


@pytest.fixture
def simple_docx_stream():
    """Returns a BytesIO stream containing a simple DOCX."""
    doc = Document()
    doc.add_heading("Contract Agreement", 0)
    doc.add_paragraph("This is a simple contract.")
    doc.add_paragraph("The party of the first part shall be known as the Seller.")

    stream = io.BytesIO()
    doc.save(stream)
    stream.seek(0)
    return stream


# Only define COM fixtures on Windows
if sys.platform == "win32":
    import pythoncom
    import win32com.client

    @pytest.fixture
    def active_word_app():
        """
        Creates an ephemeral, visible MS Word instance with a fresh document.
        Ensures it is torn down properly after the test.
        """
        pythoncom.CoInitialize()

        app = None
        try:
            # Dispatch starts a new background instance if one doesn't exist.
            # GetActiveObject will then be able to hook into it in the tool.
            app = win32com.client.Dispatch("Word.Application")
            app.Visible = True  # Needs to be visible/active for GetActiveObject sometimes
            doc = app.Documents.Add()

            # Bring to front so GetActiveObject definitely binds to this instance
            app.Activate()

            # Seed initial content
            doc.Range(0, 0).Text = "Hello world! This is a live testing document.\n"

            yield app, doc

        except Exception as e:
            pytest.skip(f"Could not initialize Word COM for testing: {e}")

        finally:
            if app:
                try:
                    doc.Close(0)  # 0 = wdDoNotSaveChanges
                except Exception:
                    pass
                # We intentionally omit app.Quit() and pythoncom.CoUninitialize()
                # to avoid Windows Access Violations (0x800706be) when Pytest holds COM locals.
