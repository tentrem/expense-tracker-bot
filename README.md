# Expense Tracker Bot

Telegram bot untuk tracking pengeluaran keluarga secara bersama (group chat).

## Fitur

- **Manual input**: Pilih kategori → input jumlah
- **Text input**: Ketik "Makan siang 50k di Indomaret" → auto parse amount + category
- **Photo OCR**: Kirim foto struk → Tesseract OCR → auto extract amount + category
- **Riwayat**: Summary pengeluaran per bulan (semua anggota keluarga)
- **Grafik**: Pie, Histogram, Trend, Heatmap
- **Edit**: Edit amount, category, description, merchant, date
- **Hapus**: Soft delete (is_deleted=1)
- **Anggaran**: Set budget per kategori (shared), notifikasi saat melebihi batas
- **Export**: Download .xlsx
- **Multi-user**: Allowlist di `.env`, data shared di group chat

## Application Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  Telegram Group Chat                                            │
│                                                                 │
│  User → /start                                                  │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────────┐                                            │
│  │  Allowlist Check│ ─── not in list → "Kamu tidak berhak"      │
│  │ (config.py)     │ ─── in list → show menu                    │
│  └────────────────┘                                            │
│           ▼                                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Main Menu (constants.py:reply_keyboard)                 │  │
│  │  ✏️ Tambah  ❌ Hapus  📊 Grafik                          │  │
│  │  📋 Riwayat  💰 Anggaran  📤 Export   Edit             │  │
│  └──────┬───────────────────────────────────────────────────┘  │
│         │                                                      │
│  ┌──────┴────────────────────────────────────────────────────┐ │
│  │  ConversationHandler (main.py) — 16 states                 │ │
│  │                                                            │ │
│  │  Tambah → Input Type Selection                             │ │
│  │  │                                                        │ │
│  │  ├─ Manual  → Pilih Kategori → Input Jumlah               │ │
│  │  │   → handlers.py::save_on_local_db()                    │ │
│  │  │                                                        │ │
│  │  ├─ Teks    → Ketik "Makan 50k di Indomaret"             │ │
│  │  │   → handlers.py::handle_text_input()                   │ │
│  │  │   → _parse_amount()  (regex: 50k→50000, 1.5jt→1500000)│ │
│  │  │   → _match_category()  (keyword matching, 10 kategori) │ │
│  │  │                                                        │ │
│  │  └─ Foto    → Kirim struk                                 │ │
│  │      → handlers.py::handle_photo()                        │ │
│  │      → ocr_handler.py::run_ocr() (Tesseract, Python 3.11) │ │
│  │      → _parse_amount() + _match_category()                │ │
│  │      → Konfirmasi → save_expense()                        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────── │
│  │  utils.py — Data Layer (SQLite)                            │ │
│  │                                                            │ │
│  │  save_expense()    → INSERT INTO expenses (audit user_id)  │ │
│  │  get_expenses()    → SELECT ... WHERE is_deleted=0         │ │
│  │  delete_expense()  → UPDATE is_deleted=1 (soft delete)     │ │
│  │  update_expense()  → UPDATE amount/category/etc            │ │
│  │  set_budget()      → INSERT/UPDATE budgets (shared)        │ │
│  │  update_spent()    → Recalculate from expenses table       │ │
│  │  check_budget()    → Notify if spent > budget              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  charts.py — Grafik                                        │ │
│  │  pandas + matplotlib → PNG → send_photo()                  │ │
│  │  Pie, Histogram, Trend, Heatmap                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  export.py — Export                                        │ │
│  │  pandas → .xlsx → send_document()                          │ │
│  └──────────────────────────────────────────────────────────── │
└─────────────────────────────────────────────────────────────────┘
```

## Architecture

```
Telegram Bot (python-telegram-bot v21.1.1)
├─ main.py          — Entry point, ConversationHandler (16 states)
├─ handlers.py      — Async handlers (UI flow, amount/category parsing)
─ utils.py         — SQLite helpers, budget, settings
├─ ocr_handler.py   — Tesseract OCR (subprocess, Python 3.11 venv)
├─ charts.py        — matplotlib charts (Pie, Histogram, Trend, Heatmap)
├─ export.py        — pandas → .xlsx export
├─ config.py        — Env vars, DB_PATH, allowlist
├─ constants.py     — States, categories, keyboard layout
└─ requirements.txt
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

```bash
cd ~/Projects/expense-tracker/bot

# Config
cp .env.example .env
# Edit .env: add TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS

# Run
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
- **Group chat**: BotFather `/setprivacy` → Disable agar bot baca semua message
