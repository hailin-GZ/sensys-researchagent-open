"""Use an explicit installed browser or Playwright's platform-specific path."""
import os
from pathlib import Path

def chromium_path():
    configured = os.environ.get('SENSYS_CHROMIUM_PATH')
    if configured:
        path = Path(configured)
    else:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            path = Path(runtime.chromium.executable_path)
    if not path.is_file():
        raise ValueError('Chromium is missing; install it and set SENSYS_CHROMIUM_PATH')
    return path
