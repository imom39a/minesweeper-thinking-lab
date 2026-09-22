"""Check documentation links and recorded research data integrity."""
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
    checksums = {}
    for line in (ROOT / "minesweeper/results/SHA256SUMS").read_text().splitlines():
        digest, filename = line.split("  ", 1)
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or filename in checksums:
            raise SystemExit(f"Invalid or duplicate checksum: {filename}")
        checksums[filename] = digest
    results_dir = ROOT / "minesweeper/results"
    results = list(results_dir.rglob("*.json"))
    if set(checksums) != {path.relative_to(results_dir).as_posix() for path in results}:
        errors.append("Result files and SHA256SUMS entries differ")
    for path in results:
        relative = str(path.relative_to(ROOT))
        expected = checksums.get(path.relative_to(results_dir).as_posix())
        if expected is None or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f"Recorded result changed: {relative}")
        document = json.loads(path.read_text())
        if "config" not in document or "summary" not in document:
            errors.append(f"Invalid result: {relative}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Checked {len(documents)} documents and preserved {len(results)} result artifacts.")


if __name__ == "__main__":
    main()
