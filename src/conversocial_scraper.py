from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

try:
    from playwright.sync_api import sync_playwright, Page, Frame
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

METRICS = [
    "Incoming Messages",
    "Incoming Conversations",
    "Conversations Interacted",
    "Avg Interaction Time",
    "Total Interaction Time",
    "Responses",
    "Response Time",
    "First Response Time",
    "Response Time BH",
    "First Response Time BH",
]

ALL_PLATFORMS = [
    "FACEBOOK",
    "GOOGLEMYBUSINESS",
    "INSTAGRAM",
    "THREADS",
    "TIKTOK",
    "TWITTER",
]

DEFAULT_QUEUES = [
    "First Response Team",
    "Hertz Car Sale Reviews",
    "Hertz Car Sales",
    "TikTok",
    "Threads",
    "Bot Spam",
    "GBR North America",
]

BASE_URL  = "https://app.conversocial.com"
AUTH_DIR  = Path(".streamlit/conversocial_profile")

# Finds a metric card by label and returns [value, change%]
_CARD_JS = """
(metric) => {
    // Each KPI tile has a unique aria-label button: "{metric} - Tile actions"
    // Use it to pinpoint the exact tile rather than walking the full DOM.
    const tileBtn = document.querySelector('[aria-label="' + metric + ' - Tile actions"]');
    if (!tileBtn) return [null, null];

    // Walk up from the tile-actions button to find the tile container
    let node = tileBtn.parentElement;
    for (let i = 0; i < 10 && node && node !== document.body; i++) {
        const rect = node.getBoundingClientRect();
        if (rect.width > 80 && rect.height > 60) {
            const leaves = [...node.querySelectorAll('*')].filter(c => c.children.length === 0);
            for (const leaf of leaves) {
                const t = (leaf.innerText || leaf.textContent || '').trim();
                // First leaf that starts with a digit and isn't the label itself
                const isNull = t === 'Ø' || t === '∅' || t === '∅' || t === 'Ø';
                if ((isNull || t === '0' || /^\\d/.test(t)) && t !== metric && !t.toLowerCase().includes('change')) {
                    if (isNull) return ['0', null];
                    // For count metrics (no "Time" in name), skip time-format values like "00:0:0"
                    if (!metric.toLowerCase().includes('time') && t.includes(':')) continue;
                    return [t, null];
                }
            }
        }
        node = node.parentElement;
    }
    return [null, null];
}
"""


def _get_credentials() -> tuple[str, str]:
    try:
        import streamlit as st
        return st.secrets["conversocial"]["username"], st.secrets["conversocial"]["password"]
    except Exception:
        import tomllib
        with open(".streamlit/secrets.toml", "rb") as f:
            cfg = tomllib.load(f)
        return cfg["conversocial"]["username"], cfg["conversocial"]["password"]


from src import _browser_state as _bs  # survives importlib.reload of this module


