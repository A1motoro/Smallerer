"""Generated-file detection (spec §3.5 rules 1 & 2).

Critical for in-place mode: must reliably identify our own outputs, or 2nd run
will ingest them as inputs.

Two-layer detection (fallback chain):
1. MANIFEST registry (primary, authoritative)
2. YAML front matter with `pipeline_version:` field (fallback if manifest lost)

File must pass BOTH name check (double suffix .ext.md) AND front matter check
to be considered generated. Conservative: ambiguous → assume user file.
"""

from __future__ import annotations

from pathlib import Path

_PROBE_BYTES = 4096


def looks_like_artifact_name(path: Path) -> bool:
    """Check if filename matches artifact naming (source.ext + .md).

    Naming spec §3.2: preserve full source name then append .md
    → artifacts always have double suffix (.pdf.md, .docx.md, etc.)
    """
    return path.suffix.lower() == ".md" and Path(path.stem).suffix != ""


def has_pipeline_front_matter(path: Path) -> bool:
    """Check if file has YAML front matter with pipeline_version field.

    Probe first 4KB (front matter should always fit). If front matter is
    longer than probe (shouldn't happen), conservatively return False.

    Only accepts files starting with '---' and containing 'pipeline_version:'
    before the closing '---'. This detects spec §3.3 sidecar files.
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(_PROBE_BYTES)
    except OSError:
        return False
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not text.startswith("---"):
        return False
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        if line.startswith("pipeline_version:"):
            return True
    # Front matter longer than probe → shouldn't happen, conservatively False
    return False


def is_generated(path: Path) -> bool:
    return looks_like_artifact_name(path) and has_pipeline_front_matter(path)
