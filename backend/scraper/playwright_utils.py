"""Playwright launch helpers — fixes arm64/x64 cache mismatches on Apple Silicon."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _fix_browser_cache_paths() -> None:
    """Symlink arm64 browser bundles when Playwright looks for mac-x64."""
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / "Library/Caches/ms-playwright"))
    if not cache.is_dir():
        return

    pairs = (
        ("chromium_headless_shell", "chrome-headless-shell-mac"),
        ("chromium", "chrome-mac"),
    )
    for prefix, folder_prefix in pairs:
        for bundle in cache.glob(f"{prefix}-*"):
            arm = bundle / f"{folder_prefix}-arm64"
            x64 = bundle / f"{folder_prefix}-x64"
            if arm.is_dir() and not x64.exists():
                try:
                    x64.symlink_to(arm, target_is_directory=True)
                except OSError as exc:
                    logger.debug("Could not link Playwright browser path: %s", exc)


def _arm64_headless_executable() -> str | None:
    cache = Path.home() / "Library/Caches/ms-playwright"
    for bundle in sorted(cache.glob("chromium_headless_shell-*"), reverse=True):
        exe = bundle / "chrome-headless-shell-mac-arm64" / "chrome-headless-shell"
        if exe.is_file():
            return str(exe)
    return None


def chromium_launch_kwargs(*, headless: bool = True) -> dict:
    _fix_browser_cache_paths()
    exe = _arm64_headless_executable()
    if exe:
        return {"headless": headless, "executable_path": exe}
    return {"headless": headless, "channel": "chrome"}


async def launch_chromium(playwright):
    """Try bundled arm64 Chrome, then system Chrome."""
    strategies = [
        chromium_launch_kwargs(),
        {"headless": True, "channel": "chrome"},
        {"headless": False, "channel": "chrome"},
    ]
    last_error: Exception | None = None
    for kwargs in strategies:
        try:
            return await playwright.chromium.launch(**kwargs)
        except Exception as exc:
            last_error = exc
            logger.debug("Playwright launch failed with %s: %s", kwargs, exc)
    raise last_error or RuntimeError("Could not launch Chromium")
