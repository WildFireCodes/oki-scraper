"""Pobieranie stron: curl_cffi (udaje przeglądarkę) + zapasowo prawdziwa przeglądarka."""
from __future__ import annotations

import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass

from curl_cffi import requests as cffi

# Odciski przeglądarek (nazwy sprawdzone w curl_cffi 0.17).
IMPERSONATE = ["chrome", "chrome131", "safari18_0"]
ACCEPT_LANGUAGE = "pl-PL,pl;q=0.9,en-US;q=0.7,en;q=0.6"
MAX_ATTEMPTS = 3

# Pewne oznaki strony blokady (zawsze).
STRONG_MARKERS = [
    "just a moment...", "attention required", "_incapsula_resource",
    "px-captcha", "captcha-delivery",
]
# Te ciągi trafiają też na zwykłe strony za Cloudflare, więc liczą się tylko
# w małych odpowiedziach (strona blokady jest niewielka).
WEAK_MARKERS = ["cf-chl", "challenge-platform", "datadome"]
WEAK_MAX_SIZE = 60_000
BLOCK_STATUSES = {403, 429, 503}


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class BlockedError(FetchError):
    """Serwis zablokował zapytanie (antybot)."""


@dataclass
class Response:
    status: int
    text: str
    content: bytes
    headers: dict


def looks_blocked(status: int, body: str) -> bool:
    if status in BLOCK_STATUSES:
        return True
    low = body[:300_000].lower()
    if any(m in low for m in STRONG_MARKERS):
        return True
    return len(body) < WEAK_MAX_SIZE and any(m in low for m in WEAK_MARKERS)


def log(msg: str) -> None:
    print(msg, flush=True)


class Fetcher:
    def __init__(self) -> None:
        self._sessions: dict[str, cffi.Session] = {}
        self._requests = 0
        self._browser: BrowserFetcher | None = None

    # -- krótka, losowa przerwa między zapytaniami (uprzejmość wobec serwisu)
    def _pause(self) -> None:
        if self._requests and not os.environ.get("SCRAPER_NO_DELAY"):
            time.sleep(random.uniform(1.0, 4.0))
        self._requests += 1

    def _session(self, target: str) -> cffi.Session:
        if target not in self._sessions:
            self._sessions[target] = cffi.Session(impersonate=target)  # ciasteczka per sesja
        return self._sessions[target]

    @staticmethod
    def _headers(kind: str, referer: str | None) -> dict:
        headers = {"Accept-Language": ACCEPT_LANGUAGE}
        if kind == "json":
            headers["Accept"] = "application/json, text/plain, */*"
        elif kind == "xml":
            headers["Accept"] = "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"
        else:
            headers["Accept"] = (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            )
        if referer:
            headers["Referer"] = referer
        return headers

    def get(self, url: str, kind: str = "html", referer: str | None = None) -> Response:
        """GET z ponawianiem. kind: html | json | xml. Rzuca FetchError/BlockedError."""
        if kind == "html" and referer is None:
            referer = "https://www.google.com/"
        self._pause()
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            target = IMPERSONATE[attempt % len(IMPERSONATE)]
            try:
                r = self._session(target).get(
                    url, headers=self._headers(kind, referer), timeout=30, allow_redirects=True
                )
                body = r.text
                if r.status_code == 200 and not looks_blocked(r.status_code, body):
                    return Response(r.status_code, body, r.content, dict(r.headers))
                if looks_blocked(r.status_code, body):
                    last = BlockedError(f"blokada ({r.status_code}) przy {url}", r.status_code)
                elif r.status_code in (404, 410):
                    raise FetchError(f"HTTP {r.status_code} dla {url}", r.status_code)
                elif 400 <= r.status_code < 500:
                    raise FetchError(f"HTTP {r.status_code} dla {url}", r.status_code)
                else:
                    last = FetchError(f"HTTP {r.status_code} dla {url}", r.status_code)
            except FetchError as e:
                if not isinstance(e, BlockedError):
                    raise
                last = e
            except Exception as e:  # błędy sieci, TLS, timeout
                last = FetchError(f"błąd sieci ({type(e).__name__}) dla {url}: {e}")
            if attempt < MAX_ATTEMPTS - 1:
                wait = 2 ** (attempt + 1) + random.uniform(0, 2)
                if os.environ.get("SCRAPER_NO_DELAY"):
                    wait = 0.1
                log(f"  ponawiam ({attempt + 1}/{MAX_ATTEMPTS - 1}) za {wait:.0f}s: {last}")
                time.sleep(wait)
        assert last is not None
        raise last

    def get_html_browser(self, url: str) -> str:
        self._pause()
        if self._browser is None:
            self._browser = BrowserFetcher()
        return self._browser.get(url)

    def close(self) -> None:
        for s in self._sessions.values():
            try:
                s.close()
            except Exception:
                pass
        if self._browser is not None:
            self._browser.close()
            self._browser = None


class BrowserFetcher:
    """Prawdziwa (bezgłowa) przeglądarka przez Playwright. Uruchamiana dopiero w razie potrzeby."""

    ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    INIT_SCRIPT = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['pl-PL', 'pl', 'en-US', 'en']});
    """

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._context = None

    def _launch(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(channel="chrome", headless=True, args=self.ARGS)
            log("  przeglądarka: zainstalowany Google Chrome")
        except Exception as e:
            log(f"  Chrome niedostępny ({type(e).__name__}), instaluję Chromium Playwrighta…")
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True, timeout=600,
            )
            self._browser = self._pw.chromium.launch(headless=True, args=self.ARGS)
        major = self._browser.version.split(".")[0]
        ua = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{major}.0.0.0 Safari/537.36"
        )
        self._context = self._browser.new_context(
            user_agent=ua,
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            viewport={"width": 1366, "height": 768},
        )
        self._context.add_init_script(self.INIT_SCRIPT)

    def get(self, url: str) -> str:
        if self._context is None:
            self._launch()
        page = self._context.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            status = resp.status if resp else 0
            deadline = time.time() + 30
            html_text = page.content()
            # Czekamy (do ~30 s), aż zniknie ekran sprawdzania przeglądarki.
            while looks_blocked(200, html_text) and time.time() < deadline:
                page.wait_for_timeout(2000)
                html_text = page.content()
            if looks_blocked(200, html_text):
                raise BlockedError(f"przeglądarka też zablokowana dla {url}", status)
            if status in (404, 410):
                raise FetchError(f"HTTP {status} dla {url}", status)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
                html_text = page.content()
            except Exception:
                pass
            return html_text
        finally:
            page.close()

    def close(self) -> None:
        for obj in (self._context, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._context = self._browser = self._pw = None
