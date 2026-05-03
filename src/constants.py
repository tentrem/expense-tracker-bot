from telegram import ReplyKeyboardMarkup

# Constants to manage the state
(
    CHOOSING,
    CHOOSING_INPUT_TYPE,
    CHOOSING_CATEGORY,
    CHOOSING_PRICE,
    CHOOSING_DATE,
    WAITING_MANUAL_CONFIRM,
    CHOOSING_ITEM_TO_DELETE,
    CHOOSING_CHART,
    CHOOSING_BUDGET,
    CHOOSING_BUDGET_CATEGORY,
    CHOOSING_BUDGET_AMOUNT,
    CHOOSING_ITEM_TO_EDIT,
    CHOOSING_EDIT_FIELD,
    EDITING_AMOUNT,
    EDITING_TEXT,
    WAITING_TEXT,
    WAITING_PHOTO,
    WAITING_PHOTO_CONFIRM,
    WAITING_TEXT_CONFIRM,
    QUICK_ADD_CONFIRM,
) = range(20)

DB_PATH = None  # Set from config at runtime
LOCAL_CHART_PATH = "./charts"
LOCAL_SETTINGS_PATH = "./settings.json"
RECEIPTS_DIR = "./receipts"

# Define reply keyboard
reply_keyboard = [
    ["✏️ Tambah", "❌ Hapus", "📊 Grafik"],
    ["📋 Riwayat", "💰 Anggaran", "📤 Export", "⚙️ Pengaturan"],
    ["📝 Edit"],
]
markup = ReplyKeyboardMarkup(
    reply_keyboard, one_time_keyboard=False, resize_keyboard=True
)

# Input type menu
input_type_keyboard = ReplyKeyboardMarkup(
    [["📝 Manual", "📷 Foto", "💬 Teks"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)

# 10 categories (Indonesia context)
CATEGORIES = [
    "Food", "Transport", "Shopping", "Bills", "Entertainment",
    "Health", "Education", "Housing", "Communication", "Other",
]
