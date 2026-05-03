import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from config import DB_PATH, logger
from utils import get_expenses, load_settings, save_settings


def sync_to_google_sheets():
    logger.info("Sync function started")
    settings = load_settings()
    if settings["google_sync"]["enabled"]:
        # Placeholder — needs credentials.json and gspread
        logger.info("Google sync enabled but not yet implemented for SQLite")
    else:
        logger.info("Google sync is disabled")


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(sync_to_google_sheets, "interval", minutes=5)
    scheduler.start()
    return scheduler
