#!/usr/bin/env bash

set -euo pipefail

usage() {
  printf 'Usage: %s [--force]\n' "$0"
}

force=false
case "${1:-}" in
  "")
    ;;
  --force)
    force=true
    ;;
  --help|-h)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_file="$repo_dir/opencode-telemetry-plugin/telemetry.js"
config_dir="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"
plugin_dir="$config_dir/plugins"
target_file="$plugin_dir/telemetry.js"

if [[ ! -f "$source_file" ]]; then
  printf 'Source plugin not found: %s\n' "$source_file" >&2
  exit 1
fi

if [[ -e "$target_file" && "$force" != true ]]; then
  printf 'Plugin already exists: %s\n' "$target_file" >&2
  printf 'Re-run with --force to replace it.\n' >&2
  exit 1
fi

mkdir -p "$plugin_dir"
install -m 0644 "$source_file" "$target_file"

printf 'Installed OpenCode telemetry plugin to %s\n' "$target_file"
printf 'Restart OpenCode for the plugin to load.\n'
