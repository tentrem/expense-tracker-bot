import json
import os
import sqlite3
from datetime import datetime

from telegram import Bot, KeyboardButton, ReplyKeyboardMarkup

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS
from constants import CATEGORIES, LOCAL_CHART_PATH, LOCAL_SETTINGS_PATH, RECEIPTS_DIR


bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Will be set from main.py after DB_PATH is known
_db_path = None


def init_db(db_path):
    global _db_path
    _db_path = db_path
    _ensure_schema()


def _get_db():
    if not _db_path:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema():
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'default',
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'IDR',
            category TEXT,
            description TEXT,
            merchant TEXT,
            date DATE,
            receipt_image_path TEXT,
            ocr_raw_text TEXT,
            source TEXT DEFAULT 'manual',
            is_deleted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'default',
            category TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            spent REAL NOT NULL DEFAULT 0,
            UNIQUE(user_id, category)
        )
    """)
    conn.commit()
    conn.close()


def build_keyboard(options, buttons_per_row=3):
    keyboard = []
    row = []
    for i, option in enumerate(options):
        row.append(KeyboardButton(option))
        if (i + 1) % buttons_per_row == 0 or i == len(options) - 1:
            keyboard.append(row)
            row = []
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)


def load_settings():
    default_settings = {
        "google_sync": {"enabled": False, "last_upload": None},
        "budget_notifications": {"enabled": False},
    }
    if not os.path.exists(LOCAL_SETTINGS_PATH):
        settings = default_settings
        with open(LOCAL_SETTINGS_PATH, "w") as f:
            json.dump(settings, f)
    else:
        with open(LOCAL_SETTINGS_PATH, "r") as f:
            settings = json.load(f)
            if "google_sync" not in settings:
                settings["google_sync"] = default_settings["google_sync"]
            if "budget_notifications" not in settings:
                settings["budget_notifications"] = default_settings["budget_notifications"]
            save_settings(settings)
    return settings


def save_settings(settings):
    with open(LOCAL_SETTINGS_PATH, "w") as f:
        json.dump(settings, f)


def save_expense(user_id, amount, category, description, merchant, date, source="manual",
                 receipt_image_path=None, ocr_raw_text=""):
    conn = _get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """INSERT INTO expenses (user_id, amount, currency, category, description, merchant,
           date, receipt_image_path, ocr_raw_text, source, created_at, updated_at)
           VALUES (?, ?, 'IDR', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, float(amount), category, description, merchant, date,
         receipt_image_path, ocr_raw_text, source, now, now),
    )
    conn.commit()
    expense_id = cursor.lastrowid
    conn.close()
    return expense_id


def get_expenses(user_id=None, category=None, date_from=None, date_to=None, limit=50):
    conn = _get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM expenses WHERE is_deleted = 0"
    params = []

    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)

    if category:
        query += " AND category = ?"
        params.append(category)
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)

    query += " ORDER BY date DESC, created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_expense_by_id(expense_id, user_id=None):
    conn = _get_db()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ? AND is_deleted = 0",
                       (expense_id, user_id))
    else:
        cursor.execute("SELECT * FROM expenses WHERE id = ? AND is_deleted = 0",
                       (expense_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_expense(expense_id, user_id=None):
    conn = _get_db()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute(
            "UPDATE expenses SET is_deleted = 1, updated_at = ? WHERE id = ? AND user_id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expense_id, user_id),
        )
    else:
        cursor.execute(
            "UPDATE expenses SET is_deleted = 1, updated_at = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expense_id),
        )
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def update_expense(expense_id, user_id=None, **kwargs):
    allowed = {"amount", "category", "description", "merchant", "date"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expense_id]
    where = "WHERE id = ?"
    if user_id is not None:
        where += " AND user_id = ?"
        values.append(user_id)

    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE expenses SET {set_clause}, updated_at = ? {where}",
        values,
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def is_expenses_empty(user_id=None):
    return len(get_expenses(user_id, limit=1)) == 0


def set_budget(category, budget):
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO budgets (user_id, category, amount, spent) VALUES ('default', ?, ?, 0) "
        "ON CONFLICT(user_id, category) DO UPDATE SET amount = ?",
        (category, float(budget), float(budget)),
    )
    conn.commit()
    conn.close()


def get_budget(category):
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT amount, spent FROM budgets WHERE user_id = 'default' AND category = ?",
        (category,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return float(row["amount"]), float(row["spent"])
    return 0.0, 0.0


def update_spent(category=None):
    """Recalculate spent for a category from expenses table (all users)."""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT COALESCE(SUM(amount), 0) as total FROM expenses
           WHERE category = ? AND is_deleted = 0""",
        (category,),
    )
    total = cursor.fetchone()["total"]
    cursor.execute(
        """INSERT INTO budgets (user_id, category, amount, spent) VALUES ('default', ?, 0, ?)
           ON CONFLICT(user_id, category) DO UPDATE SET spent = ?""",
        (category, float(total), float(total)),
    )
    conn.commit()
    conn.close()


async def check_budget(category):
    settings = load_settings()
    if not settings["budget_notifications"]["enabled"]:
        return

    budget, spent = get_budget(category)
    if spent > budget > 0:
        message = (
            f"Peringatan ️\n\nAnggaran <u>{category}</u> melebihi batas\n"
            f"Pengeluaran: Rp {spent:,.0f} | Anggaran: Rp {budget:,.0f}\n"
            f"Terlampaui <b>Rp {spent - budget:,.0f}</b>"
        )
        for uid in TELEGRAM_ALLOWED_USERS:
            try:
                await bot.send_message(chat_id=uid, text=message, parse_mode="HTML")
            except Exception:
                pass


def get_current_budget(category):
    budget, _ = get_budget(category)
    return budget


def get_all_budgets():
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT category, amount, spent FROM budgets WHERE user_id = 'default' ORDER BY category",
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def ensure_charts_path():
    if not os.path.exists(LOCAL_CHART_PATH):
        os.makedirs(LOCAL_CHART_PATH, exist_ok=True)


def ensure_receipts_dir():
    if not os.path.exists(RECEIPTS_DIR):
        os.makedirs(RECEIPTS_DIR, exist_ok=True)
