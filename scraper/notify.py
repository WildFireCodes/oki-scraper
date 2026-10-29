"""Wysyłanie powiadomień na Telegram i budowanie ich treści."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from html import escape

from .text import extract_details

DEFAULT_MESSAGE = "Jest nowy wpis"
MAX_PER_SOURCE = 15
TELEGRAM_LIMIT = 4000


class ConfigError(Exception):
    pass


class TelegramError(Exception):
    pass


def e(text: str) -> str:
    return escape(text or "", quote=False)


def build_entry_message(entry, source_name: str, message: str, matched: list[str]) -> str:
    icon = "🎯" if matched else "🔔"
    lines = [f"{icon} <b>{e(message)}</b>", f"📂 {e(source_name)}", "", f"<b>{e(entry.title)}</b>"]
    if matched:
        lines.append(f"🔑 Słowo kluczowe: {e(', '.join(matched))}")
    details = extract_details(entry.text)
    if "termin" in details:
        lines.append(f"📅 Termin: {e(details['termin'])}")
    if "miejsce" in details:
        lines.append(f"📍 Miejsce: {e(details['miejsce'])}")
    if "koszt" in details:
        lines.append(f"💰 Koszt: {e(details['koszt'])}")
    if entry.link:
        lines.append(f"🔗 {e(entry.link)}")
    return "\n".join(lines)


def build_summary_message(source_name: str, count: int, listing_url: str) -> str:
    return (
        f"…i jeszcze {count} {_wpisow(count)} w: <b>{e(source_name)}</b>\n"
        f"🔗 {e(listing_url)}"
    )


def wpisy(n: int) -> str:
    """'1 wpis', '3 wpisy', '13 wpisów'."""
    if n == 1:
        return "1 wpis"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} wpisy"
    return f"{n} wpisów"


def _wpisow(n: int) -> str:
    """Polska odmiana: 'nowy wpis' (1), 'nowe wpisy' (2-4), 'nowych wpisów' (5+)."""
    if n == 1:
        return "nowy wpis"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "nowe wpisy"
    return "nowych wpisów"


class Notifier:
    def __init__(self, token: str | None, chat_ids: str | None, dry_run: bool = False):
        self.dry_run = dry_run
        self.token = (token or "").strip()
        self.chat_ids = [c.strip() for c in (chat_ids or "").split(",") if c.strip()]
        if not dry_run and (not self.token or not self.chat_ids):
            raise ConfigError(
                "Brak danych do Telegrama: ustaw sekrety TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID "
                "(GitHub → Settings → Secrets and variables → Actions). Szczegóły w INSTRUKCJA.md."
            )

    def send(self, text: str) -> None:
        if len(text) > TELEGRAM_LIMIT:
            text = text[: TELEGRAM_LIMIT - 1] + "…"
        if self.dry_run:
            print("----- [dry-run] wiadomość Telegram -----")
            print(text)
            print("-----")
            return
        errors, ok = [], 0
        for chat in self.chat_ids:
            try:
                self._send_one(chat, text)
                ok += 1
            except TelegramError as exc:
                errors.append(f"czat {chat}: {exc}")
        for err in errors:
            print(f"::warning::Telegram – {err}", flush=True)
        if not ok:
            raise TelegramError("; ".join(errors))

    def _send_one(self, chat_id: str, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
            }
        ).encode("utf-8")
        for attempt in range(4):
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp.read()
                return
            except urllib.error.HTTPError as err:
                body = err.read().decode("utf-8", "replace")
                try:
                    info = json.loads(body)
                except ValueError:
                    info = {}
                if err.code == 429 and attempt < 3:
                    wait = int((info.get("parameters") or {}).get("retry_after", 5)) + 1
                    print(f"  Telegram prosi o odczekanie {wait} s", flush=True)
                    time.sleep(min(wait, 120))
                    continue
                raise TelegramError(f"HTTP {err.code}: {info.get('description', body[:200])}")
            except (urllib.error.URLError, TimeoutError, OSError) as err:
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                # Treść błędu nie zawiera adresu z tokenem.
                raise TelegramError(f"błąd połączenia: {type(err).__name__}")
        raise TelegramError("nie udało się wysłać wiadomości")


def notifier_from_env(dry_run: bool) -> Notifier:
    return Notifier(os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID"), dry_run)