class ConversocialScraper:
    def __init__(self, headless: bool = False):
        self.headless = headless

    @property
    def session_ready(self) -> bool:
        return True

    def _get_browser(self):
        """Always start a fresh browser. Session is preserved via user_data_dir cookies on disk."""
        # Kill any leftover browser/playwright from a previous run
        if _bs.browser_ctx is not None:
            try:
                _bs.browser_ctx.close()
            except Exception:
                pass
        if _bs.pw_instance is not None:
            try:
                _bs.pw_instance.stop()
            except Exception:
                pass
        _bs.browser_ctx = None
        _bs.browser_page = None
        _bs.pw_instance = None

        # Remove Chrome profile lock files left by crashed/killed instances
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        for _lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            try:
                (AUTH_DIR / _lock).unlink()
            except FileNotFoundError:
                pass

        from playwright.sync_api import sync_playwright as _spw
        _bs.pw_instance = _spw().start()
        _bs.browser_ctx = _bs.pw_instance.chromium.launch_persistent_context(
            user_data_dir=str(AUTH_DIR),
            headless=self.headless,
            viewport={"width": 1600, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        _bs.browser_page = _bs.browser_ctx.new_page()
        return _bs.browser_ctx, _bs.browser_page

    def run(
        self,
        platforms: list[str] | None = None,
        queues: list[str] | None = None,
        on_progress: Callable[[int, str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        target_date: str | None = None,
        dates: list[str] | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> pd.DataFrame:
        """
        Extract metrics from Conversocial/Looker.

        date resolution priority:
          1. dates — list of YYYY-MM-DD strings; extracted one day at a time in one
             browser session (no summing — each day gets its own rows)
          2. target_date — single YYYY-MM-DD string
          3. neither — yesterday
        """
        self._username = username
        self._password = password
        global _browser_ctx, _browser_page

        if not PLAYWRIGHT_OK:
            raise RuntimeError(
                "Playwright not installed. Run:\n"
                "  py -m pip install playwright\n"
                "  py -m playwright install chromium"
            )

        platforms = platforms or ALL_PLATFORMS
        queues = queues or DEFAULT_QUEUES
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Build the ordered list of dates to process
        if dates:
            date_list = dates
        elif target_date:
            date_list = [target_date]
        else:
            date_list = [yesterday]

        ctx, page = self._get_browser()
        self._page = page

        rows: list[dict] = []
        total_steps = len(date_list) * len(platforms)
        step = 0

        try:
            looker = self._open_analytics(page, on_status=on_status)

            for date_str in date_list:
                if on_status:
                    on_status(f"📅 Setting date filter to {date_str}…")
                self._set_date_filter(looker, date_str)
                # Small settle; _apply_queues/_apply_platform both call _wait_for_looker_idle
                looker.wait_for_timeout(500)

                # Queue filter persists across platform changes — apply once per date
                self._apply_queues(looker, queues)

                for platform in platforms:
                    if on_progress:
                        on_progress(step, platform, date_str, total_steps)
                    row: dict = {"Date": date_str, "Platform": platform}
                    try:
                        self._apply_platform(looker, platform)
                        self._wait_for_refresh(looker)
                        row.update(self._extract_cards(looker))
                    except Exception as exc:
                        row["Error"] = str(exc)
                    rows.append(row)
                    step += 1

        finally:
            try:
                ctx.close()
            except Exception:
                pass
            try:
                _bs.pw_instance.stop()
            except Exception:
                pass
            _bs.browser_ctx = None
            _bs.browser_page = None
            _bs.pw_instance = None

        return pd.DataFrame(rows)

    # ── internal helpers ───────────────────────────────────────────────────────

    def _login(self, page: "Page", on_status: Callable | None = None) -> None:
        """Auto-login using credentials (from sidebar or secrets.toml)."""
        username = getattr(self, "_username", None)
        password = getattr(self, "_password", None)
        if not username or not password:
            try:
                username, password = _get_credentials()
            except Exception:
                username, password = None, None

        if not username or not password:
            page.wait_for_load_state("networkidle", timeout=30_000)
            return

        if on_status:
            on_status("🔐 Logging in to Conversocial…")
        try:
            # Step 1 — username
            page.wait_for_selector(
                'input[name="username"], input[type="text"], input[type="email"]',
                timeout=15_000,
            )
            # click + keyboard.type is more reliable than fill() across SSO frameworks
            page.click('input[name="username"], input[type="text"], input[type="email"]')
            page.keyboard.type(username, delay=40)
            page.wait_for_timeout(500)

            _submitted = False
            for _sel in [
                'button[type="submit"]', 'input[type="submit"]',
                'button:has-text("Next")', 'button:has-text("Continue")',
                'button:has-text("Sign in")', 'button:has-text("Log in")', 'button:has-text("Login")',
            ]:
                try:
                    _btn = page.locator(_sel)
                    if _btn.count() > 0 and _btn.first.is_visible(timeout=1_000):
                        _btn.first.click()
                        _submitted = True
                        break
                except Exception:
                    continue
            if not _submitted:
                page.keyboard.press("Enter")
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            page.wait_for_timeout(1_000)

            # Step 2 — password
            # Wait for the password field to become visible (hash-routed forms
            # show it after the username step without a full page reload)
            pwd_el = None
            try:
                pwd_el = page.wait_for_selector(
                    'input[type="password"]', state="visible", timeout=10_000
                )
            except Exception:
                try:
                    pwd_el = page.wait_for_selector(
                        'input[type="password"]', state="attached", timeout=10_000
                    )
                    # Unhide if necessary
                    page.evaluate("""() => {
                        const el = document.querySelector('input[type="password"]');
                        if (el) { el.removeAttribute('hidden');
                                  el.style.display=''; el.style.visibility=''; }
                    }""")
                except Exception:
                    pass

            if pwd_el:
                # click + type fires real keyboard events which React/Angular need
                pwd_el.click()
                pwd_el.fill("")          # clear first
                pwd_el.type(password, delay=40)
            else:
                raise RuntimeError("Password field not found after username step.")

            page.wait_for_timeout(600)

            _submitted2 = False
            for _sel in [
                'button[type="submit"]', 'input[type="submit"]',
                'button:has-text("Sign in")', 'button:has-text("Log in")',
                'button:has-text("Login")', 'button:has-text("Continue")',
            ]:
                try:
                    _btn = page.locator(_sel)
                    if _btn.count() > 0 and _btn.first.is_visible(timeout=1_000):
                        _btn.first.click()
                        _submitted2 = True
                        break
                except Exception:
                    continue
            if not _submitted2:
                page.keyboard.press("Enter")

            # Wait for the URL to leave the login page — this is the reliable signal
            # that authentication succeeded (works regardless of SSO domain chain).
            try:
                page.wait_for_url(
                    lambda url: "/login" not in url and "signin" not in url,
                    timeout=60_000,
                )
            except Exception:
                # If URL never changed, collect diagnostic info
                final_url = page.url
                try:
                    err_el = page.locator('[class*="error"], [class*="alert"], [role="alert"]').first
                    err_text = err_el.inner_text(timeout=2_000) if err_el.count() > 0 else ""
                except Exception:
                    err_text = ""
                try:
                    page.screenshot(path=".streamlit/debug_login_fail.png")
                except Exception:
                    pass
                hint = f"Page says: {err_text[:200]}" if err_text else "Check credentials in the sidebar."
                raise RuntimeError(
                    f"Login failed — still on login page 60 s after submitting.\n"
                    f"Stuck URL: {final_url}\n{hint}"
                )

        except RuntimeError:
            raise
        except Exception as e:
            try:
                page.screenshot(path=".streamlit/debug_login_fail.png")
            except Exception:
                pass
            raise RuntimeError(f"Auto-login failed: {str(e)[:400]}")

    def _open_analytics(self, page: "Page", on_status: Callable | None = None) -> "Frame":
        page.goto(f"{BASE_URL}/analytics/")
        page.wait_for_load_state("networkidle", timeout=30_000)
        page.screenshot(path=".streamlit/debug_home.png")

        if "/login" in page.url or "signin" in page.url or "verint" in page.url.lower():
            self._login(page, on_status=on_status)
            page.goto(f"{BASE_URL}/analytics/")
            page.wait_for_load_state("networkidle", timeout=30_000)

        # Wait for the Looker iframe to appear and authenticate
        page.wait_for_selector("iframe", timeout=30_000)
        page.wait_for_timeout(3_000)  # give Looker SSO redirect time

        # Get the Looker frame (waits until it's navigated past /login)
        looker = self._get_looker_frame(page)
        page.screenshot(path=".streamlit/debug_analytics.png")
        return looker

    def _get_looker_frame(self, page: "Page") -> "Frame":
        """Wait for the Looker iframe to finish its SSO redirect, then return the frame."""
        deadline = 30_000
        page.wait_for_timeout(2_000)
        for _ in range(15):
            for frame in page.frames:
                if "looker" in frame.url and "/login" not in frame.url:
                    return frame
            page.wait_for_timeout(2_000)
        # Fallback: return the first non-main frame
        for frame in page.frames:
            if frame != page.main_frame:
                return frame
        raise RuntimeError("Could not find Looker analytics iframe")

    def _set_date_yesterday(self, frame: "Frame") -> None:
        try:
            # Dump all text in frame to find how the date filter is labelled
            date_info = frame.evaluate("""() => {
                const all = [...document.querySelectorAll('*')];
                const hits = all.filter(el => {
                    const t = (el.innerText || el.textContent || '').trim();
                    return t === 'Yesterday' || t === 'Last 7 Days' || t === 'Today'
                        || t === 'Last 28 Days' || t === 'Last 90 Days';
                });
                return hits.map(el => ({
                    tag: el.tagName, cls: el.className, text: (el.innerText||el.textContent||'').trim()
                }));
            }""")
            import json
            Path(".streamlit/debug_date.txt").write_text(json.dumps(date_info, indent=2), encoding="utf-8")
        except Exception as e:
            Path(".streamlit/debug_date.txt").write_text(f"Error: {e}", encoding="utf-8")

        try:
            # Try clicking Yesterday directly
            clicked = frame.evaluate("""() => {
                const all = [...document.querySelectorAll('*')];
                // Find the Yesterday option element (not just text node)
                for (const el of all) {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (t === 'Yesterday' && el.children.length === 0) {
                        // Try clicking the element or its parent button
                        let node = el;
                        for (let i = 0; i < 5; i++) {
                            if (!node) break;
                            if (node.tagName === 'BUTTON' || node.tagName === 'LI'
                                || node.getAttribute('role') === 'option'
                                || node.getAttribute('role') === 'menuitem') {
                                node.click();
                                return true;
                            }
                            node = node.parentElement;
                        }
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            if clicked:
                frame.wait_for_timeout(1_000)
                return
            # If Yesterday not visible, the date picker may need to be opened first
            # Look for the date range button (shows current range like "Last 7 Days")
            opened = frame.evaluate("""() => {
                const all = [...document.querySelectorAll('button, [role="button"], [role="combobox"]')];
                for (const el of all) {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (t.includes('Last 7 Days') || t.includes('Last 28 Days') || t.includes('Today')
                        || t.includes('Last 90 Days')) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            if opened:
                frame.wait_for_timeout(800)
                # Now try clicking Yesterday again
                frame.evaluate("""() => {
                    const all = [...document.querySelectorAll('*')];
                    for (const el of all) {
                        const t = (el.innerText || el.textContent || '').trim();
                        if (t === 'Yesterday' && el.children.length === 0) {
                            let node = el;
                            for (let i = 0; i < 5; i++) {
                                if (!node) break;
                                if (node.tagName === 'BUTTON' || node.tagName === 'LI'
                                    || node.getAttribute('role') === 'option'
                                    || node.getAttribute('role') === 'menuitem') {
                                    node.click();
                                    return true;
                                }
                                node = node.parentElement;
                            }
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                frame.wait_for_timeout(1_000)
        except Exception:
            pass

    def _set_date_filter(self, frame: "Frame", target_date: str) -> None:
        """Set Looker date filter to a specific date."""
        import re as _re
        from datetime import datetime as _dt
        d = _dt.strptime(target_date, "%Y-%m-%d")
        target_day = str(d.day)
        target_month = d.strftime("%B %Y")  # e.g. "May 2026"
        date_slash = d.strftime("%Y/%m/%d")  # Looker text-input format

        log: list[str] = []

        def snap(name: str) -> None:
            try:
                frame.screenshot(path=f".streamlit/debug_date_{name}.png")
            except Exception:
                pass

        try:
            # ── Step 1: open the date chip ────────────────────────────────────
            # Dump all filter-token texts so we can see what's actually on screen
            all_tokens = frame.evaluate("""() =>
                [...document.querySelectorAll('[data-testid="filter-token"]')]
                .map(el => el.innerText || el.textContent || '')
            """) or []
            log.append(f"step1: filter-tokens visible = {all_tokens}")

            opened = False

            # Primary: find the "Date" filter label, then click the chip between
            # it and the next filter label (Date chip is NOT a filter-token element)
            chip_info = frame.evaluate("""() => {
                const allEls = [...document.querySelectorAll('*')];

                // Find the "Date" label leaf node
                let labelIdx = -1;
                for (let i = 0; i < allEls.length; i++) {
                    const el = allEls[i];
                    if (el.children.length === 0) {
                        const t = (el.innerText || el.textContent || '').trim();
                        if (t === 'Date') { labelIdx = i; break; }
                    }
                }
                if (labelIdx === -1) return null;

                // Find where the NEXT filter label starts (to bound the search)
                const nextLabels = ['Use Comparison Date', 'Comparison Date',
                                    'Time Origin', 'Platform', 'Channel', 'Queue'];
                let boundIdx = allEls.length;
                for (const lbl of nextLabels) {
                    for (let i = labelIdx + 1; i < allEls.length; i++) {
                        if (allEls[i].children.length === 0) {
                            const t = (allEls[i].innerText || allEls[i].textContent || '').trim();
                            if (t === lbl && i < boundIdx) { boundIdx = i; break; }
                        }
                    }
                }

                // Find the first visible clickable element in that window
                const clickables = [...document.querySelectorAll(
                    '[role="button"], button, [data-testid="filter-token"]'
                )];
                for (const el of clickables) {
                    const idx = allEls.indexOf(el);
                    if (idx > labelIdx && idx < boundIdx) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 10 && r.height > 10) {
                            return { x: r.left + r.width / 2, y: r.top + r.height / 2,
                                     text: (el.innerText || el.textContent || '').trim() };
                        }
                    }
                }
                return null;
            }""")

            if chip_info:
                # Use page mouse so React receives a real pointer event
                iframe_box = self._page.locator("iframe").first.bounding_box()
                if iframe_box:
                    ax = iframe_box["x"] + chip_info["x"]
                    ay = iframe_box["y"] + chip_info["y"]
                    self._page.mouse.click(ax, ay)
                    frame.wait_for_timeout(1_000)
                    opened = True
                    log.append(f"step1: clicked Date chip '{chip_info['text']}' via page mouse")

            # Fallback: text-based search across known date preset labels
            if not opened:
                for kw in ["Yesterday", "Today", "Last 7", "Last 28", "Last 90",
                           "days ago", "day ago", "This Week", "This Month"]:
                    for sel in [
                        f'[data-testid="filter-token"]:has-text("{kw}")',
                        f'[role="button"]:has-text("{kw}")',
                        f'button:has-text("{kw}")',
                    ]:
                        loc = frame.locator(sel)
                        if loc.count() > 0:
                            loc.first.click(force=True, timeout=5_000)
                            frame.wait_for_timeout(1_000)
                            opened = True
                            log.append(f"step1: opened via fallback '{kw}' {sel}")
                            break
                    if opened:
                        break

            snap("step1")
            if not opened:
                log.append("step1: FAILED — date chip not found")
                Path(".streamlit/debug_date_filter_err.txt").write_text("\n".join(log), encoding="utf-8")
                return

            # ── Step 2: click "Custom" tab ────────────────────────────────────
            custom_clicked = False
            for sel in [
                '[role="tab"]:has-text("Custom")',
                'button:has-text("Custom")',
                '[class*="tab" i]:has-text("Custom")',
                'text=Custom',
            ]:
                try:
                    loc = frame.locator(sel)
                    if loc.count() > 0:
                        loc.first.click(force=True, timeout=3_000)
                        frame.wait_for_timeout(800)
                        custom_clicked = True
                        log.append(f"step2: Custom tab clicked via {sel}")
                        break
                except Exception as e:
                    log.append(f"step2: {sel} err: {e}")

            snap("step2")
            if not custom_clicked:
                log.append("step2: Custom tab NOT clicked — trying text input anyway")

            # ── Step 3: fill Start date and End date inputs separately ───────
            filled = False
            frame.wait_for_timeout(600)  # let Custom tab panel animate in
            try:
                start_inp = frame.locator('input[placeholder*="Start" i]')
                end_inp   = frame.locator('input[placeholder*="End" i]')
                if start_inp.count() > 0 and start_inp.first.is_visible(timeout=3_000):
                    start_inp.first.click(click_count=3, timeout=2_000)
                    start_inp.first.fill(date_slash)
                    frame.wait_for_timeout(300)
                    end_inp.first.click(click_count=3, timeout=2_000)
                    end_inp.first.fill(date_slash)
                    frame.wait_for_timeout(400)
                    filled = True
                    log.append("step3: filled Start date + End date inputs")
            except Exception as e:
                log.append(f"step3: start/end inputs err: {e}")

            # Fallback: single combined input
            if not filled:
                for inp_sel in [
                    'input[placeholder*="YYYY" i]',
                    'input[placeholder*="date" i]',
                    'input[type="text"]',
                ]:
                    try:
                        inp = frame.locator(inp_sel)
                        if inp.count() > 0 and inp.first.is_visible(timeout=2_000):
                            inp.first.click(click_count=3, timeout=2_000)
                            inp.first.fill(date_slash)
                            frame.wait_for_timeout(400)
                            filled = True
                            log.append(f"step3: filled single input via {inp_sel}")
                            break
                    except Exception as e:
                        log.append(f"step3: {inp_sel} err: {e}")

            snap("step3")

            if not filled:
                log.append("step3: text input not found — falling back to calendar clicks")
                # ── Calendar fallback: navigate to month, click day ──────────
                for _ in range(12):
                    body = frame.evaluate("() => document.body.innerText") or ""
                    if target_month in body:
                        break
                    for prev_sel in [
                        '[aria-label*="previous" i]', '[aria-label*="prev" i]',
                        '[aria-label*="back" i]', 'button:has-text("<")',
                        '[data-testid*="prev" i]',
                    ]:
                        try:
                            p = frame.locator(prev_sel)
                            if p.count() > 0:
                                p.first.click(force=True, timeout=2_000)
                                frame.wait_for_timeout(400)
                                break
                        except Exception:
                            continue

                day_loc = frame.locator('td, button, [role="gridcell"]').filter(
                    has_text=_re.compile(rf'^\s*{target_day}\s*$')
                )
                if day_loc.count() > 0:
                    day_loc.first.click(force=True)
                    frame.wait_for_timeout(350)
                    day_loc.first.click(force=True)
                    frame.wait_for_timeout(400)
                    log.append(f"step3-cal: clicked day {target_day}")
                else:
                    log.append(f"step3-cal: day {target_day} not found for {target_month}")

            # ── Step 4: apply / confirm ───────────────────────────────────────
            applied = False
            for apply_sel in [
                'button:has-text("Apply")',
                'button:has-text("Update")',
                'button:has-text("Done")',
                '[data-testid="date-apply"]',
            ]:
                try:
                    loc = frame.locator(apply_sel)
                    if loc.count() > 0 and loc.first.is_visible(timeout=1_500):
                        loc.first.click(force=True, timeout=3_000)
                        frame.wait_for_timeout(800)
                        applied = True
                        log.append(f"step4: applied via {apply_sel}")
                        break
                except Exception as e:
                    log.append(f"step4: {apply_sel} err: {e}")

            if not applied:
                self._page.keyboard.press("Enter")
                frame.wait_for_timeout(600)
                log.append("step4: applied via Enter")

            snap("step4_done")

        except Exception as e:
            log.append(f"EXCEPTION: {e}")
            snap("exception")
            try:
                self._page.keyboard.press("Escape")
                frame.wait_for_timeout(400)
            except Exception:
                pass

        Path(".streamlit/debug_date_filter_err.txt").write_text("\n".join(log), encoding="utf-8")

    def _open_filter_dropdown(self, frame: "Frame", label: str) -> None:
        """Open a Looker filter dropdown by clicking the chip after its label."""
        # Find the chip's coordinates via JS, then use a real Playwright mouse click
        chip_info = frame.evaluate(
            """(label) => {
                const allEls = [...document.querySelectorAll('*')];
                let labelIdx = -1;
                for (let i = 0; i < allEls.length; i++) {
                    if (allEls[i].children.length === 0) {
                        const t = (allEls[i].innerText || allEls[i].textContent || '').trim();
                        if (t === label) { labelIdx = i; break; }
                    }
                }
                if (labelIdx === -1) return null;
                const tokens = [...document.querySelectorAll('[data-testid="filter-token"]')];
                for (const tok of tokens) {
                    if (allEls.indexOf(tok) > labelIdx) {
                        const r = tok.getBoundingClientRect();
                        if (r.width > 4 && r.height > 4)
                            return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                    }
                }
                return null;
            }""",
            label,
        )
        if not chip_info:
            frame.screenshot(path=str(Path(".streamlit") / f"debug_fail_{label}.png"))
            raise RuntimeError(f"Could not find filter chip for '{label}'")

        # Real mouse click via page coordinates (iframe offset + chip offset)
        iframe_box = self._page.locator("iframe").first.bounding_box()
        if not iframe_box:
            raise RuntimeError("Could not find Looker iframe bounding box")
        self._page.mouse.click(
            iframe_box["x"] + chip_info["x"],
            iframe_box["y"] + chip_info["y"],
        )
        frame.wait_for_timeout(1_000)  # give dropdown time to animate open

    def _deselect_all(self, frame: "Frame") -> None:
        """Click 'Deselect all' inside an open Looker filter dropdown."""
        for label in ["Deselect all", "Select None", "Clear all"]:
            loc = frame.locator(f'text="{label}"')
            if loc.count() > 0:
                try:
                    loc.first.scroll_into_view_if_needed(timeout=2_000)
                    loc.first.click(force=True, timeout=3_000)
                    frame.wait_for_timeout(500)
                    return
                except Exception:
                    continue

    def _click_option(self, frame: "Frame", text: str) -> bool:
        """Select a specific option inside an open Looker filter dropdown."""
        import re as _re
        for sel in [
            f'[role="option"]:has-text("{text}")',
            f'[role="checkbox"]:has-text("{text}")',
            f'li:has-text("{text}")',
            f'label:has-text("{text}")',
        ]:
            loc = frame.locator(sel).filter(
                has_text=_re.compile(rf'^\s*{_re.escape(text)}\s*$')
            )
            if loc.count() > 0:
                try:
                    loc.first.scroll_into_view_if_needed(timeout=2_000)
                    loc.first.click(force=True, timeout=3_000)
                    frame.wait_for_timeout(400)
                    return True
                except Exception:
                    continue
        return False

    def _apply_platform(self, frame: "Frame", platform: str) -> None:
        for attempt in range(3):
            self._wait_for_looker_idle(frame)  # ensure no query is running
            self._open_filter_dropdown(frame, "Platform")
            frame.wait_for_timeout(800)   # dropdown fully rendered
            self._deselect_all(frame)
            frame.wait_for_timeout(800)   # deselect settles
            self._click_option(frame, platform)
            frame.wait_for_timeout(600)
            self._page.keyboard.press("Escape")
            frame.wait_for_timeout(1_500)

            # Verify the chip shows the correct platform before proceeding
            chip_text = frame.evaluate("""() => {
                const allEls = [...document.querySelectorAll('*')];
                let labelIdx = -1;
                for (let i = 0; i < allEls.length; i++) {
                    if (allEls[i].children.length === 0 &&
                        (allEls[i].innerText || allEls[i].textContent || '').trim() === 'Platform') {
                        labelIdx = i; break;
                    }
                }
                if (labelIdx === -1) return '';
                const tokens = [...document.querySelectorAll('[data-testid="filter-token"]')];
                for (const tok of tokens) {
                    if (allEls.indexOf(tok) > labelIdx)
                        return (tok.innerText || tok.textContent || '').trim();
                }
                return '';
            }""") or ""

            if platform.lower() in chip_text.lower():
                break  # confirmed correct

    def _apply_queues(self, frame: "Frame", queues: list[str]) -> None:
        self._wait_for_looker_idle(frame)  # ensure no query is running
        self._open_filter_dropdown(frame, "Queue")
        frame.wait_for_timeout(800)
        self._deselect_all(frame)
        frame.wait_for_timeout(600)
        for q in queues:
            self._click_option(frame, q)
            frame.wait_for_timeout(300)
        self._page.keyboard.press("Escape")
        frame.wait_for_timeout(1_500)

    def _wait_for_looker_idle(self, frame: "Frame", timeout: int = 120_000) -> None:
        """Wait until Looker's loading spinner is gone before touching any filter."""
        # Looker shows a circular spinner/cancel button while queries run.
        # Wait up to `timeout` ms for it to disappear.
        try:
            frame.wait_for_function(
                """() => {
                    const selectors = [
                        '[aria-label="Cancel"]',
                        '[class*="spinner"]',
                        '[class*="loading-spinner"]',
                        '[class*="LoadingSpinner"]',
                        '[data-testid*="spinner"]',
                    ];
                    return selectors.every(sel => document.querySelector(sel) === null);
                }""",
                timeout=timeout,
            )
        except Exception:
            pass  # if we can't detect spinner, proceed anyway
        frame.wait_for_timeout(500)  # small settle after spinner clears

    def _click_run(self, frame: "Frame") -> None:
        """Click Looker's Run button with a real Playwright mouse click."""
        try:
            # Scroll to top of frame first so the Run button is in viewport
            frame.evaluate("window.scrollTo(0, 0)")
            frame.wait_for_timeout(300)
            btn = frame.locator('[class*="RunButton"]')
            if btn.count() > 0:
                btn.first.scroll_into_view_if_needed()
                btn.first.click(force=True, timeout=5_000)
                Path(".streamlit/debug_run_click.txt").write_text("clicked via .click(force=True)", encoding="utf-8")
                return
        except Exception as e:
            Path(".streamlit/debug_run_click.txt").write_text(f"locator click failed: {e}", encoding="utf-8")

        # Fallback: use page mouse at button coordinates
        try:
            coords = frame.evaluate("""() => {
                const btn = document.querySelector('[class*="RunButton"]');
                if (!btn) return null;
                const r = btn.getBoundingClientRect();
                return { x: r.left + r.width/2, y: r.top + r.height/2 };
            }""")
            if coords:
                self._page.mouse.click(coords["x"], coords["y"])
                Path(".streamlit/debug_run_click.txt").write_text(f"page mouse click at {coords}", encoding="utf-8")
                return
        except Exception as e:
            pass
        Path(".streamlit/debug_run_click.txt").write_text("nothing worked", encoding="utf-8")

    def _wait_for_refresh(self, frame: "Frame") -> None:
        # Phase 1: click Run — wait for Looker to acknowledge new filters
        # (tiles return to "Load data to see results" = fresh Snowflake query started)
        self._click_run(frame)
        try:
            frame.wait_for_function(
                "document.body.innerText.includes('Load data to see results')",
                timeout=20_000,
            )
        except Exception:
            pass

        # Phase 2: wait for ALL loading tiles to finish (up to 3 min)
        try:
            frame.wait_for_function(
                "!document.body.innerText.includes('Load data to see results')",
                timeout=180_000,
            )
        except Exception:
            pass

        # Phase 3: verify every one of the 10 KPI tiles has a numeric value loaded.
        # Each tile has a unique aria-label button; we check that a digit is visible inside it.
        metrics_check = (
            "() => {"
            "const metrics = " + str(METRICS).replace("'", '"') + ";"
            "return metrics.every(m => {"
            "  const btn = document.querySelector('[aria-label=\"' + m + ' - Tile actions\"]');"
            "  if (!btn) return false;"
            "  let node = btn.parentElement;"
            "  for (let i = 0; i < 10 && node && node !== document.body; i++) {"
            "    const leaves = [...node.querySelectorAll('*')].filter(c => c.children.length === 0);"
            "    for (const leaf of leaves) {"
            "      const t = (leaf.innerText || leaf.textContent || '').trim();"
            "      if (/^\\d/.test(t)) return true;"
            "    }"
            "    node = node.parentElement;"
            "  }"
            "  return false;"
            "});"
            "}"
        )
        try:
            frame.wait_for_function(metrics_check, timeout=60_000)
        except Exception:
            pass  # some metrics may genuinely have no data (e.g. zero activity)

        frame.wait_for_timeout(2_000)  # final render settle

    def _extract_cards(self, frame: "Frame") -> dict:
        # Debug: capture page screenshot + all frame text nodes
        try:
            self._page.screenshot(path=".streamlit/debug_frame.png")
        except Exception:
            pass
        try:
            visible = frame.evaluate("""() => {
                const out = [];
                // All text nodes
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                while (walker.nextNode()) {
                    const t = walker.currentNode.textContent.trim();
                    if (t) out.push(t);
                }
                // Also check iframes within the frame
                const subframes = [...document.querySelectorAll('iframe')];
                out.push('SUB_IFRAMES:' + subframes.length);
                // Canvas elements (Looker may use canvas)
                const canvases = [...document.querySelectorAll('canvas')];
                out.push('CANVASES:' + canvases.length);
                return out.join(' | ');
            }""")
            Path(".streamlit/debug_frame_text.txt").write_text(visible or "empty", encoding="utf-8")
        except Exception as e:
            Path(".streamlit/debug_frame_text.txt").write_text(f"Error: {e}", encoding="utf-8")

        data: dict = {}
        for metric in METRICS:
            try:
                value, _ = frame.evaluate(_CARD_JS, metric)
                if value:
                    data[metric] = value
            except Exception:
                pass
        return data
