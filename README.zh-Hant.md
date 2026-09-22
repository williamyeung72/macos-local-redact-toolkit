# macOS Local Redact Toolkit

本機、離線優先的 macOS [Finder 快速操作](https://support.apple.com/guide/mac-help/mchl7ab36458/mac)：把檔案轉成 Markdown，並用本機 **Ollama** 產生 **塗改草稿**（redaction draft）。除非你自己的環境另有設定，否則不會把檔案上傳到雲端轉換服務。

目標平台：**Apple Silicon**（M 系列 Mac）。

產品表面（Finder 選單、通知、安裝腳本、程式註解、模型 prompt）全部是**英文**。這份文件只說明同一個英文產品。

英文主文件：[README.md](./README.md)

> [!WARNING]
> 本工具產出的是 AI 輔助的塗改草稿，**不是**完整匿名化、私隱保護或法律合規的保證。分享、上傳或倚賴輸出前，必須人手覆核。
>
> 不要把它當成受規管、法律、醫療、金融、僱傭、學校或安全關鍵文件的唯一控制措施。

## 快速操作

兩個 Finder 動作互相獨立，可以分開使用。選單名稱是英文：

| Quick Action | 做什麼 | 輸出 |
| --- | --- | --- |
| **Convert to Markdown** | 文件／圖片 → Markdown | 同目錄 `*.md` |
| **Ollama AI Redact** | 優先轉 MD，再用本機文字模型塗改 | `*_redacted.md` |

**塗改**是指：在**新檔**裡把敏感字元換成可重覆的 typed placeholder（例如 `[PERSON_1]`、`[EMAIL_2]`）。**不會改原檔**，也不是不可逆匿名化，更不是把 PDF 塗黑。

### Convert to Markdown 路徑

| 類型 | 預設行為 |
| --- | --- |
| **PDF** | **`pymupdf4llm`**（本機；不上雲轉換） |
| PDF（可選） | `MARKITDOWN_PDF_MODE=vision` → 整頁 Ollama vision（`qwen3.5:4b`） |
| PDF（可選） | `text` = 純 PyMuPDF blocks；`auto` = 字少先 vision，否則 pymupdf4llm |
| **Office**（docx／pptx／xlsx） | `markitdown-ocr` + Ollama（Ollama 掛唔到則退回 MarkItDown） |
| **圖片** | EXIF／meta（MarkItDown）+ Ollama vision；失敗先 Tesseract |
| 其他 | Microsoft MarkItDown |

### Ollama AI Redact 路徑

1. 非圖片：盡量先轉成 `.md`（經 MarkItDown／上述 PDF 邏輯）
2. 用 `llama3.1` 對 Markdown 做塗改 → `*_redacted.md`
3. 轉唔到有用內容時，圖片才用 vision 模型
4. **塗改結果必須人手覆核**先傳出／上雲

## 專案結構

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

安裝後實際落點：

- 腳本：`~/Scripts/markitdown_qa.py`、`~/Scripts/ollama_redact.py`
- 塗改 venv：`~/Scripts/ollama-redact-venv`
- Quick Actions：`~/Library/Services/`
- 日誌：`~/Library/Logs/markitdown-qa.log`、`ollama-redact.log`、`ollama-redact-install.log`

Git 裡的 `.workflow` 用 `$HOME` 作 placeholder。`install.sh` 會把安裝到本機的副本改寫成你這部 Mac 的絕對路徑。只 clone、未跑安裝程式，Quick Action 不能直接用。

## 先決條件

1. macOS **Apple Silicon**（arm64）
2. [Homebrew](https://brew.sh)
3. [Ollama](https://ollama.com) 已安裝並可執行
4. （安裝腳本會裝）`pipx`、`ffmpeg`、`tesseract`、`exiftool`

## 安裝

```bash
cd /path/to/macos-local-redact-toolkit
chmod +x install.sh
./install.sh
```

`install.sh` 會：

1. 確認／安裝 brew 依賴（`pipx`、`ffmpeg`、`tesseract`、`exiftool`；可選 `tesseract-lang`）
2. `pipx install markitdown==0.1.8`（唔用 `markitdown[all]`，避免 Azure pre-release 鎖死）
3. `pipx inject`：`markitdown-ocr`、`openai`、`pillow`、`pytesseract`、`pypdf`、`pymupdf`、**`pymupdf4llm`**
4. 建立 `~/Scripts/ollama-redact-venv` 並裝 `ollama`、`pymupdf` 等
5. 複製 scripts + 兩個 Finder workflow，並按本機 `$HOME` 改寫路徑  
   （**Convert to Markdown** 預設 `MARKITDOWN_PDF_MODE=pymupdf4llm`）

然後拉模型（唔打包權重）：

```bash
ollama pull llama3.1:latest
ollama pull qwen3.5:4b
```

跑完 `./install.sh` 之後，對 PDF、圖片或其他支援檔案按右鍵。**Quick Actions** 裡可能暫時未見 **Convert to Markdown** 同 **Ollama AI Redact**。打開 **Quick Actions → Customize…**，把兩個項目打開。

若仍然沒有：**系統設定 → 私隱與保安 → 延伸功能 → Finder**。

## 使用

1. 開住 **Ollama**
2. Finder 選 PDF、圖片或其他支援檔案 → 右鍵 → **Quick Actions** → **Convert to Markdown** 或 **Ollama AI Redact**（未見就先 **Customize…**）
3. 睇同目錄產出；失敗睇通知同日誌

命令列（同 Quick Action 同一支腳本）：

```bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
export OLLAMA_HOST="http://127.0.0.1:11434"

# 用 pipx markitdown venv 嘅 Python
PY="$HOME/Library/Application Support/pipx/venvs/markitdown/bin/python"

"$PY" ~/Scripts/markitdown_qa.py ./some.pdf
"$PY" ~/Scripts/markitdown_qa.py ./photo.jpg

# 塗改
~/Scripts/ollama-redact-venv/bin/python ~/Scripts/ollama_redact.py ./some.pdf
```

合成測試檔在 `samples/demo-contact-list.txt`。不要 commit 真實文件或 `*_redacted.md` 輸出。

## 環境變數

| 變數 | 預設 | 說明 |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | 腳本會把 `0.0.0.0` 正規化成 `127.0.0.1` |
| `MARKITDOWN_PDF_MODE` | `pymupdf4llm` | `pymupdf4llm` \| `vision` \| `text` \| `auto` |
| `MARKITDOWN_LLM_MODEL` | `qwen3.5:4b` | Vision／OCR 用模型 |
| `MARKITDOWN_PDF_CHARS_PER_PAGE` | `200` | `auto` 模式：平均字元／頁低於此 → vision |
| `MARKITDOWN_PDF_VISION_DPI` | `180` | 整頁 render DPI |

## 點解 PDF 預設係 pymupdf4llm？

多欄評分表／時間表用純文字抽取或細 vision model 時，閱讀順序容易散。

對於部分含多欄文字、時間表或表格式 PDF，pymupdf4llm 在本機測試中通常較純文字抽取保留較佳的閱讀順序與結構；實際效果會因文件而異，請人手覆核。真掃描件或圖多頁再用 `MARKITDOWN_PDF_MODE=vision`。

## 開發／維護

改完 script 後：

1. 複製去 `~/Scripts/`（或重跑 `./install.sh`）
2. 若改 workflow 預設環境變數，同步 `services/*.workflow` 或靠 `install.sh` 重寫

可選 zip：

```bash
cd ..
ditto -c -k --sequesterRsrc --keepParent macos-local-redact-toolkit macos-local-redact-toolkit.zip
```

煙測建議：

- 文字／表格 PDF → 確認日誌有 `PDF path=pymupdf4llm`，欄位順序用人眼睇
- 圖片 → Ollama vision；Ollama 關機時應有 Tesseract fallback
- `markitdown --list-plugins` 應見 `ocr`

## 保安、私隱與限制

- 設計為本機處理。處理敏感資料前，請確認你自己的網絡、Ollama 與依賴設定。
- Ollama 輔助塗改可能漏掉、誤判或改錯敏感資訊。
- 分享或上傳前必須人手覆核輸出。
- 不要 commit 輸入檔、日誌、產出、憑證、證書或真實塗改文件。
- 本工具不是法律、合規、保安或資料保護意見。
- 不宣稱符合 PCI、HIPAA、GDPR、HKMA、學校政策或其他監管要求。
- 不打包 Ollama 模型權重。
- 主要針對 Apple Silicon；Intel Mac 路徑可能要改 `/usr/local`。

## 第三方元件

本專案會整合或呼叫 Ollama、Microsoft MarkItDown、PyMuPDF、pymupdf4llm、Tesseract、ExifTool、FFmpeg 及相關 Python 套件。這些元件各自有授權條款，使用者須自行遵守。

OpenAI Python client 只用嚟對本機 Ollama 做 OpenAI-compatible 介面（`api_key="ollama"` 係 dummy，不是雲端憑證）。

## 授權

MIT — 見 [LICENSE](./LICENSE)。
