#!/usr/bin/env bash

# Source from bash: source scripts/load-jev-env.sh
# Values are parsed by Python and exported as data, never evaluated as shell code.
_mines_project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "${_mines_project_dir}/.env" ]]; then
  {
    if ! IFS= read -r -d '' _mines_env_status || [[ "$_mines_env_status" != "OK" ]]; then
      unset _mines_env_status _mines_project_dir
      return 1 2>/dev/null || exit 1
    fi
    while IFS= read -r -d '' _mines_env_entry; do
      export "$_mines_env_entry"
    done
  } < <(python3 - "${_mines_project_dir}/.env" <<'PYENV'
from pathlib import Path
import re
import shlex
import sys

entries = []
for line in Path(sys.argv[1]).read_text().splitlines():
    line = line.strip()
    if line.startswith("export "):
        line = line[7:].lstrip()
    key, separator, raw = line.partition("=")
    key = key.strip()
    if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        continue
    lexer = shlex.shlex(raw.strip(), posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        value = " ".join(lexer)
    except ValueError:
        raise SystemExit("Invalid quoting in .env; values must occupy one line.") from None
    if "\0" in value:
        raise SystemExit("Invalid NUL character in .env.")
    entries.append(f"{key}={value}\0".encode())
sys.stdout.buffer.write(b"OK\0" + b"".join(entries))
PYENV
  )
  unset _mines_env_entry _mines_env_status
fi

if [[ -z "${TYPESAFE_API_KEY:-}" && -n "${JEV_API_KEY:-}" ]]; then
  export TYPESAFE_API_KEY="${JEV_API_KEY}"
fi
if [[ -z "${OPENROUTER_API_KEY:-}" && -n "${openouterkey:-}" ]]; then
  export OPENROUTER_API_KEY="${openouterkey}"
fi
unset _mines_project_dir

if [[ -z "${TYPESAFE_API_KEY:-}" ]]; then
  echo "Missing TYPESAFE_API_KEY (or JEV_API_KEY); fill in your private .env first." >&2
  return 1 2>/dev/null || exit 1
fi
