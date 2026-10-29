"""Uruchomienie: python -m scraper [--dry-run] [--config PATH] [--state PATH] [--test-telegram]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from .fetch import Fetcher, log
from .notify import (
    DEFAULT_MESSAGE, MAX_PER_SOURCE, ConfigError, Notifier, TelegramError,
    build_entry_message, build_summary_message, e, notifier_from_env, wpisy,
)
from .sources import SourceError, fetch_source
from .state import (
    add_recent, get_source, load_state, merge_seen, now_iso, save_state_if_changed, source_key,
)
from .text import match_keywords

WARN_AFTER = 3     # ostrzeżenie przy 3. porażce z rzędu
WARN_EVERY = 12    # potem co 12. porażkę
LAST_OK_REFRESH = timedelta(hours=24)


# ------------------------------------------------------------------ konfiguracja
def load_config(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"Nie znaleziono pliku konfiguracji: {path}")
    except ValueError as exc:
        raise ConfigError(f"Plik konfiguracji ({path}) nie jest poprawnym JSON-em: {exc}")
    if not isinstance(raw, dict):
        raise ConfigError("Plik konfiguracji musi być obiektem JSON.")

    sources = []
    for i, s in enumerate(raw.get("sources") or [], 1):
        if not isinstance(s, dict) or not str(s.get("url", "")).startswith(("http://", "https://")):
            raise ConfigError(f"Źródło nr {i} w konfiguracji nie ma poprawnego adresu URL.")
        sources.append(
            {
                "name": str(s.get("name") or s["url"]).strip(),
                "url": str(s["url"]).strip(),
                "api": str(s.get("api") or "").strip(),
                "enabled": s.get("enabled", True) is not False,
            }
        )
    keywords = []
    for kw in raw.get("keywords") or []:
        if isinstance(kw, str):
            kw = {"word": kw}
        if isinstance(kw, dict) and str(kw.get("word", "")).strip():
            keywords.append(
                {"word": str(kw["word"]).strip(), "message": str(kw.get("message") or "").strip()}
            )
    return {
        "sources": sources,
        "keywords": keywords,
        "notifyAllNew": raw.get("notifyAllNew", True) is not False,
        "defaultMessage": str(raw.get("defaultMessage") or "").strip() or DEFAULT_MESSAGE,
    }


def decide(entry, cfg: dict) -> tuple[str, list[str]] | None:
    """(tekst powiadomienia, dopasowane słowa) albo None, gdy nie powiadamiać."""
    matches = match_keywords(cfg["keywords"], f"{entry.title}\n{entry.text}")
    if matches:
        message = matches[0]["message"] or cfg["defaultMessage"]
        return message, [m["word"] for m in matches]
    if cfg["notifyAllNew"]:
        return cfg["defaultMessage"], []
    return None


# ------------------------------------------------------------------ test Telegrama
def test_message(cfg: dict) -> str:
    lines = ["🧪 <b>Testowe powiadomienie</b>", "Obserwator OIL Kraków działa poprawnie.", ""]
    lines.append("<b>Źródła:</b>")
    for s in cfg["sources"]:
        lines.append(f"• {e(s['name'])}" + ("" if s["enabled"] else " (wyłączone)"))
    lines.append("")
    if cfg["keywords"]:
        lines.append("<b>Słowa kluczowe:</b>")
        for kw in cfg["keywords"]:
            lines.append(f"• {e(kw['word'])} → „{e(kw['message'] or cfg['defaultMessage'])}”")
    else:
        lines.append("<b>Słowa kluczowe:</b> brak")
    lines.append("")
    if cfg["notifyAllNew"]:
        lines.append(f"Tryb: powiadamiam o każdym nowym wpisie („{e(cfg['defaultMessage'])}”).")
    else:
        lines.append("Tryb: powiadamiam tylko o wpisach ze słowami kluczowymi.")
    return "\n".join(lines)


# ------------------------------------------------------------------ jedno źródło
def process_source(src: dict, cfg: dict, state: dict, notifier: Notifier, fetcher: Fetcher,
                   all_seen: set[str], force: str | None) -> None:
    key = source_key(src["url"])
    st = get_source(state, key)
    name = src["name"]
    log(f"== {name}")
    try:
        entries, tier = fetch_source(src, fetcher, force)
    except SourceError as exc:
        st["failures"] = int(st.get("failures", 0)) + 1
        n = st["failures"]
        log(f"  BŁĄD ({n}. z rzędu): {exc}")
        print(f"::warning::{name}: nie udało się pobrać wpisów ({exc})", flush=True)
        if n == WARN_AFTER or (n > WARN_AFTER and (n - WARN_AFTER) % WARN_EVERY == 0):
            try:
                notifier.send(
                    f"⚠️ <b>Problem z obserwowaniem: {e(name)}</b>\n"
                    f"Nie udało się pobrać strony już {n} razy z rzędu.\n"
                    f"🔗 {e(src['url'])}\n"
                    "Sprawdź logi w zakładce Actions na GitHubie."
                )
                st["warned"] = True
            except TelegramError as terr:
                log(f"  nie udało się wysłać ostrzeżenia: {terr}")
        return

    log(f"  pobrano {len(entries)} wpisów (metoda: {tier})")
    current_ids = [x.id for x in entries]
    first_time = not st.get("lastOk")
    unsent: set[str] = set()

    if first_time:
        try:
            notifier.send(f"✅ Zaczynam obserwować: <b>{e(name)}</b> ({wpisy(len(entries))})")
        except TelegramError as terr:
            log(f"  nie udało się wysłać komunikatu startowego: {terr}")
    else:
        new = [x for x in entries if x.id not in all_seen]
        log(f"  nowych wpisów: {len(new)}")
        to_send = []
        for x in reversed(new):  # od najstarszego do najnowszego
            d = decide(x, cfg)
            if d:
                to_send.append((x, d))
        skipped = max(0, len(to_send) - MAX_PER_SOURCE)
        to_send = to_send[skipped:]  # zostają najnowsze
        found, sent_ids, failed = [], set(), False
        for x, (message, matched) in to_send:
            try:
                notifier.send(build_entry_message(x, name, message, matched))
            except TelegramError as terr:
                print(f"::error::Telegram: nie udało się wysłać powiadomienia ({terr})", flush=True)
                failed = True
                break
            sent_ids.add(x.id)
            found.append({"title": x.title, "link": x.link, "source": name,
                          "foundAt": now_iso(), "matched": matched})
        if failed:
            # Nie oznaczamy niewysłanych jako widziane – spróbujemy przy następnym uruchomieniu.
            unsent = {x.id for x, _ in to_send if x.id not in sent_ids}
        elif skipped:
            try:
                notifier.send(build_summary_message(name, skipped, src["url"]))
            except TelegramError as terr:
                log(f"  nie udało się wysłać podsumowania: {terr}")
        add_recent(state, list(reversed(found)))

    if st.get("warned"):
        try:
            notifier.send(f"✅ <b>{e(name)}</b> znów działa")
        except TelegramError as terr:
            log(f"  nie udało się wysłać komunikatu o naprawie: {terr}")
    st["failures"] = 0
    st["warned"] = False
    st["seen"] = merge_seen([i for i in current_ids if i not in unsent], st.get("seen", []))
    all_seen.update(st["seen"])
    _touch_last_ok(st)


def _touch_last_ok(st: dict) -> None:
    last = st.get("lastOk")
    try:
        old = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if last else None
    except ValueError:
        old = None
    if old is None or datetime.now(timezone.utc) - old > LAST_OK_REFRESH:
        st["lastOk"] = now_iso()


# ------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="python -m scraper", description="Obserwator stron OIL Kraków")
    ap.add_argument("--dry-run", action="store_true", help="wypisz wiadomości zamiast wysyłać na Telegram")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--state", default="data/state.json")
    ap.add_argument("--test-telegram", action="store_true", help="wyślij testowe powiadomienie i zakończ")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(args.config)
        notifier = notifier_from_env(args.dry_run)
    except ConfigError as exc:
        print(f"::error::{exc}", flush=True)
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 2

    if args.test_telegram:
        try:
            notifier.send(test_message(cfg))
        except TelegramError as exc:
            print(f"::error::Telegram: {exc}", flush=True)
            print(f"BŁĄD: nie udało się wysłać wiadomości testowej: {exc}", file=sys.stderr)
            return 1
        log("Wysłano testowe powiadomienie.")
        return 0

    state = load_state(args.state)
    force = os.environ.get("SCRAPER_FORCE")
    all_seen: set[str] = {i for s in state["sources"].values() for i in s.get("seen", [])}
    fetcher = Fetcher()
    try:
        for src in cfg["sources"]:
            if not src["enabled"]:
                continue
            try:
                process_source(src, cfg, state, notifier, fetcher, all_seen, force)
            except Exception as exc:  # jedno źródło nie może zatrzymać pozostałych
                print(f"::error::{src['name']}: nieoczekiwany błąd {type(exc).__name__}: {exc}", flush=True)
    finally:
        fetcher.close()

    if save_state_if_changed(args.state, state):
        log(f"Zapisano stan: {args.state}")
    else:
        log("Stan bez zmian.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
