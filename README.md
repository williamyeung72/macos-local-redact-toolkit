# macOS Local Redact Toolkit

macOS [Finder Quick Actions](https://support.apple.com/guide/mac-help/mchl7ab36458/mac) that convert local files to Markdown and produce **AI Redact** drafts. Inference uses **Apple on-device plus Private Cloud Compute, no third-party model hosts.**

Target platform: **Apple Silicon** (M-series Macs). **AI Redact** needs **macOS 26** with Apple Intelligence enabled. **Convert to Markdown** still works without that.

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
| **AI Redact** | Prefer Markdown, then redact with Apple Intelligence | `*_redacted.md` |

Redaction replaces sensitive spans with typed placeholders such as `[PERSON_1]` and `[EMAIL_2]`. It does **not** modify the original file and it is **not** irreversible anonymisation. Treat every `*_redacted.md` as a draft to review.

An older Finder item named **Ollama AI Redact**, if already installed, is left on disk. New installs add **AI Redact** instead.

### Convert to Markdown paths

| Type | Default behaviour |
| --- | --- |
| **PDF** | **`pymupdf4llm`** for text PDFs; image-only / sparse text → Apple visual |
| PDF (optional) | `MARKITDOWN_PDF_MODE=vision` → full-page Apple visual understanding |
| PDF (optional) | `text` = plain PyMuPDF blocks; `auto` = vision when extractable text is sparse, otherwise pymupdf4llm |
| **Office** (docx / pptx / xlsx) | MarkItDown; embedded images via Apple visual understanding when available |
| **Images** | EXIF / meta (MarkItDown) + Apple visual understanding; Tesseract if that fails |
| Other | Microsoft MarkItDown |

### AI Redact paths

1. Non-Markdown: convert to `.md` when possible (MarkItDown / PDF logic above)
2. Redact that Markdown with Apple Intelligence → `*_redacted.md`
3. If Apple Intelligence is unavailable, AI Redact fails in English and does not write a partial draft
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
├── native/
│   └── apple-redact-worker/
├── scripts/
│   ├── apple_worker.py
│   ├── markitdown_qa.py
│   └── ai_redact.py
└── services/
    ├── Convert to Markdown.workflow
    └── AI Redact.workflow
```

After install:

- Scripts: `~/Scripts/markitdown_qa.py`, `~/Scripts/ai_redact.py`, `~/Scripts/apple_worker.py`
- Helper: `~/Scripts/apple-redact-worker`
- Redact venv: `~/Scripts/ai-redact-venv`
- Quick Actions: `~/Library/Services/`
- Logs: `~/Library/Logs/markitdown-qa.log`, `ai-redact.log`, `ai-redact-install.log`

Committed `.workflow` bundles use `$HOME` placeholders. `install.sh` rewrites the installed copies to this Mac’s absolute paths. A git clone is not a working Quick Action until you run the installer.

## Prerequisites

1. macOS **Apple Silicon** (arm64)
2. [Homebrew](https://brew.sh)
3. The installer also needs (and will install) `pipx`, `ffmpeg`, `tesseract`, `exiftool`
4. **AI Redact**: macOS 26+ with Apple Intelligence enabled

## Install

```bash
cd /path/to/macos-local-redact-toolkit
chmod +x install.sh
./install.sh
```

`install.sh` will:

1. Confirm / install brew deps (`pipx`, `ffmpeg`, `tesseract`, `exiftool`; optional `tesseract-lang`)
2. `pipx install markitdown==0.1.8` (not `markitdown[all]`, which can pin an Azure pre-release)
3. `pipx inject`: `pillow`, `pytesseract`, `pypdf`, `pymupdf`, **`pymupdf4llm`**
4. Create `~/Scripts/ai-redact-venv`
5. Build and install the Swift Apple Intelligence helper
6. Copy scripts and the two Finder workflows, and rewrite paths for `$HOME`  
   (**Convert to Markdown** defaults to `MARKITDOWN_PDF_MODE=pymupdf4llm`)

After `./install.sh`, right-click a PDF, image, or other supported file. **Quick Actions** may not yet list **Convert to Markdown** or **AI Redact**. Open **Quick Actions → Customize…** and turn both items on.

If they still do not appear: **System Settings → Privacy & Security → Extensions → Finder**.

## Usage

1. Enable Apple Intelligence if you will use **AI Redact**
2. In Finder, select a PDF, image, or other supported file → right-click → **Quick Actions** → **Convert to Markdown** or **AI Redact** (use **Customize…** if they are missing)
3. Check the sibling output; on failure, check the notification and logs

CLI (same scripts as the Quick Actions):

```bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

# pipx markitdown venv Python (path varies by pipx; shebang is authoritative)
PY="$(awk 'NR==1 { sub(/^#!/, ""); print $1; exit }' "$(command -v markitdown)")"

"$PY" ~/Scripts/markitdown_qa.py ./some.pdf
"$PY" ~/Scripts/markitdown_qa.py ./photo.jpg

# Redaction
~/Scripts/ai-redact-venv/bin/python ~/Scripts/ai_redact.py ./some.pdf
```

Synthetic smoke-test input is in `samples/demo-contact-list.txt`. Do not commit real documents or `*_redacted.md` output.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `MARKITDOWN_PDF_MODE` | `pymupdf4llm` | `pymupdf4llm` \| `vision` \| `text` \| `auto` |
| `MARKITDOWN_PDF_CHARS_PER_PAGE` | `200` | `auto` mode: average chars/page below this → vision |
| `MARKITDOWN_PDF_VISION_DPI` | `180` | Full-page render DPI |
| `APPLE_REDACT_HELPER` | `~/Scripts/apple-redact-worker` | Override the Swift helper path |
| `REDACT_CHUNK_CHARS` | `2500` | Max characters per Apple Intelligence chunk (on-device context is small) |

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
- Image → Apple visual understanding; Tesseract fallback when Apple Intelligence is unavailable
- Convert still succeeds on a Mac without Apple Intelligence; AI Redact should fail clearly in English

## Security, privacy and limitations

- Apple may run some requests on-device and some via Private Cloud Compute. There are no third-party model hosts in this toolkit.
- AI-assisted redaction can miss, misclassify, or alter sensitive information.
- Always manually review outputs before sharing or uploading.
- Do not commit input files, logs, generated output, credentials, certificates, or real redacted documents.
- Do not treat this toolkit as legal, compliance, security, or data-protection advice.
- The project does not claim PCI, HIPAA, GDPR, HKMA, school-policy, or other regulatory compliance.
- Model weights are not bundled.
- Apple Silicon is the supported path; Intel Macs may need `/usr/local` instead of `/opt/homebrew`.

## Third-party components

This project integrates or invokes third-party tools and libraries, including
Microsoft MarkItDown, PyMuPDF, pymupdf4llm, Tesseract, ExifTool,
FFmpeg, and Python packages, plus Apple Foundation Models / Vision. These
components are distributed under their own licenses and terms. Users are
responsible for reviewing and complying with those licenses and terms.

## License

MIT — see [LICENSE](./LICENSE).
