from config import DB_PATH, TELEGRAM_BOT_TOKEN
from constants import (
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
    WAITING_TEXT_CONFIRM,
    QUICK_ADD_CONFIRM,
)
from handlers import (
    ask_budget,
    ask_budget_amount,
    ask_budget_category,
    ask_category,
    ask_charts,
    ask_deleting,
    ask_editing,
    ask_input_type,
    ask_price,
    ask_settings,
    fallback,
    handle_deletion,
    handle_edit_field_selection,
    handle_edit_selection,
    handle_edit_value,
    handle_export,
    handle_input_type,
    handle_pagination,
    handle_photo,
    handle_photo_confirm,
    handle_quick_add,
    handle_quick_add_confirm,
    handle_settings_choice,
    handle_text_input,
    handle_text_input_confirm,
    handle_undo_delete,
    handle_unexpected_message,
    make_list,
    save_budget,
    save_on_local_db,
    show_budget,
    show_heatmap_chart,
    show_monthly_chart,
    show_trend_chart,
    show_yearly_chart,
    start,
)
from telegram import Update
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters


def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [
                CommandHandler("start", start),
                MessageHandler(filters.Regex("^✏️ Tambah$"), ask_input_type),
                MessageHandler(filters.Regex("^❌ Hapus$"), ask_deleting),
                MessageHandler(filters.Regex("^📊 Grafik$"), ask_charts),
                MessageHandler(filters.Regex("^📋 Riwayat$"), make_list),
                MessageHandler(filters.Regex("^💰 Anggaran$"), ask_budget),
                MessageHandler(filters.Regex("^📤 Export$"), handle_export),
                MessageHandler(filters.Regex("^⚙️ Pengaturan$"), ask_settings),
                MessageHandler(filters.Regex("^📝 Edit$"), ask_editing),
                MessageHandler(filters.Regex("^Enable Google Sheet sync$"), handle_settings_choice),
                MessageHandler(filters.Regex("^Disable Google Sheet sync$"), handle_settings_choice),
                MessageHandler(filters.Regex("^Enable budget notification$"), handle_settings_choice),
                MessageHandler(filters.Regex("^Disable budget notification$"), handle_settings_choice),
                MessageHandler(filters.Regex("^↩️ Undo Hapus$"), handle_undo_delete),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quick_add),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message),
            ],
            CHOOSING_INPUT_TYPE: [
                CommandHandler("start", start),
                MessageHandler(filters.Regex("^📝 Manual$"), ask_category),
                MessageHandler(filters.Regex("^📷 Foto$"), handle_input_type),
                MessageHandler(filters.Regex("^💬 Teks$"), handle_input_type),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message),
            ],
            CHOOSING_CATEGORY: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_price),
            ],
            CHOOSING_PRICE: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_on_local_db),
            ],
            WAITING_TEXT: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input),
            ],
            WAITING_TEXT_CONFIRM: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input_confirm),
            ],
            WAITING_PHOTO: [
                CommandHandler("start", start),
                MessageHandler(filters.PHOTO, handle_photo),
            ],
            WAITING_PHOTO_CONFIRM: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_photo_confirm),
            ],
            CHOOSING_ITEM_TO_DELETE: [
                CommandHandler("start", start),
                MessageHandler(
                    filters.Regex(r"^🔥 [\d-]+ [\w]+: Rp \d[\d,.]*$"),
                    handle_deletion,
                ),
                MessageHandler(filters.Regex("^(⬅️ Previous|➡️ Next)$"), handle_pagination),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message),
            ],
            QUICK_ADD_CONFIRM: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quick_add_confirm),
            ],
            CHOOSING_CHART: [
                CommandHandler("start", start),
                MessageHandler(filters.Regex("^Pie$"), show_yearly_chart),
                MessageHandler(filters.Regex("^Histogram$"), show_monthly_chart),
                MessageHandler(filters.Regex("^Trend$"), show_trend_chart),
                MessageHandler(filters.Regex("^Heatmap$"), show_heatmap_chart),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message),
            ],
            CHOOSING_BUDGET: [
                CommandHandler("start", start),
                MessageHandler(filters.Regex("^Set$"), ask_budget_category),
                MessageHandler(filters.Regex("^Show$"), show_budget),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message),
            ],
            CHOOSING_BUDGET_CATEGORY: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_budget_amount),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message),
            ],
            CHOOSING_BUDGET_AMOUNT: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_budget),
            ],
            CHOOSING_ITEM_TO_EDIT: [
                CommandHandler("start", start),
                MessageHandler(
                    filters.Regex(r"^📝 [\d-]+ [\w]+: Rp \d[\d,.]*$"),
                    handle_edit_selection,
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message),
            ],
            CHOOSING_EDIT_FIELD: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_field_selection),
            ],
            EDITING_AMOUNT: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_value),
            ],
            EDITING_TEXT: [
                CommandHandler("start", start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_value),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^/cancel$"), fallback)],
    )

    application.add_handler(conv_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    from utils import init_db
    init_db(DB_PATH)
    main()
