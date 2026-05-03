import calendar
import datetime
import os
import re
import tempfile

import pandas as pd
from config import DB_PATH, ITEMS_PER_PAGE, TELEGRAM_ALLOWED_USERS, logger
from constants import (
    CATEGORIES,
    CHOOSING,
    CHOOSING_BUDGET,
    CHOOSING_BUDGET_AMOUNT,
    CHOOSING_BUDGET_CATEGORY,
    CHOOSING_CATEGORY,
    CHOOSING_CHART,
    CHOOSING_EDIT_FIELD,
    CHOOSING_INPUT_TYPE,
    CHOOSING_ITEM_TO_DELETE,
    CHOOSING_ITEM_TO_EDIT,
    CHOOSING_PRICE,
    EDITING_AMOUNT,
    EDITING_TEXT,
    WAITING_TEXT,
    WAITING_PHOTO,
    WAITING_PHOTO_CONFIRM,
    QUICK_ADD_CONFIRM,
    markup,
    input_type_keyboard,
)
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils import (
    build_keyboard,
    check_budget,
    delete_expense,
    ensure_receipts_dir,
    get_all_budgets,
    get_current_budget,
    get_expense_by_id,
    get_expenses,
    is_expenses_empty,
    load_settings,
    restore_expense,
    save_expense,
    save_settings,
    set_budget,
    update_expense,
    update_spent,
)

from charts import (
    save_heatmap,
    save_pie_chart,
    save_stacked_bar_chart,
    save_trend_chart,
)
from ocr_handler import run_ocr
from export import export_to_xlsx


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if str(update.effective_user.id) not in TELEGRAM_ALLOWED_USERS:
        await update.message.reply_text("Kamu tidak berhak. Minta admin untuk akses. ⛔")
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "Halo! Saya expense tracker. Mau apa hari ini?", reply_markup=markup
    )
    return CHOOSING


# --- Input Type Selection ---
async def ask_input_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Pilih cara input:", reply_markup=input_type_keyboard)
    return CHOOSING_INPUT_TYPE


async def handle_input_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text
    if choice == "📝 Manual":
        return await ask_category(update, context)
    elif choice == "💬 Teks":
        await update.message.reply_text(
            "Ketik pengeluaran, contoh: 'Makan siang 50k di Indomaret'"
        )
        return WAITING_TEXT
    elif choice == "📷 Foto":
        await update.message.reply_text("Kirim foto struk:")
        return WAITING_PHOTO
    return await handle_unexpected_message(update, context)


# --- Photo Input (OCR) ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            temp_path = tmp.name

        await update.message.reply_text("Memproses foto... ⏳")

        ocr_result = run_ocr(temp_path)
        if not ocr_result.get("success"):
            error_msg = ocr_result.get("error", "OCR gagal")
            await update.message.reply_text(f"OCR error: {error_msg}", reply_markup=markup)
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            return CHOOSING

        ocr_text = ocr_result.get("full_text", "")
        logger.info(f"OCR text: {ocr_text}")

        amount = _parse_amount(ocr_text)
        category = _match_category(ocr_text)
        merchant = _detect_merchant(ocr_text)

        context.user_data["ocr_amount"] = amount
        context.user_data["ocr_category"] = category
        context.user_data["ocr_merchant"] = merchant
        context.user_data["ocr_text"] = ocr_text
        context.user_data["ocr_temp_path"] = temp_path

        merchant_line = f"\n<b>Merchant:</b> {merchant}\n" if merchant else ""

        if amount is not None:
            confirm_msg = (
                f"<b>Hasil OCR:</b>\n\n"
                f"<b>Jumlah:</b> Rp {amount:,.0f}\n"
                f"<b>Kategori:</b> {category}\n"
                f"{merchant_line}"
                f"Ketik <b>ya</b> untuk simpan, atau edit jumlah (contoh: '50000'):"
            )
        else:
            confirm_msg = (
                f"<b>Hasil OCR:</b>\n\n"
                f"Tidak bisa menentukan jumlah.\n"
                f"<b>Kategori:</b> {category}\n"
                f"{merchant_line}"
                f"Ketik jumlah (contoh: '50000'):"
            )

        await update.message.reply_text(confirm_msg, parse_mode="HTML")
        return WAITING_PHOTO_CONFIRM

    except Exception as e:
        logger.error(f"Photo handling error: {e}")
        await update.message.reply_text(f"Gagal memproses foto: {e}", reply_markup=markup)
        return CHOOSING


