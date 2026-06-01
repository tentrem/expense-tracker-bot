# Expense Tracker Bot

Telegram bot untuk tracking pengeluaran keluarga secara bersama (group chat).

## Fitur

- **Manual input**: `Tambah` → pilih kategori → isi deskripsi/jumlah → pilih tanggal → konfirmasi
- **Quick-add text**: Ketik dari menu utama seperti `Makan siang 50k di Indomaret` → auto parse amount + category
- **Bulk multi-line input**: Paste beberapa baris sekaligus dari menu utama → preview → konfirmasi batch
- **Photo OCR**: Kirim foto struk → Tesseract OCR → auto extract amount + category
- **Riwayat**: Summary pengeluaran per bulan (semua anggota keluarga)
- **Grafik**: Pie, Histogram, Trend, Heatmap untuk 3 bulan terakhir
- **Edit**: Edit amount, category, description, merchant, date
- **Hapus**: Soft delete (`is_deleted=1`) + undo
- **Anggaran**: Set budget per kategori (shared), notifikasi saat melebihi batas
- **Export**: Download `.xlsx`
- **Multi-user**: Allowlist di `.env`, data shared di group chat

## Application Flow

```text
/start → Allowlist check → Main menu

Main menu:
- ✏️ Tambah
- ❌ Hapus
- 📊 Grafik
- 📋 Riwayat
- 💰 Anggaran
- 📤 Export
- 📝 Edit
- ⚙️ Pengaturan

Tambah:
- 📝 Manual → pilih kategori → isi deskripsi/jumlah → pilih tanggal → konfirmasi → simpan
- 📷 Foto → kirim struk → OCR → parse → konfirmasi → simpan

Quick-add dari menu utama:
- single-line text → parse amount + category + merchant → konfirmasi → simpan
- multi-line text → parse semua baris → preview batch → konfirmasi → simpan banyak expense

Lainnya:
- ❌ Hapus → soft delete + undo
- 📊 Grafik → Pie / Histogram / Trend / Heatmap (3 bulan terakhir)
- 📋 Riwayat → monthly summary text
- 💰 Anggaran → Set / Show
- 📤 Export → file `.xlsx`
- 📝 Edit → pilih expense → pilih field → update
- ⚙️ Pengaturan → Google Sheets sync, budget notifications
- /cancel → reset flow dengan aman
```

## Architecture

```
Telegram Bot (python-telegram-bot v21.1.1)
├─ main.py          — Entry point, ConversationHandler (19 states)
├─ handlers.py      — Async handlers (UI flow, quick-add, bulk input, parsing)
├─ utils.py         — SQLite helpers, budget, settings
├─ ocr_handler.py   — Tesseract OCR (subprocess, Python 3.11 venv)
├─ charts.py        — matplotlib charts (Pie, Histogram, Trend, Heatmap)
├─ export.py        — pandas → .xlsx export
├─ config.py        — Env vars, DB_PATH, allowlist
├─ constants.py     — States, categories, keyboard layout
├─ requirements.txt
└─ requirements-ocr.txt
```

## Data Storage

| Item | Path |
|------|------|
| SQLite DB | `bot/expenses.db` |
| Receipt images | `bot/receipts/` |
| Charts | `bot/charts/` |
| Settings | `bot/settings.json` |
| Export | `bot/spreadsheets/` |

## Database Schema

```sql
expenses (
  id, user_id, amount, currency, category, description, merchant,
  date, receipt_image_path, ocr_raw_text, source, is_deleted, created_at, updated_at
)

budgets (
  id, user_id, category, amount, spent
)
```

- `user_id` stored on save for audit trail (siapa yang input)
- `is_deleted=1` for soft deletes
- All queries filter `WHERE is_deleted = 0`
- Budget shared: `user_id='default'` untuk semua kategori

## Setup

### 1. Main app

```bash
cd ~/Projects/expense-tracker/bot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Config
cp .env.example .env
# Edit .env: add TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS
```

### 2. OCR environment

`src/ocr_handler.py` runs OCR via separate Python 3.11 env at `venv_ocr/`.

Install system Tesseract first, then create OCR env:

```bash
python3.11 -m venv venv_ocr
source venv_ocr/bin/activate
pip install -r requirements-ocr.txt
```

Make sure `tesseract` binary is available in PATH, or installed in one of these common paths used by `ocr_handler.py`:
- `/home/linuxbrew/.linuxbrew/bin/tesseract`
- `/opt/homebrew/bin/tesseract`
- `/usr/bin/tesseract`

### 3. Run bot

```bash
source venv/bin/activate
PYTHONPATH=src python3 src/main.py
```

## Categories (10)

| Kategori | Keywords |
|----------|----------|
| Food | makan, minum, indomaret, alfamart, gofood, grabfood |
| Transport | gojek, grab, ojek, bus, bensin, parkir |
| Shopping | belanja, tokopedia, shopee, lazada |
| Bills | listrik, air, internet, pulsa, bpjs |
| Entertainment | nonton, game, spotify, netflix |
| Health | obat, dokter, rs, klinik |
| Education | buku, kursus, sekolah |
| Housing | sewa, kos, rumah, gas |
| Communication | telkom, indihome, xl, telkomsel |
| Other | fallback |

## Notes

- **Shared expense**: Semua anggota keluarga lihat semua expense (Riwayat, Charts, Export)
- **Allowlist**: Hanya user di `TELEGRAM_ALLOWED_USERS` yang bisa `/start`
- **OCR**: Tesseract via subprocess (Python 3.11 venv di `venv_ocr/`)
- **`venv_ocr/` is not committed**: create it locally with `requirements-ocr.txt`
- **Quick-add**: text input langsung dari menu utama, tidak ada menu `Teks` terpisah
- **Bulk input**: multi-line text dari menu utama diproses sebagai batch
- **Charts**: filter otomatis 3 bulan terakhir; file PNG dibersihkan setelah dikirim
- **Group chat**: BotFather `/setprivacy` → Disable agar bot baca semua message
