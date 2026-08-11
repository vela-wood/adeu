# Adeu: Python Toolchain

This directory contains the slim Python implementation of Adeu. It provides the core Redline Engine, developer SDK, and command-line interface (CLI).

Adeu acts as a "Virtual DOM" for Microsoft Word. It translates complex DOCX XML into token-efficient CriticMarkup for LLMs, validates structural edits, and patches the XML safely to preserve document formatting, metadata, and styles.

## Local Development Setup

Adeu is managed using [`uv`](https://docs.astral.sh/uv/) and packaged via `hatchling`. It requires Python 3.12 or higher.

```bash
# Clone and enter the directory
cd python

# Install dependencies and sync the virtual environment
uv sync

# Run the test suite
uv run pytest
```

## The Command Line Interface (CLI)

The `adeu` CLI provides a powerful suite of tools for interacting with documents locally.

### Extraction & Reading
Extract text as CriticMarkup. Use `--clean-view` to simulate "Accept All Changes".
```bash
# Extract full text
uvx adeu extract contract.docx -o output.md

# Extract only the structural heading outline
uvx adeu extract contract.docx --mode outline

```

### Diffing
Generate a word-level patch diff between two document versions.
```bash
# Compare two DOCX files
uvx adeu diff original.docx modified.docx

# Output raw JSON edits for programmatic use
uvx adeu diff original.docx modified.docx --json
```

### Applying Edits
Apply a JSON array of `DocumentChange` objects (or a modified markdown file) back to the DOCX.
```bash
# Apply a JSON batch of edits to a file
uvx adeu apply original.docx edits.json --author "AI Reviewer" -o redlined.docx

# Emit the batch result as machine-readable JSON on stdout (for agents/scripts)
uvx adeu apply original.docx edits.json --json

```

### Accepting All Changes
Accept every tracked change and remove all comments in one operation, producing a finalized clean document. Mirrors the `accept_all_changes` MCP tool.
```bash
# Writes contract_clean.docx next to the input
uvx adeu accept-all contract.docx

# Explicit output path, machine-readable result on stdout
uvx adeu accept-all contract.docx -o final.docx --json
```

### Sanitization
Strip sensitive metadata, hidden text, and author names before external distribution.
```bash
# Full scrub (fails if unresolved track changes exist unless --accept-all is passed)
uvx adeu sanitize contract.docx --accept-all -o clean.docx

# Keep your redlines/comments, but anonymize the author and strip metadata
uvx adeu sanitize redline.docx --keep-markup --author "My Firm"
```

### Agentic / Headless Usage (the CLI as an API)
When an agent operates in a closed sandbox (a CI pipeline, a containerized coding agent) it cannot reach an MCP server. The CLI is the fallback: a strictly local, air-gapped command-line API that accepts the same JSON change schema as the MCP tools. The mapping is 1:1:

| MCP tool                 | CLI equivalent                          |
| ------------------------ | --------------------------------------- |
| `read_docx`              | `adeu extract <doc> [--json]`           |
| `diff_docx_files`        | `adeu diff <orig> <mod> [--json]`       |
| `process_document_batch` | `adeu apply <doc> <changes.json> [--json]` |
| `accept_all_changes`     | `adeu accept-all <doc> [--json]`        |

The I/O contract (see `docs/cli-agent-spec.md` for the full specification):

* **stdout** carries only document data (Markdown/CriticMarkup) or, with `--json`, a machine-readable JSON result. `uvx adeu extract doc.docx > out.md` always produces a clean file, even with `--debug`.
* **stderr** carries all logs, progress messages, warnings, and errors.
* **Exit codes**: `0` = full success; `1` = failure or a partially applied batch (check `edits_skipped` in the JSON stats).

`adeu apply --json` prints the engine's raw stats object — `edits_applied`, `edits_skipped`, per-edit reports with CriticMarkup previews, plus `output_path` — and suppresses the human-readable logs. A batch that fails validation prints `{"error": "batch_validation_failed", "errors": [...]}` and exits 1.

## The Python SDK

The SDK allows you to embed Adeu's Redline Engine directly into your own Python applications.

### Applying Tracked Changes
The engine processes a flat list of `DocumentChange` objects (`ModifyText`, `AcceptChange`, `RejectChange`, `ReplyComment`, `InsertTableRow`, `DeleteTableRow`).

```python
from io import BytesIO
from adeu import RedlineEngine, ModifyText, AcceptChange

# 1. Load the document stream
with open("contract.docx", "rb") as f:
    stream = BytesIO(f.read())

# 2. Define your edits
changes = [
    ModifyText(
        target_text="State of New York",
        new_text="State of Delaware",
        comment="Standardized jurisdiction.",
        match_mode="all"
    ),
    AcceptChange(target_id="Chg:12")
]

# 3. Initialize the engine and apply
engine = RedlineEngine(stream, author="AI Copilot")
stats = engine.process_batch(changes)

# 4. Save the result
with open("contract_redlined.docx", "wb") as f:
    f.write(engine.save_to_stream().getvalue())
```

### Extracting Text
Read a document into CriticMarkup representation.

```python
from io import BytesIO
from adeu import extract_text_from_stream

with open("contract.docx", "rb") as f:
    stream = BytesIO(f.read())

# Extract raw text with {++ ++} and {-- --} tags intact
markdown_text = extract_text_from_stream(stream)

# Extract clean text simulating "Accept All Changes"
clean_text = extract_text_from_stream(stream, clean_view=True)
```

### Sanitizing Documents
Run the metadata scrubber programmatically.

```python
from adeu.sanitize import sanitize_docx

result = sanitize_docx(
    input_path="draft.docx",
    output_path="final.docx",
    keep_markup=True,
    author="Legal Team"
)

print(result.report_text)
```

## Testing & Architectural Constraints

When developing inside the `python/` directory, please note the following invariants:

* **Surgical Mode**: The `RedlineEngine` never performs global document normalization on load or save. This strict behavior prevents the silent destruction of unrelated metadata (like `<w:proofErr>`) and minimizes XML diff noise.
* **Testing Asserts**: Native `python-docx` `Paragraph.text` properties silently ignore text inside `<w:ins>` tags. When writing tests to verify redlines, strictly use `extract_text_from_stream(clean_view=True)` to accurately evaluate the accepted text state.