async def handle_photo_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    user_id = str(update.effective_user.id)

    try:
        amount = context.user_data.get("ocr_amount")
        category = context.user_data.get("ocr_category", "Other")
        merchant = context.user_data.get("ocr_merchant")
        ocr_text = context.user_data.get("ocr_text", "")
        temp_path = context.user_data.get("ocr_temp_path")

        if text == "ya":
            if amount is None:
                await update.message.reply_text("Jumlah tidak valid. Coba lagi.", reply_markup=markup)
                return CHOOSING
        else:
            parsed = _parse_amount(text)
            if parsed is not None:
                amount = parsed
            else:
                try:
                    amount = float(text.replace(".", "").replace(",", "."))
                except ValueError:
                    await update.message.reply_text("Jumlah tidak valid. Coba lagi.", reply_markup=markup)
                    return CHOOSING

        expense_id = save_expense(
            user_id=user_id,
            amount=amount,
            category=category,
            description="Receipt scan",
            merchant=merchant,
            date=datetime.datetime.now().strftime("%Y-%m-%d"),
            source="ocr",
            receipt_image_path=temp_path,
            ocr_raw_text=ocr_text,
        )

        if temp_path and os.path.exists(temp_path):
            ensure_receipts_dir()
            dest = f"./receipts/receipt_{expense_id}.jpg"
            try:
                os.rename(temp_path, dest)
            except OSError:
                pass

        update_spent(category)
        await check_budget(category)

        await update.message.reply_text(
            f"<b>Tercatat </b>\n\n"
            f"<b>Kategori:</b> {category}\n"
            f"<b>Jumlah:</b> Rp {amount:,.0f}\n"
            f"<b>Sumber:</b> Foto (OCR)\n"
            f"<b>ID:</b> {expense_id}",
            parse_mode="HTML",
            reply_markup=markup,
        )

    except Exception as e:
        logger.error(f"Photo confirm error: {e}")
        await update.message.reply_text(f"Gagal menyimpan: {e}", reply_markup=markup)

    return CHOOSING


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    parsed = _parse_amount(text)
    if parsed is None:
        await update.message.reply_text(
            "Tidak bisa menemukan jumlah. Coba format: 'Makan 50k', 'Rp 50.000', '100000'",
            reply_markup=markup,
        )
        return CHOOSING

    category = _match_category(text)
    context.user_data["text_amount"] = parsed
    context.user_data["text_category"] = category
    context.user_data["text_description"] = text

    confirm_msg = (
        f"<b>Simpan pengeluaran?</b>\n\n"
        f"<b>Jumlah:</b> Rp {parsed:,.0f}\n"
        f"<b>Kategori:</b> {category}\n"
        f"<b>Catatan:</b> {text}\n\n"
        f"Ketik <b>ya</b> untuk simpan, <b>cancel</b> untuk batal, "
        f"atau ketik jumlah baru (contoh: '75000'):"
    )
    await update.message.reply_text(confirm_msg, parse_mode="HTML")
    return WAITING_TEXT_CONFIRM


async def handle_text_input_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()

    if text == "cancel" or text == "/cancel":
        context.user_data.clear()
        await update.message.reply_text("Dibatalkan.", reply_markup=markup)
        return CHOOSING

    amount = context.user_data.get("text_amount")
    category = context.user_data.get("text_category", "Other")
    description = context.user_data.get("text_description", "")

    if text != "ya":
        parsed = _parse_amount(text)
        if parsed is not None:
            amount = parsed
        else:
            try:
                amount = float(text.replace(".", "").replace(",", "."))
            except ValueError:
                await update.message.reply_text("Jumlah tidak valid. Coba lagi.", reply_markup=markup)
                return CHOOSING

    user_id = str(update.effective_user.id)
    expense_id = save_expense(
        user_id=user_id,
        amount=amount,
        category=category,
        description=description,
        merchant=None,
        date=datetime.datetime.now().strftime("%Y-%m-%d"),
        source="text",
    )

    update_spent(category)
    await check_budget(category)

    await update.message.reply_text(
        f"<b>Tercatat ✅</b>\n\n"
        f"<b>Kategori:</b> {category}\n"
        f"<b>Jumlah:</b> Rp {amount:,.0f}\n"
        f"<b>Catatan:</b> {description}\n"
        f"<b>ID:</b> {expense_id}",
        parse_mode="HTML",
        reply_markup=markup,
    )

    context.user_data.clear()
    return CHOOSING


