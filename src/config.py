import logging
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load env vars
load_dotenv()
env_vars = dotenv_values()
TELEGRAM_BOT_TOKEN = env_vars.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_USERS = set(
    u.strip() for u in env_vars.get("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()
)
DASHSCOPE_API_KEY = env_vars.get("DASHSCOPE_API_KEY", "")

# Database path (local to bot)
BOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BOT_DIR / "expenses.db"

# Pagination
ITEMS_PER_PAGE = 5
