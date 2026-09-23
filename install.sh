#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVICES_DIR="$HOME/Library/Services"
SCRIPTS_DIR="$HOME/Scripts"
VENV="$SCRIPTS_DIR/ai-redact-venv"
LOG="$HOME/Library/Logs/ai-redact-install.log"
HELPER_SRC="$ROOT/native/apple-redact-worker"

mkdir -p "$SCRIPTS_DIR" "$SERVICES_DIR" "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

echo "=== macos-local-redact-toolkit (Apple Silicon) ==="
echo "Root: $ROOT"
echo "Home: $HOME"
echo "Arch: $(uname -m)"

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "WARN: expected Apple Silicon (arm64); continuing, but paths may use /usr/local"
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "ERROR: Homebrew is required. Install it from https://brew.sh"
  exit 1
fi

if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

echo "Installing/upgrading brew deps (ffmpeg tesseract exiftool pipx)..."
brew list pipx >/dev/null 2>&1 || brew install pipx
brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list tesseract >/dev/null 2>&1 || brew install tesseract
brew list exiftool >/dev/null 2>&1 || brew install exiftool
if ! brew list tesseract-lang >/dev/null 2>&1; then
  echo "(optional) installing tesseract-lang for chi_tra/eng..."
  brew install tesseract-lang || echo "WARN: tesseract-lang skipped"
fi

pipx ensurepath >/dev/null 2>&1 || true
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "Installing/upgrading markitdown==0.1.8 via pipx..."
if command -v markitdown >/dev/null 2>&1; then
  pipx uninstall markitdown || true
fi
pipx install "markitdown==0.1.8"
pipx inject markitdown "markitdown[pdf,docx,pptx,xlsx]" \
  pillow pytesseract pypdf pymupdf pymupdf4llm

MARKITDOWN_BIN="$(command -v markitdown || true)"
if [[ -z "$MARKITDOWN_BIN" && -x "$HOME/.local/bin/markitdown" ]]; then
  MARKITDOWN_BIN="$HOME/.local/bin/markitdown"
fi
if [[ -z "$MARKITDOWN_BIN" ]]; then
  echo "ERROR: markitdown not found after pipx install. Open a new Terminal and re-run."
  exit 1
fi
echo "markitdown: $MARKITDOWN_BIN ($("$MARKITDOWN_BIN" --version 2>/dev/null || true))"
export MARKITDOWN_BIN

# pipx console scripts are often:
#   #!/bin/sh
#   '''exec' '/path/to/venv/bin/python' "$0" "$@"
python_ok() {
  [[ -n "${1:-}" && -x "$1" ]] || return 1
  "$1" -c 'import sys' >/dev/null 2>&1
}

MARKITDOWN_PY=""
if [[ -f "$MARKITDOWN_BIN" ]]; then
  cand="$(awk 'NR==1 { sub(/^#!/, ""); print $1; exit }' "$MARKITDOWN_BIN")"
  if python_ok "$cand"; then
    MARKITDOWN_PY="$cand"
  else
    cand="$(awk -F"'" '$0 ~ /exec/ {
      for (i = 1; i <= NF; i++) if ($i ~ /python/) { print $i; exit }
    }' "$MARKITDOWN_BIN")"
    if python_ok "$cand"; then
      MARKITDOWN_PY="$cand"
    fi
  fi
fi
if ! python_ok "${MARKITDOWN_PY:-}"; then
  for candidate in \
    "$HOME/.local/pipx/venvs/markitdown/bin/python" \
    "$HOME/Library/Application Support/pipx/venvs/markitdown/bin/python"; do
    if python_ok "$candidate"; then
      MARKITDOWN_PY="$candidate"
      break
    fi
  done
fi
if ! python_ok "${MARKITDOWN_PY:-}"; then
  echo "ERROR: markitdown pipx venv python not found (checked shebang, exec line, and common pipx paths)."
  exit 1
fi
echo "markitdown python: $MARKITDOWN_PY"
export MARKITDOWN_PY

echo "Verifying pymupdf4llm..."
"$MARKITDOWN_PY" - <<'PY'
import importlib.util
for name in ("pymupdf", "pymupdf4llm"):
    print(name, "OK" if importlib.util.find_spec(name) else "MISSING")
PY
pipx runpip markitdown install -U httpx SpeechRecognition || true

PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$HOME/miniconda3/bin/python3" python3; do
  if [[ -x "$c" ]] || command -v "$c" >/dev/null 2>&1; then
    PY="$c"
    break
  fi
done
if [[ -z "$PY" ]]; then
  echo "ERROR: python3 is required"
  exit 1
fi
echo "python: $PY ($($PY -V 2>&1))"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating venv: $VENV"
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/pip" install -U pip

echo "Building Apple Intelligence helper..."
if [[ ! -x "$HELPER_SRC/build.sh" ]]; then
  echo "ERROR: missing $HELPER_SRC/build.sh"
  exit 1