def _parse_amount(text: str) -> float | None:
    """Parse amount from Indonesian text input."""
    lines = text.lower().split('\n')

    # Priority 1: Look for "total belanja" line
    for line in lines:
        if 'total belanja' in line:
            # Extract all digits and separators, then clean
            match = re.search(r'(\d[\d\s.,]*)', line)
            if match:
                raw = match.group(1).replace(".", "").replace(" ", "")
                # Indonesian format: comma is thousands separator (129,800 = 129800)
                raw = raw.replace(",", "")
                return float(raw) if raw else None

    # Priority 2: Look for "total" line (but not "total disc" or "total item")
    for line in lines:
        if 'total' in line and 'disc' not in line and 'item' not in line:
            match = re.search(r'(\d[\d\s.,]*)', line)
            if match:
                raw = match.group(1).replace(".", "").replace(" ", "")
                raw = raw.replace(",", "")
                return float(raw) if raw else None

    # Fallback: original patterns
    match = re.search(r'(\d+)\s*k\b', text, re.IGNORECASE)
    if match:
        return float(match.group(1)) * 1000

    match = re.search(r'([\d.,]+)\s*(jt|juta)\b', text, re.IGNORECASE)
    if match:
        val = float(match.group(1).replace(",", "."))
        return val * 1_000_000

    match = re.search(r'\b(?:rp\.?\s*)?(\d{1,3}(?:[\s.]\d{3})*(?:,\s*\d{2})?|\d{4,})\b', text, re.IGNORECASE)
    if match:
        raw = match.group(1)
        if "." in raw:
            return float(raw.replace(".", ""))
        val = float(raw)
        if val <= 100:
            return val
        return val

    return None


def _match_category(text: str) -> str:
    """Match text to a category based on keywords.
    Scan order matters: longer/more-specific keywords first to avoid false matches
    (e.g. 'grabfood' before 'grab').
    """
    text_lower = text.lower()

    # Context-aware: alfamart/indomaret with food context → Food, otherwise Shopping
    shopping_markers = ["alfamart", "indomaret", "supermarket", "pasar"]
    food_context = any(w in text_lower for w in ["makan", "nasi", "minum", "jajanan", "cemilan", "snack", "kopi", "teh", "mie", "bakso", "soto"])
    has_shopping_marker = any(m in text_lower for m in shopping_markers)
    if has_shopping_marker and not food_context:
        # Defer: will be caught by Shopping keywords below
        pass

    # Category keywords — order matters within each category
    keywords = {
        "Food": [
            "makanan", "minuman", "rumah makan", "warung makan",
            "resto", "restaurant", "warteg", "kantin", "warung", "resto",
            "makan", "minum", "nasi", "mie", "indomie", "bakso", "soto",
            "gorengan", "jajanan", "cemilan", "snack", "es krim", "coklat",
            "kopi", "teh", "susu", "roti",
            "delivery", "gofood", "grabfood", "grab food", "shopeefood",
            "catering", "cater",
        ],
        "Transport": [
            "kereta api", "pesawat",
            "gojek", "grab", "ojol", "ojek",
            "bus", "angkot", "travel", "damri",
            "taxi", "taksi", "bensin", "bbm",
            "parkir", "tol", "toll",
            "motor", "mobil", "service motor", "cuci motor",
            "flight",
        ],
        "Shopping": [
            "tokopedia", "shopee", "lazada", "blibli", "bukalapak",
            "alfamart", "indomaret", "alfamidi", "supermarket", "pasar",
            "baju", "kaos", "celana", "sepatu", "tas",
            "gadget", "hp", "handphone", "laptop", "elektronik",
            "skincare", "kosmetik",
            "furnitur", "furniture", "perabot",
            "belanja", "mall",
        ],
        "Bills": [
            "listrik", "pln", "air", "pdam",
            "internet", "wifi", "modem", "router",
            "pulsa", "data", "hp", "telpon",
            "bpjs", "asuransi",
            "tagihan", "iuran", "denda",
            "cicilan", "kredit", "kpr", "spaylater", "paylater",
            "dana", "ovo", "gopay", "shopeepay", "qris",
        ],
        "Entertainment": [
            "hiburan", "nonton", "bioskop", "karaoke",
            "game", "konser", "tiket",
            "wisata", "liburan", "jalan-jalan",
            "spotify", "youtube", "netflix",
        ],
        "Health": [
            "dokter", "klinik", "rs ", "rs.", "rumah sakit",
            "obat", "apotek", "vitamin", "suplemen",
            "masker", "handsanitizer", "sanitasi",
            "sehat", "kesehatan",
        ],
        "Education": [
            "sekolah", "kuliah", "universitas",
            "buku", "kursus", "belajar",
            "les", "bimbel", "seminar", "workshop",
        ],
        "Housing": [
            "sewa", "kos", "rumah", "gas", "furniture",
            "cat", "renovasi", "perbaikan", "tukang", "kuli",
        ],
        "Communication": [
            "telkom", "indihome", "telkomsel",
            "xl", "indosat", "tri", "axis",
            "modem", "router", "wifi id",
        ],
        "Other": [
            "donasi", "zakat", "infak", "sedekah",
            "hadiah", "kado",
        ],
    }

    for cat, words in keywords.items():
        for word in words:
            if word in text_lower:
                return cat
    return "Other"


