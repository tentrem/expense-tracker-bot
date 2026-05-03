"""Export expenses from SQLite to .xlsx file."""

import os
from datetime import datetime

import pandas as pd

from utils import get_expenses


def export_to_xlsx(category=None, date_from=None, date_to=None, output_path=None):
    """Export expenses to .xlsx file.

    Args:
        category: Optional filter by category
        date_from: Optional start date (YYYY-MM-DD)
        date_to: Optional end date (YYYY-MM-DD)
        output_path: Optional output file path

    Returns:
        str: Path to generated .xlsx file
    """
    expenses = get_expenses(category=category, date_from=date_from, date_to=date_to, limit=10000)

    if not expenses:
        return None

    df = pd.DataFrame(expenses)

    # Select and rename columns for readability
    column_map = {
        "id": "ID",
        "date": "Tanggal",
        "category": "Kategori",
        "description": "Deskripsi",
        "merchant": "Merchant",
        "amount": "Jumlah (Rp)",
        "source": "Sumber",
        "created_at": "Dicatat",
    }
    display_df = df[[c for c in column_map.keys() if c in df.columns]].rename(columns=column_map)

    if output_path is None:
        os.makedirs("./spreadsheets", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"./spreadsheets/export_{ts}.xlsx"

    display_df.to_excel(output_path, index=False)
    return output_path
