"""Pomocnicze funkcje tekstowe: czyszczenie HTML, adresy, słowa kluczowe."""
from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")


def clean_html(raw: str | None) -> str:
    """HTML -> zwykły tekst (bez znaczników, z rozkodowanymi encjami)."""
    if not raw:
        return ""
    if "<" in raw:
        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        raw = soup.get_text(" ")
    return _WS.sub(" ", html.unescape(raw)).strip()


def clean_title(raw: str | None) -> str:
    return clean_html(raw)


def canonical_link(link: str | None) -> str:
    """Ujednolicony adres wpisu: bez fragmentu (#...), bez końcowego ukośnika."""
    if not link:
        return ""
    parts = urlsplit(link.strip())
    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, parts.netloc.lower(), path, parts.query, ""))


def fold(text: str) -> str:
    """Małe litery, bez polskich znaków (ł -> l itd.), jedna spacja."""
    text = (text or "").casefold().replace("ł", "l")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _WS.sub(" ", text).strip()


def match_keywords(keywords: list[dict], haystack: str) -> list[dict]:
    """Zwraca dopasowane słowa kluczowe (w kolejności z konfiguracji)."""
    folded = fold(haystack)
    found = []
    for kw in keywords:
        word = fold(kw.get("word", ""))
        if word and word in folded:
            found.append(kw)
    return found


# Etykiety, które kończą wartość poprzedniego pola.
_LABELS = (
    "Termin", "Data", "Godzina", "Godziny", "Miejsce", "Koszt", "Cena", "Opłata",
    "Punkty edukacyjne", "Punkty", "Kierownik naukowy", "Kierownik", "Prowadzący",
    "Prowadzenie", "Organizator", "Zapisy", "Liczba miejsc", "Limit miejsc",
    "Wykładowca", "Wykładowcy", "Program", "Adres", "Forma",
)
_LABEL_ALT = "|".join(sorted((re.escape(x) for x in _LABELS), key=len, reverse=True))
# Oddziela treść wpisu od dopisanych znaczników (kategorie, "płatny") z listy HTML.
META_SEP = "¦"
_START = r"(?<![\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ])"


def _field(text: str, names: tuple[str, ...], limit: int = 150) -> str:
    alt = "|".join(re.escape(n) for n in names)
    pattern = re.compile(
        rf"{_START}(?:{alt})\s*:\s*(.+?)(?=\s+(?:{_LABEL_ALT})\s*:|\s*{META_SEP}|\s*$)", re.S
    )
    m = pattern.search(text)
    if not m:
        return ""
    value = _WS.sub(" ", m.group(1)).strip(" ;,")
    if not value.strip(".…"):  # ucięty fragment, np. "Koszt:..."
        return ""
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


def extract_details(text: str) -> dict[str, str]:
    """Wyciąga z tekstu wpisu: termin, miejsce i koszt (jeśli są)."""
    head = _WS.sub(" ", text or "")[:3000]
    out = {
        "termin": _field(head, ("Termin",)) or _field(head, ("Data",)),
        "miejsce": _field(head, ("Miejsce",)),
        "koszt": _field(head, ("Koszt", "Cena", "Opłata")),
    }
    return {k: v for k, v in out.items() if v}
