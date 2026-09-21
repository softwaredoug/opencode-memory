#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'Required command not found: %s\n' "$command_name" >&2
    exit 1
  fi
}

require_command uv
require_command opencode
require_command install

"$repo_dir/scripts/install_opencode.sh" --force
uv tool install --force "$repo_dir"

printf 'Installed OpenCode history daemon and search CLI.\n'
