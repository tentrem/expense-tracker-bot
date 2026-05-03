"""OCR handler — runs Tesseract via pytesseract."""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to Python 3.11 venv for OCR (local to bot)
BOT_DIR = Path(__file__).resolve().parent.parent
PADDLEOCR_VENV_PYTHON = BOT_DIR / "venv_ocr" / "bin" / "python3.11"

_OCR_SCRIPT = """
import sys, json, os
import shutil
import pytesseract
from PIL import Image

image_path = sys.argv[1]

try:
    # Find tesseract binary
    tesseract_path = shutil.which('tesseract')
    if not tesseract_path:
        # Try common paths
        for path in ['/home/linuxbrew/.linuxbrew/bin/tesseract', '/opt/homebrew/bin/tesseract', '/usr/bin/tesseract']:
            if os.path.exists(path):
                tesseract_path = path
                break

    if not tesseract_path:
        raise RuntimeError("tesseract binary not found")

    pytesseract.pytesseract.tesseract_cmd = tesseract_path

    img = Image.open(image_path)
    full_text = pytesseract.image_to_string(img)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    lines = []
    for i, text in enumerate(data['text']):
        if text.strip() and data['conf'][i] > 0:
            lines.append({"text": text, "confidence": float(data['conf'][i])})

    print(json.dumps({"success": True, "lines": lines, "full_text": full_text}))
except Exception as e:
    print(json.dumps({"success": False, "error": str(e)}))
"""


def run_ocr(image_path: str) -> dict:
    """Run Tesseract OCR via subprocess (Python 3.11 venv)."""
    if not os.path.exists(str(PADDLEOCR_VENV_PYTHON)):
        return {"success": False, "error": f"OCR venv not found at {PADDLEOCR_VENV_PYTHON}"}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(_OCR_SCRIPT)
        script_path = f.name

    try:
        result = subprocess.run(
            [str(PADDLEOCR_VENV_PYTHON), script_path, image_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        logger.info(f"OCR stdout: {result.stdout[:500] if result.stdout else 'empty'}")
        logger.error(f"OCR stderr: {result.stderr[:500] if result.stderr else 'empty'}")
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        return {"success": False, "error": "No JSON output from OCR"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "OCR timed out after 60s"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass
