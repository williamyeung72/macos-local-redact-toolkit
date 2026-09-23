# macOS Local Redact Toolkit

macOS [Finder 快速操作](https://support.apple.com/guide/mac-help/mchl7ab36458/mac)：把檔案轉成 Markdown，並用 **AI Redact** 產生塗改草稿（redaction draft）。推論走 **Apple 裝置端加上 Private Cloud Compute，沒有第三方模型主機。**

目標平台：**Apple Silicon**（M 系列 Mac）。**AI Redact** 需要 **macOS 26** 並已開啟 Apple Intelligence。**Convert to Markdown** 在沒有 Apple Intelligence 時仍可使用。

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
| **AI Redact** | 優先轉 MD，再用 Apple Intelligence 塗改 | `*_redacted.md` |

**塗改**是指：在**新檔**裡把敏感字元換成可重覆的 typed placeholder（例如 `[PERSON_1]`、`[EMAIL_2]`）。**不會改原檔**，也不是不可逆匿名化，更不是把 PDF 塗黑。每一份 `*_redacted.md` 都只是草稿，必須人手覆核。

若本機已裝過名為 **Ollama AI Redact** 的舊快速操作，安裝程式**不會刪除**它；新安裝改為加入 **AI Redact**。

### Convert to Markdown 路徑

| 類型 | 預設行為 |
| --- | --- |
| **PDF** | **`pymupdf4llm`**（本機表格式抽取） |
| PDF（可選） | `MARKITDOWN_PDF_MODE=vision` → 整頁 Apple 視覺理解 |
| PDF（可選） | `text` = 純 PyMuPDF blocks；`auto` = 字少先 vision，否則 pymupdf4llm |
| **Office**（docx／pptx／xlsx） | MarkItDown；內嵌圖片在可用時走 Apple 視覺理解 |
| **圖片** | EXIF／meta（MarkItDown）+ Apple 視覺理解；失敗先 Tesseract |
| 其他 | Microsoft MarkItDown |

### AI Redact 路徑

1. 非 Markdown：盡量先轉成 `.md`（經 MarkItDown／上述 PDF 邏輯）
2. 用 Apple Intelligence 對 Markdown 做塗改 → `*_redacted.md`
3. 沒有 Apple Intelligence 時，AI Redact 以英文失敗，並且不寫半成品草稿
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

安裝後實際落點：

- 腳本：`~/Scripts/markitdown_qa.py`、`~/Scripts/ai_redact.py`、`~/Scripts/apple_worker.py`
- Helper：`~/Scripts/apple-redact-worker`
- 塗改 venv：`~/Scripts/ai-redact-venv`
- Quick Actions：`~/Library/Services/`
- 日誌：`~/Library/Logs/markitdown-qa.log`、`ai-redact.log`、`ai-redact-install.log`

Git 裡的 `.workflow` 用 `$HOME` 作 placeholder。`install.sh` 會把安裝到本機的副本改寫成你這部 Mac 的絕對路徑。只 clone、未跑安裝程式，Quick Action 不能直接用。

## 先決條件

1. macOS **Apple Silicon**（arm64）
2. [Homebrew](https://brew.sh)
3. （安裝腳本會裝）`pipx`、`ffmpeg`、`tesseract`、`exiftool`
4. **AI Redact**：macOS 26+ 並已開啟 Apple Intelligence

## 安裝

```bash
cd /path/to/macos-local-redact-toolkit
chmod +x install.sh
./install.sh
```

`install.sh` 會：

1. 確認／安裝 brew 依賴（`pipx`、`ffmpeg`、`tesseract`、`exiftool`；可選 `tesseract-lang`）
2. `pipx install markitdown==0.1.8`（唔用 `markitdown[all]`，避免 Azure pre-release 鎖死）
3. `pipx inject`：`pillow`、`pytesseract`、`pypdf`、`pymupdf`、**`pymupdf4llm`**
4. 建立 `~/Scripts/ai-redact-venv`
5. 編譯並安裝 Swift Apple Intelligence helper
6. 複製 scripts + 兩個 Finder workflow，並按本機 `$HOME` 改寫路徑  
   （**Convert to Markdown** 預設 `MARKITDOWN_PDF_MODE=pymupdf4llm`）

跑完 `./install.sh` 之後，對 PDF、圖片或其他支援檔案按右鍵。**Quick Actions** 裡可能暫時未見 **Convert to Markdown** 同 **AI Redact**。打開 **Quick Actions → Customize…**，把兩個項目打開。

若仍然沒有：**系統設定 → 私隱與保安 → 延伸功能 → Finder**。

## 使用

1. 若要用 **AI Redact**，先開啟 Apple Intelligence
2. Finder 選 PDF、圖片或其他支援檔案 → 右鍵 → **Quick Actions** → **Convert to Markdown** 或 **AI Redact**（未見就先 **Customize…**）
3. 睇同目錄產出；失敗睇通知同日誌

命令列（同 Quick Action 同一支腳本）：

```bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

# 用 pipx markitdown venv 嘅 Python（路徑因 pipx 而異；以 shebang 為準）
PY="$(awk 'NR==1 { sub(/^#!/, ""); print $1; exit }' "$(command -v markitdown)")"

"$PY" ~/Scripts/markitdown_qa.py ./some.pdf
"$PY" ~/Scripts/markitdown_qa.py ./photo.jpg

# 塗改
~/Scripts/ai-redact-venv/bin/python ~/Scripts/ai_redact.py ./some.pdf
```

合成測試檔在 `samples/demo-contact-list.txt`。不要 commit 真實文件或 `*_redacted.md` 輸出。

## 環境變數

| 變數 | 預設 | 說明 |
| --- | --- | --- |
| `MARKITDOWN_PDF_MODE` | `pymupdf4llm` | `pymupdf4llm` \| `vision` \| `text` \| `auto` |
| `MARKITDOWN_PDF_CHARS_PER_PAGE` | `200` | `auto` 模式：平均字元／頁低於此 → vision |
| `MARKITDOWN_PDF_VISION_DPI` | `180` | 整頁 render DPI |
| `APPLE_REDACT_HELPER` | `~/Scripts/apple-redact-worker` | 覆寫 Swift helper 路徑 |
| `REDACT_CHUNK_CHARS` | `2500` | 每個 Apple Intelligence chunk 的字元上限（裝置端 context 有限） |

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
- 圖片 → Apple 視覺理解；沒有 Apple Intelligence 時應有 Tesseract fallback
- 沒有 Apple Intelligence 時 Convert 仍應成功；AI Redact 應以英文清楚失敗

## 保安、私隱與限制

- Apple 可能在裝置端或經 Private Cloud Compute 處理請求。本工具沒有第三方模型主機。
- AI 輔助塗改可能漏掉、誤判或改錯敏感資訊。
- 分享或上傳前必須人手覆核輸出。
- 不要 commit 輸入檔、日誌、產出、憑證、證書或真實塗改文件。
- 本工具不是法律、合規、保安或資料保護意見。
- 不宣稱符合 PCI、HIPAA、GDPR、HKMA、學校政策或其他監管要求。
- 不打包模型權重。
- 主要針對 Apple Silicon；Intel Mac 路徑可能要改 `/usr/local`。

## 第三方元件

本專案會整合或呼叫 Microsoft MarkItDown、PyMuPDF、pymupdf4llm、Tesseract、ExifTool、FFmpeg、相關 Python 套件，以及 Apple Foundation Models／Vision。這些元件各自有授權條款，使用者須自行遵守。

## 授權

MIT — 見 [LICENSE](./LICENSE)。
