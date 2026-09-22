"""Check standalone documentation links and original research data integrity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    errors = []
    documents = [ROOT / "README.md", ROOT / "ATTRIBUTION.md", ROOT / "CHANGELOG.md"]
    documents += list((ROOT / "docs").glob("*.md"))
    documents += list((ROOT / "minesweeper").glob("README.md"))
    documents += list((ROOT / "minesweeper/docs").glob("*.md"))
    for path in documents:
        if not path.exists():
            errors.append(f"Missing document: {path.relative_to(ROOT)}")
            continue
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            relative = target.split("#")[0]
            if relative and not (path.parent / relative).exists():
                errors.append(f"Broken link in {path.relative_to(ROOT)}: {relative}")
    extraction = json.loads((ROOT / "EXTRACTION.json").read_text())
    results = list((ROOT / "minesweeper/results").glob("*.json"))
    for path in results:
        relative = str(path.relative_to(ROOT))
        expected = extraction["files"].get(relative)
        if expected is None or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f"Historical result changed: {relative}")
        document = json.loads(path.read_text())
        if "config" not in document or "summary" not in document:
            errors.append(f"Invalid result: {relative}")
    if len(results) != 11:
        errors.append(f"Expected 11 historical results, found {len(results)}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Checked {len(documents)} documents and preserved {len(results)} result artifacts.")


if __name__ == "__main__":
    main()