fi
zsh "$HELPER_SRC/build.sh"
cp "$HELPER_SRC/bin/apple-redact-worker" "$SCRIPTS_DIR/apple-redact-worker"
chmod +x "$SCRIPTS_DIR/apple-redact-worker"

cp "$ROOT/scripts/markitdown_qa.py" "$SCRIPTS_DIR/markitdown_qa.py"
cp "$ROOT/scripts/apple_worker.py" "$SCRIPTS_DIR/apple_worker.py"
cp "$ROOT/scripts/ai_redact.py" "$SCRIPTS_DIR/ai_redact.py"
chmod +x "$SCRIPTS_DIR/markitdown_qa.py" "$SCRIPTS_DIR/ai_redact.py"

for name in "Convert to Markdown" "AI Redact"; do
  src="$ROOT/services/$name.workflow"
  dst="$SERVICES_DIR/$name.workflow"
  if [[ -d "$src" ]]; then
    rm -rf "$dst"
    cp -R "$src" "$dst"
    echo "Copied $name.workflow"
  else
    echo "ERROR: missing $src"
    exit 1
  fi
done

MARKITDOWN_BIN="$MARKITDOWN_BIN" MARKITDOWN_PY="$MARKITDOWN_PY" "$VENV/bin/python" - << 'PY'
import os
import plistlib
from pathlib import Path

home = Path.home()
services = home / "Library" / "Services"
mark_py = Path(os.environ["MARKITDOWN_PY"])
redact_py = home / "Scripts" / "ai-redact-venv" / "bin" / "python"
mark_helper = home / "Scripts" / "markitdown_qa.py"
redact_helper = home / "Scripts" / "ai_redact.py"

def rewrite_workflow(name: str, command: str):
    wf = services / f"{name}.workflow" / "Contents" / "document.wflow"
    data = plistlib.loads(wf.read_bytes())
    params = data["actions"][0]["action"]["ActionParameters"]
    params["COMMAND_STRING"] = command
    params["shell"] = "/bin/zsh"
    params["inputMethod"] = 1
    wf.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_XML))
    print(f"Rewrote {name}.workflow with this user's paths")

mark_cmd = f'''export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:$PATH"
export MARKITDOWN_PDF_MODE="${{MARKITDOWN_PDF_MODE:-pymupdf4llm}}"
PY="{mark_py}"
HELPER="{mark_helper}"
LOG="$HOME/Library/Logs/markitdown-qa.log"
mkdir -p "$(dirname "$LOG")"

if [ ! -x "$PY" ]; then
  /usr/bin/osascript -e 'display notification "markitdown Python not found" with title "Convert to Markdown"'
  exit 1
fi

if "$PY" "$HELPER" "$@" >"$LOG" 2>&1; then
  /usr/bin/osascript -e 'display notification "Done" with title "Convert to Markdown"'
  exit 0
fi
err=$(/usr/bin/grep -E '^(ERROR |RuntimeError:)' "$LOG" 2>/dev/null | /usr/bin/tail -n 1 | /usr/bin/cut -c1-180)
/usr/bin/osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv)' -e 'end run' -- "${{err:-see ~/Library/Logs/markitdown-qa.log}}" "Convert to Markdown failed"
exit 1
'''

redact_cmd = f'''export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:$PATH"
PY="{redact_py}"
HELPER="{redact_helper}"
LOG="$HOME/Library/Logs/ai-redact.log"
mkdir -p "$(dirname "$LOG")"

if [ ! -x "$PY" ]; then
  /usr/bin/osascript -e 'display notification "ai-redact venv not found" with title "AI Redact"'
  exit 1
fi

if "$PY" "$HELPER" "$@" >"$LOG" 2>&1; then
  /usr/bin/osascript -e 'display notification "Done" with title "AI Redact"'
  exit 0
fi
err=$(/usr/bin/grep -E '^(ERROR |RuntimeError:)' "$LOG" 2>/dev/null | /usr/bin/tail -n 1 | /usr/bin/cut -c1-180)
/usr/bin/osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv)' -e 'end run' -- "${{err:-see ~/Library/Logs/ai-redact.log}}" "AI Redact failed"
exit 1
'''

rewrite_workflow("Convert to Markdown", mark_cmd)
rewrite_workflow("AI Redact", redact_cmd)
PY

echo
echo "=== Done ==="
echo "Scripts: $SCRIPTS_DIR"
echo "Helper: $SCRIPTS_DIR/apple-redact-worker"
echo "Services: $SERVICES_DIR"
echo "Apple on-device plus Private Cloud Compute, no third-party model hosts."
echo "Next:"
echo "  1) Enable Apple Intelligence (macOS 26+)"
echo "  2) Finder → right-click a PDF/image → Quick Actions → Convert to Markdown / AI Redact"
echo "PDF default: pymupdf4llm; vision: MARKITDOWN_PDF_MODE=vision"
echo "If the actions are missing: Quick Actions → Customize… and turn both on"
echo "Convert to Markdown works without Apple Intelligence. AI Redact requires it."