def _detect_merchant(ocr_text: str) -> str:
    """Detect merchant name from OCR text. Look for known store names in first few lines."""
    known_merchants = [
        "indomaret", "alfamart", "alfamidi", "hypermart", "carrefour",
        "lottemart", "transmart", "hero", "giant", "superindo",
        "starbucks", "jco", "chatime", "kopi kenangan", "janji jiwa",
        "mcdonalds", "kfc", "pizza hut", "domino", "burger king",
        "warteg", "warung makan", "rumah makan", "resto", "cafe",
        "tokopedia", "shopee", "lazada", "blibli", "bukalapak",
        "grab", "gojek", "grabfood", "gofood",
        "apotek k-24", "apotek", "kimia farma", "guardian", "watson",
        "telkom", "telkomsel", "xl", "indosat", "tri", "axis",
        "pln", "pdam", "bpjs", "prudential", "manulife",
    ]
    for merchant in known_merchants:
        if merchant in ocr_text.lower():
            return merchant.title()
    return None


# --- Manual Input: Category Selection ---
async def ask_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cat_buttons = build_keyboard(CATEGORIES, buttons_per_row=3)
    await update.message.reply_text("Pilih kategori:", reply_markup=cat_buttons)
    return CHOOSING_CATEGORY


async def ask_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected_category = update.message.text
    if selected_category not in CATEGORIES:
        return await handle_unexpected_message(update, context)

    context.user_data["selected_category"] = selected_category
    logger.info(f"Kategori dipilih: {selected_category}")

    await update.message.reply_text("Masukkan jumlah (Rp):")
    return CHOOSING_PRICE


async def handle_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    price_text = update.message.text.strip()
    parsed = _parse_amount(price_text)
    if parsed is None:
        try:
            parsed = float(price_text.replace(".", "").replace(",", "."))
        except ValueError:
            await update.message.reply_text("Masukkan jumlah yang valid. ", reply_markup=markup)
            return CHOOSING_PRICE

    category = context.user_data["selected_category"]
    context.user_data["manual_amount"] = parsed
    context.user_data["manual_description"] = category

    await update.message.reply_text(
        f"Konfirmasi pengeluaran:\n\n"
        f"<b>Kategori:</b> {category}\n"
        f"<b>Jumlah:</b> Rp {parsed:,.0f}\n\n"
        f"Ketik <b>ya</b> untuk simpan, <b>cancel</b> untuk batal, "
        f"atau ketik ulang jumlah untuk mengubah.",
        parse_mode="HTML",
    )
    return WAITING_MANUAL_CONFIRM


async def handle_manual_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == "cancel" or text == "/cancel":
        context.user_data.clear()
        await update.message.reply_text("Dibatalkan.", reply_markup=markup)
        return CHOOSING

    amount = context.user_data["manual_amount"]
    category = context.user_data["selected_category"]

    if text != "ya":
        parsed = _parse_amount(text)
        if parsed is not None:
            amount = parsed
        else:
            try:
                amount = float(text.replace(".", "").replace(",", "."))
            except ValueError:
                await update.message.reply_text("Jumlah tidak valid. Coba lagi.", reply_markup=markup)
                return WAITING_MANUAL_CONFIRM

    user_id = str(update.effective_user.id)
    expense_id = save_expense(
        user_id=user_id,
        amount=amount,
        category=category,
        description=category,
        merchant=None,
        date=datetime.datetime.now().strftime("%Y-%m-%d"),
        source="manual",
    )

    update_spent(category)
    await check_budget(category)

    await update.message.reply_text(
        f"<b>Tercatat 📌</b>\n\n"
        f"<b>Kategori:</b> {category}\n"
        f"<b>Jumlah:</b> Rp {amount:,.0f}\n"
        f"<b>ID:</b> {expense_id}",
        parse_mode="HTML",
        reply_markup=markup,
    )

    context.user_data.clear()
    return CHOOSING


# --- Delete Expenses ---
async def ask_deleting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if is_expenses_empty():
        await update.message.reply_text("Belum ada pengeluaran.", reply_markup=markup)
        return CHOOSING

    if "current_page" not in context.user_data:
        context.user_data["current_page"] = 0

    return await show_expenses(update, context)


