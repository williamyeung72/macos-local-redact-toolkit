# macOS Local Redact Toolkit

Offline-first macOS [Finder Quick Actions](https://support.apple.com/guide/mac-help/mchl7ab36458/mac) that convert local files to Markdown and produce **Ollama-assisted redaction drafts**. Nothing is uploaded unless your own machine or tools are configured to do so.

Target platform: **Apple Silicon** (M-series Macs).

[繁體中文說明](./README.zh-Hant.md)

> [!WARNING]
> This toolkit produces AI-assisted redaction drafts, not a guarantee of complete
> anonymisation, privacy protection, or legal compliance. Always review output
> manually before sharing, uploading, or relying on it.
>
> Do not use it as the sole control for regulated, legal, medical, financial,
> employment, school, or safety-critical documents.

## Quick Actions

These two Finder actions are independent. You can use either one on its own.

| Quick Action | What it does | Output |
| --- | --- | --- |
| **Convert to Markdown** | File / image → Markdown | Sibling `*.md` |
| **Ollama AI Redact** | Prefer Markdown, then redact with a local text model | `*_redacted.md` |

Redaction replaces sensitive spans with typed placeholders such as `[PERSON_1]` and `[EMAIL_2]`. It does **not** modify the original file and it is **not** irreversible anonymisation.

### Convert to Markdown paths

| Type | Default behaviour |
| --- | --- |
| **PDF** | **`pymupdf4llm`** (local; no cloud conversion) |
| PDF (optional) | `MARKITDOWN_PDF_MODE=vision` → full-page Ollama vision (`qwen3.5:4b`) |
| PDF (optional) | `text` = plain PyMuPDF blocks; `auto` = vision when extractable text is sparse, otherwise pymupdf4llm |
| **Office** (docx / pptx / xlsx) | MarkItDown; embedded images via Apple visual understanding when available |
| **Images** | EXIF / meta (MarkItDown) + Ollama vision; Tesseract if that fails |
| Other | Microsoft MarkItDown |

### Ollama AI Redact paths

1. Non-images: convert to `.md` when possible (MarkItDown / PDF logic above)
2. Redact that Markdown with `llama3.1` → `*_redacted.md`
3. If conversion is not useful, use a vision model for images
4. **Review the draft yourself** before sharing or uploading

## Layout

```
macos-local-redact-toolkit/
├── README.md
├── README.zh-Hant.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── .gitignore
├── install.sh
├── samples/
│   └── demo-contact-list.txt
├── scripts/
│   ├── markitdown_qa.py
│   └── ollama_redact.py
└── services/
    ├── Convert to Markdown.workflow
    └── Ollama AI Redact.workflow
```

After install:

- Scripts: `~/Scripts/markitdown_qa.py`, `~/Scripts/ollama_redact.py`
- Redact venv: `~/Scripts/ollama-redact-venv`
- Quick Actions: `~/Library/Services/`
- Logs: `~/Library/Logs/markitdown-qa.log`, `ollama-redact.log`, `ollama-redact-install.log`

Committed `.workflow` bundles use `$HOME` placeholders. `install.sh` rewrites the installed copies to this Mac’s absolute paths. A git clone is not a working Quick Action until you run the installer.

## Prerequisites

1. macOS **Apple Silicon** (arm64)
2. [Homebrew](https://brew.sh)
3. [Ollama](https://ollama.com) installed and runnable
4. The installer also needs (and will install) `pipx`, `ffmpeg`, `tesseract`, `exiftool`

## Install

```bash
cd /path/to/macos-local-redact-toolkit
chmod +x install.sh
./install.sh
```

`install.sh` will:

1. Confirm / install brew deps (`pipx`, `ffmpeg`, `tesseract`, `exiftool`; optional `tesseract-lang`)
2. `pipx install markitdown==0.1.8` (not `markitdown[all]`, which can pin an Azure pre-release)
3. `pipx inject`: `markitdown-ocr`, `openai`, `pillow`, `pytesseract`, `pypdf`, `pymupdf`, **`pymupdf4llm`**
4. Create `~/Scripts/ollama-redact-venv` and install `ollama`, `pymupdf`, and related packages
5. Copy scripts and the two Finder workflows, and rewrite paths for `$HOME`  
   (**Convert to Markdown** defaults to `MARKITDOWN_PDF_MODE=pymupdf4llm`)

Then pull models (weights are not bundled):

```bash
ollama pull llama3.1:latest
ollama pull qwen3.5:4b
```

After `./install.sh`, right-click a PDF, image, or other supported file. **Quick Actions** may not yet list **Convert to Markdown** or **Ollama AI Redact**. Open **Quick Actions → Customize…** and turn both items on.

If they still do not appear: **System Settings → Privacy & Security → Extensions → Finder**.

## Usage

1. Keep **Ollama** running
2. In Finder, select a PDF, image, or other supported file → right-click → **Quick Actions** → **Convert to Markdown** or **Ollama AI Redact** (use **Customize…** if they are missing)
3. Check the sibling output; on failure, check the notification and logs

CLI (same scripts as the Quick Actions):

```bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
export OLLAMA_HOST="http://127.0.0.1:11434"

# pipx markitdown venv Python (path varies by pipx; shebang is authoritative)
PY="$(awk 'NR==1 { sub(/^#!/, ""); print $1; exit }' "$(command -v markitdown)")"

"$PY" ~/Scripts/markitdown_qa.py ./some.pdf
"$PY" ~/Scripts/markitdown_qa.py ./photo.jpg

# Redaction
~/Scripts/ollama-redact-venv/bin/python ~/Scripts/ollama_redact.py ./some.pdf
```

Synthetic smoke-test input is in `samples/demo-contact-list.txt`. Do not commit real documents or `*_redacted.md` output.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Scripts normalise `0.0.0.0` to `127.0.0.1` |
| `MARKITDOWN_PDF_MODE` | `pymupdf4llm` | `pymupdf4llm` \| `vision` \| `text` \| `auto` |
| `MARKITDOWN_LLM_MODEL` | `qwen3.5:4b` | Vision / OCR model |
| `MARKITDOWN_PDF_CHARS_PER_PAGE` | `200` | `auto` mode: average chars/page below this → vision |
| `MARKITDOWN_PDF_VISION_DPI` | `180` | Full-page render DPI |

## Why PDF defaults to pymupdf4llm

Multi-column score sheets and timetables often lose reading order with naive text extraction or small vision models.

For some PDFs that contain multi-column text, timetables, or table-like layout, pymupdf4llm in local testing usually keeps a more readable order and structure than plain text extraction. Results vary by document; review the Markdown by hand. Use `MARKITDOWN_PDF_MODE=vision` for scans or image-heavy pages.

## Development

After editing scripts:

1. Copy them to `~/Scripts/` (or re-run `./install.sh`)
2. If you change workflow default environment variables, update `services/*.workflow` or let `install.sh` rewrite them

Optional zip:

```bash
cd ..
ditto -c -k --sequesterRsrc --keepParent macos-local-redact-toolkit macos-local-redact-toolkit.zip
```

Smoke checks:

- Text / table PDF → log should include `PDF path=pymupdf4llm`; check column order by eye
- Image → Ollama vision; Tesseract fallback when Ollama is stopped
- `markitdown --list-plugins` should list `ocr`

## Security, privacy and limitations

- Designed for local processing. Confirm your own network, Ollama, and dependency configuration before handling sensitive data.
- Ollama-assisted redaction can miss, misclassify, or alter sensitive information.
- Always manually review outputs before sharing or uploading.
- Do not commit input files, logs, generated output, credentials, certificates, or real redacted documents.
- Do not treat this toolkit as legal, compliance, security, or data-protection advice.
- The project does not claim PCI, HIPAA, GDPR, HKMA, school-policy, or other regulatory compliance.
- Model weights are not bundled.
- Apple Silicon is the supported path; Intel Macs may need `/usr/local` instead of `/opt/homebrew`.

## Third-party components

This project integrates or invokes third-party tools and libraries, including
Ollama, Microsoft MarkItDown, PyMuPDF, pymupdf4llm, Tesseract, ExifTool,
FFmpeg, and Python packages. These components are distributed under their own
licenses and terms. Users are responsible for reviewing and complying with
those licenses and terms.

The OpenAI Python client is used only as a local OpenAI-compatible adapter
against Ollama (`api_key="ollama"` is a dummy value, not a cloud credential).

## License

MIT — see [LICENSE](./LICENSE).
