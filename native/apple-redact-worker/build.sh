#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/bin"
swiftc -parse-as-library -O -o "$ROOT/bin/apple-redact-worker" "$ROOT/main.swift"
echo "Built $ROOT/bin/apple-redact-worker"