async def show_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    all_expenses = get_expenses(limit=200)

    if not all_expenses:
        await update.message.reply_text("Belum ada pengeluaran.", reply_markup=markup)
        return CHOOSING

    current_page = context.user_data["current_page"]
    start_index = current_page * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    page_expenses = all_expenses[start_index:end_index]

    expense_buttons = []
    expense_dict = {}

    for exp in page_expenses:
        button_text = f"🔥 {exp['date']} {exp['category']}: Rp {exp['amount']:,.0f}"
        expense_buttons.append([KeyboardButton(button_text)])
        expense_dict[button_text] = exp["id"]

    context.user_data["expense_dict"] = expense_dict

    navigation_buttons = []
    if start_index > 0:
        navigation_buttons.append(KeyboardButton("⬅️ Previous"))
    if end_index < len(all_expenses):
        navigation_buttons.append(KeyboardButton("➡️ Next"))

    if navigation_buttons:
        expense_buttons.append(navigation_buttons)

    reply_markup = ReplyKeyboardMarkup(
        expense_buttons, one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text("Pilih pengeluaran untuk dihapus:", reply_markup=reply_markup)
    return CHOOSING_ITEM_TO_DELETE


async def handle_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    expense_dict = context.user_data.get("expense_dict", {})
    expense_id = expense_dict.get(text)
    if expense_id is None:
        await update.message.reply_text("Pilihan tidak valid. Coba lagi.", reply_markup=markup)
        return CHOOSING

    deleted = delete_expense(expense_id)

    if deleted:
        context.user_data["last_deleted_id"] = expense_id
        context.user_data["last_deleted_text"] = text
        undo_kb = ReplyKeyboardMarkup([["↩️ Undo Hapus"]], one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Pengeluaran dihapus. ✅", reply_markup=undo_kb)
    else:
        await update.message.reply_text("Gagal menghapus.", reply_markup=markup)

    return CHOOSING


async def handle_undo_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    expense_id = context.user_data.get("last_deleted_id")
    if not expense_id:
        await update.message.reply_text("Tidak ada yang bisa di-undo.", reply_markup=markup)
        return CHOOSING

    restored = restore_expense(expense_id)
    context.user_data.pop("last_deleted_id", None)
    context.user_data.pop("last_deleted_text", None)

    if restored:
        await update.message.reply_text("Pengeluaran dikembalikan. ↩️", reply_markup=markup)
    else:
        await update.message.reply_text("Gagal mengembalikan.", reply_markup=markup)

    return CHOOSING


async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == "⬅️ Previous":
        context.user_data["current_page"] += 1
    elif text == "➡️ Next":
        context.user_data["current_page"] -= 1

    return await show_expenses(update, context)


# --- Edit Expense ---
async def ask_editing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    expenses = get_expenses(limit=20)

    if not expenses:
        await update.message.reply_text("Belum ada pengeluaran untuk diedit.", reply_markup=markup)
        return CHOOSING

    def label(e):
        return f"📝 {e['date']} {e['category']}: Rp {e['amount']:,.0f}"

    context.user_data["expense_dict"] = {label(e): e["id"] for e in expenses}
    reply_markup = build_keyboard([label(e) for e in expenses], buttons_per_row=1)
    await update.message.reply_text("Pilih pengeluaran untuk diedit:", reply_markup=reply_markup)
    return CHOOSING_ITEM_TO_EDIT


async def handle_edit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    expense_dict = context.user_data.get("expense_dict", {})
    expense_id = expense_dict.get(text)

    if expense_id is None:
        await update.message.reply_text("Pilihan tidak valid.", reply_markup=markup)
        return CHOOSING

    expense = next((e for e in get_expenses(limit=100) if e["id"] == expense_id), None)
    if not expense:
        await update.message.reply_text("Pengeluaran tidak ditemukan.", reply_markup=markup)
        return CHOOSING

    context.user_data["edit_expense_id"] = expense_id
    context.user_data["edit_expense"] = expense

    field_options = ["💰 Amount", "📂 Category", "📝 Description", "🏪 Merchant", "📅 Date"]
    reply_markup = build_keyboard(field_options, buttons_per_row=2)
    await update.message.reply_text("Pilih field yang ingin diedit:", reply_markup=reply_markup)
    return CHOOSING_EDIT_FIELD


async def handle_edit_field_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    logger.info(f"handle_edit_field_selection: text={text!r}")

    field_map = {
        "💰 Amount": ("amount", EDITING_AMOUNT, "Ketik jumlah baru (contoh: 50000):"),
        "📂 Category": ("category", EDITING_TEXT, "Pilih kategori:"),
        "📝 Description": ("description", EDITING_TEXT, "Ketik deskripsi baru:"),
        "🏪 Merchant": ("merchant", EDITING_TEXT, "Ketik merchant baru:"),
        "📅 Date": ("date", EDITING_TEXT, "Ketik tanggal baru (YYYY-MM-DD):"),
    }

    field_info = field_map.get(text)
    if not field_info:
        # Try matching without emoji
        for key, val in field_map.items():
            if key.split(" ", 1)[1] == text:
                field_info = val
                break

    if not field_info:
        logger.warning(f"handle_edit_field_selection: no match for {text!r}, returning CHOOSING")
        await update.message.reply_text("Pilihan tidak valid.", reply_markup=markup)
        return CHOOSING

    field_name, next_state, prompt = field_info
    context.user_data["edit_field"] = field_name
    logger.info(f"handle_edit_field_selection: field={field_name}, next_state={next_state}")

    if field_name == "category":
        reply_markup = build_keyboard(CATEGORIES, buttons_per_row=3)
        await update.message.reply_text(prompt, reply_markup=reply_markup)
    else:
        await update.message.reply_text(prompt, reply_markup=ReplyKeyboardRemove())

    return next_state


async def handle_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    expense_id = context.user_data.get("edit_expense_id")
    field_name = context.user_data.get("edit_field")
    new_value = update.message.text.strip()

    logger.info(f"handle_edit_value: expense_id={expense_id}, field={field_name}, value={new_value}")

    if not expense_id or not field_name:
        logger.error(f"handle_edit_value: missing data - expense_id={expense_id}, field={field_name}")
        await update.message.reply_text("Error: data edit tidak lengkap.", reply_markup=markup)
        return CHOOSING

    if field_name == "amount":
        parsed = _parse_amount(new_value)
        if parsed is None:
            await update.message.reply_text("Format jumlah tidak valid. Coba lagi.", reply_markup=ReplyKeyboardRemove())
            return EDITING_AMOUNT
        new_value = parsed

    if field_name == "date":
        try:
            datetime.datetime.strptime(new_value, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("Format tanggal tidak valid (YYYY-MM-DD). Coba lagi.", reply_markup=ReplyKeyboardRemove())
            return EDITING_TEXT

    if field_name == "category" and new_value not in CATEGORIES:
        await update.message.reply_text(f"Kategori tidak valid. Pilih dari: {CATEGORIES}", reply_markup=ReplyKeyboardRemove())
        return EDITING_TEXT

    updated = update_expense(expense_id, **{field_name: new_value})

    if updated:
        old_expense = context.user_data.get("edit_expense", {})
        if field_name in ("amount", "category"):
            # Recalculate spent for both old and new categories
            old_cat = old_expense.get("category")
            new_cat = new_value if field_name == "category" else old_cat
            for cat in {old_cat, new_cat}:
                if cat:
                    update_spent(cat)

        await update.message.reply_text(f"✅ Berhasil edit {field_name} → {new_value}", reply_markup=markup)
    else:
        await update.message.reply_text("❌ Gagal mengedit pengeluaran.", reply_markup=markup)

    return CHOOSING


# --- Budget ---
async def ask_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    budget_options = ["Set", "Show"]
    reply_markup = build_keyboard(budget_options, buttons_per_row=2)
    await update.message.reply_text("Pilih aksi anggaran:", reply_markup=reply_markup)
    return CHOOSING_BUDGET


async def ask_budget_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cat_buttons = build_keyboard(CATEGORIES, buttons_per_row=3)
    await update.message.reply_text("Pilih kategori untuk diatur anggarannya:", reply_markup=cat_buttons)
    return CHOOSING_BUDGET_CATEGORY


async def ask_budget_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected_category = update.message.text
    context.user_data["budget_category"] = selected_category

    if selected_category not in CATEGORIES:
        return await handle_unexpected_message(update, context)

    current_budget = get_current_budget(selected_category)
    await update.message.reply_text(
        f"Masukkan jumlah anggaran untuk {selected_category}.\n(Anggaran saat ini: Rp {current_budget:,.0f})"
    )
    return CHOOSING_BUDGET_AMOUNT


async def save_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        budget_text = update.message.text.replace(".", "").replace(",", ".")
        budget = float(budget_text)
        if budget <= 0:
            raise ValueError("Budget must be greater than 0")

        category = context.user_data["budget_category"]
        set_budget(category, budget)
        await update.message.reply_text(
            f"Anggaran diatur untuk {category}: Rp {budget:,.0f}", reply_markup=markup
        )
    except ValueError:
        await update.message.reply_text("Masukkan jumlah anggaran yang valid. 🚨", reply_markup=markup)

    return CHOOSING


async def show_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    budgets = get_all_budgets()

    if budgets:
        message = "Anggaran:\n\n"
        for b in budgets:
            message += f"<b>{b['category']}:</b> Rp {b['amount']:,.0f} | Pakai: Rp {b['spent']:,.0f}\n"
    else:
        message = "Belum ada anggaran."

    await update.message.reply_text(message, parse_mode="HTML", reply_markup=markup)
    return CHOOSING


# --- Charts ---
async def ask_charts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chart_options = ["Pie", "Histogram", "Trend", "Heatmap"]
    reply_markup = build_keyboard(chart_options, buttons_per_row=2)
    await update.message.reply_text("Pilih grafik:", reply_markup=reply_markup)
    return CHOOSING_CHART


def _get_expenses_df():
    expenses = get_expenses(limit=10000)
    if not expenses:
        return None
    df = pd.DataFrame(expenses)
    df["amount"] = df["amount"].astype(float)
    df["date"] = pd.to_datetime(df["date"])
    return df


async def show_yearly_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    df = _get_expenses_df()
    if df is None or df.empty:
        await update.message.reply_text("Belum ada data pengeluaran.", reply_markup=markup)
        return CHOOSING

    await save_pie_chart(df, "charts/expense_by_category_by_year.png")
    await update.message.reply_photo(
        open("charts/expense_by_category_by_year.png", "rb"),
        caption="Pengeluaran per kategori (tahunan)",
        reply_markup=markup,
    )
    return CHOOSING


async def show_trend_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    df = _get_expenses_df()
    if df is None or df.empty:
        await update.message.reply_text("Belum ada data pengeluaran.", reply_markup=markup)
        return CHOOSING

    await save_trend_chart(df, "charts/expense_trend_top_categories_by_month.png")
    await update.message.reply_photo(
        open("charts/expense_trend_top_categories_by_month.png", "rb"),
        caption="Trend 3 kategori teratas (bulanan)",
        reply_markup=markup,
    )
    return CHOOSING


async def show_monthly_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    df = _get_expenses_df()
    if df is None or df.empty:
        await update.message.reply_text("Belum ada data pengeluaran.", reply_markup=markup)
        return CHOOSING

    await save_stacked_bar_chart(df, "charts/monthly_expenses_by_category.png")
    await update.message.reply_photo(
        open("charts/monthly_expenses_by_category.png", "rb"),
        caption="Pengeluaran per kategori (bulanan)",
        reply_markup=markup,
    )
    return CHOOSING


async def show_heatmap_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    df = _get_expenses_df()
    if df is None or df.empty:
        await update.message.reply_text("Belum ada data pengeluaran.", reply_markup=markup)
        return CHOOSING

    await save_heatmap(df, "charts/heatmap_expense_intensity.png")
    await update.message.reply_photo(
        open("charts/heatmap_expense_intensity.png", "rb"),
        caption="Intensitas pengeluaran (bulanan)",
        reply_markup=markup,
    )
    return CHOOSING


# --- Expense List (Riwayat) ---
async def make_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    df = _get_expenses_df()
    if df is None or df.empty:
        await update.message.reply_text("Belum ada data pengeluaran.", reply_markup=markup)
        return CHOOSING

    current_year = datetime.datetime.now().year
    df_current_year = df[df["date"].dt.year == current_year]

    if df_current_year.empty:
        await update.message.reply_text(f"Tidak ada pengeluaran di {current_year}.", reply_markup=markup)
        return CHOOSING

    message = ""
    grouped = df_current_year.groupby([df_current_year["date"].dt.month, "category"])["amount"].sum()
    total_per_month = df_current_year.groupby(df_current_year["date"].dt.month)["amount"].sum()

    current_month = datetime.datetime.now().month
    for month in range(1, current_month + 1):
        month_name = calendar.month_name[month]
        message += f"\n<b>{month_name}:</b>\n"
        if month in grouped.index.get_level_values(0):
            for category, amount in grouped[month].items():
                message += f"  - {category}: Rp {amount:,.0f}\n"
        total = total_per_month.get(month, 0)
        message += f"  <b>Total:</b> Rp {total:,.0f}\n"

    await update.message.reply_text(message, parse_mode="HTML")
    return CHOOSING


# --- Settings ---
async def ask_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    settings = load_settings()
    google_sync_status = "aktif" if settings["google_sync"]["enabled"] else "nonaktif"
    budget_notification_status = "aktif" if settings["budget_notifications"]["enabled"] else "nonaktif"

    settings_options = [
        "Enable Google Sheet sync" if google_sync_status == "nonaktif" else "Disable Google Sheet sync",
        "Enable budget notification" if budget_notification_status == "nonaktif" else "Disable budget notification",
    ]
    reply_markup = build_keyboard(settings_options, buttons_per_row=2)
    message = (
        f"- Google Sheets sync: <u>{google_sync_status}</u>\n"
        f"- Notifikasi anggaran: <u>{budget_notification_status}</u>\n"
    )
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="HTML")
    return CHOOSING


async def handle_settings_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    settings = load_settings()

    if "Enable Google Sheet sync" in text:
        settings["google_sync"]["enabled"] = True
        message = "Google Sheets sync diaktifkan."
    elif "Disable Google Sheet sync" in text:
        settings["google_sync"]["enabled"] = False
        message = "Google Sheets sync dinonaktifkan."
    elif "Enable budget notification" in text:
        settings["budget_notifications"]["enabled"] = True
        message = "Notifikasi anggaran diaktifkan."
    elif "Disable budget notification" in text:
        settings["budget_notifications"]["enabled"] = False
        message = "Notifikasi anggaran dinonaktifkan."
    else:
        message = ""

    if message:
        save_settings(settings)
        await update.message.reply_text(message, reply_markup=markup)
    return CHOOSING


# --- Export ---
async def handle_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    output_path = export_to_xlsx()

    if output_path and os.path.exists(output_path):
        await update.message.reply_document(
            document=open(output_path, "rb"),
            caption="Export data expenses (.xlsx)",
            reply_markup=markup,
        )
    else:
        await update.message.reply_text("Belum ada data untuk export.", reply_markup=markup)

    return CHOOSING


# --- Slash Commands ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "<b>📋 Daftar Command</b>\n\n"
        "/start — Mulai tracking pengeluaran\n"
        "/help — Tampilkan daftar command\n"
        "/cancel — Batalkan input saat ini\n\n"
        "<b>💡 Quick-add:</b> ketik langsung dari menu utama\n"
        "Contoh: <code>makan siang 50k di warung</code>"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")


async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return await start(update, context)


async def handle_unexpected_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Huh?", reply_markup=markup)
    return CHOOSING


# --- Quick Add (direct text input from main menu) ---
async def handle_quick_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    amount = _parse_amount(text)
    if amount is None:
        await update.message.reply_text("Huh?", reply_markup=markup)
        return CHOOSING

    category = _match_category(text)
    context.user_data["quick_amount"] = amount
    context.user_data["quick_category"] = category
    context.user_data["quick_description"] = text

    confirm_msg = (
        f"<b>Simpan pengeluaran?</b>\n\n"
        f"<b>Jumlah:</b> Rp {amount:,.0f}\n"
        f"<b>Kategori:</b> {category}\n"
        f"<b>Catatan:</b> {text}\n\n"
        f"Ketik <b>ya</b> untuk simpan, <b>cancel</b> untuk batal, "
        f"atau ketik jumlah baru (contoh: '75000'):"
    )
    await update.message.reply_text(confirm_msg, parse_mode="HTML")
    return QUICK_ADD_CONFIRM


async def handle_quick_add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    user_id = str(update.effective_user.id)

    if text == "cancel" or text == "/cancel":
        context.user_data.clear()
        await update.message.reply_text("Dibatalkan.", reply_markup=markup)
        return CHOOSING

    amount = context.user_data.get("quick_amount")
    category = context.user_data.get("quick_category", "Other")
    description = context.user_data.get("quick_description", "")

    if text == "ya":
        pass  # use existing amount
    else:
        parsed = _parse_amount(text)
        if parsed is not None:
            amount = parsed
        else:
            try:
                amount = float(text.replace(".", "").replace(",", "."))
            except ValueError:
                await update.message.reply_text("Jumlah tidak valid. Coba lagi.", reply_markup=markup)
                return CHOOSING

    expense_id = save_expense(
        user_id=user_id,
        amount=amount,
        category=category,
        description=description,
        merchant=None,
        date=datetime.datetime.now().strftime("%Y-%m-%d"),
        source="quick",
    )

    update_spent(category)
    await check_budget(category)

    await update.message.reply_text(
        f"<b>Tercatat ✅</b>\n\n"
        f"<b>Kategori:</b> {category}\n"
        f"<b>Jumlah:</b> Rp {amount:,.0f}\n"
        f"<b>Catatan:</b> {description}\n"
        f"<b>ID:</b> {expense_id}",
        parse_mode="HTML",
        reply_markup=markup,
    )

    context.user_data.clear()
    return CHOOSING
