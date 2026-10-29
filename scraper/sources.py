"""Pobieranie listy wpisów z jednego źródła: API WordPressa -> RSS -> HTML."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .fetch import BlockedError, FetchError, Fetcher, log
from .text import META_SEP, canonical_link, clean_html, clean_title

API_FIELDS = "id,date,modified,link,title,excerpt,content"
MAX_HTML_PAGES = 6
MIN_LINK_TEXT = 12
TIERS = ("api", "rss", "html")


@dataclass
class Entry:
    id: str
    title: str
    link: str
    text: str = ""
    published: str = ""
    extra: dict = field(default_factory=dict)


class SourceError(Exception):
    pass


def _make_entry(link: str, title: str, text: str, published: str = "", wp_id=None) -> Entry | None:
    cid = canonical_link(link) or (f"wp:{wp_id}" if wp_id else "")
    title = clean_title(title)
    if not cid or not title:
        return None
    if "__trashed" in cid:  # wpis wyrzucony do kosza, który WordPress jeszcze pokazuje
        return None
    return Entry(id=cid, title=title, link=link or "", text=text, published=published)


def _dedupe(entries: list[Entry | None]) -> list[Entry]:
    seen, out = set(), []
    for e in entries:
        if e and e.id not in seen:
            seen.add(e.id)
            out.append(e)
    return out


# ---------------------------------------------------------------- Tier 1: API
def fetch_api(src: dict, fetcher: Fetcher) -> list[Entry]:
    sep = "&" if "?" in src["api"] else "?"
    url = f"{src['api']}{sep}per_page=50&orderby=date&order=desc&_fields={API_FIELDS}"
    r = fetcher.get(url, kind="json", referer=src["url"])
    try:
        data = json.loads(r.text)
    except ValueError as e:
        raise FetchError(f"API nie zwróciło poprawnego JSON: {e}")
    if not isinstance(data, list):
        raise FetchError("API zwróciło nieoczekiwaną odpowiedź")
    out = []
    for item in data:
        title = (item.get("title") or {}).get("rendered", "")
        content = (item.get("content") or {}).get("rendered", "")
        excerpt = (item.get("excerpt") or {}).get("rendered", "")
        text = clean_html(content) or clean_html(excerpt)
        out.append(_make_entry(item.get("link", ""), title, text, item.get("date", ""), item.get("id")))
    return _dedupe(out)


# ---------------------------------------------------------------- Tier 2: RSS
def fetch_rss(src: dict, fetcher: Fetcher) -> list[Entry]:
    url = src["url"].rstrip("/") + "/feed/"
    r = fetcher.get(url, kind="xml", referer=src["url"])
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        raise FetchError(f"RSS nie jest poprawnym XML: {e}")
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    out = []
    for item in root.iter("item"):
        full = item.findtext("content:encoded", default="", namespaces=ns)
        desc = item.findtext("description", default="")
        out.append(
            _make_entry(
                (item.findtext("link") or "").strip(),
                item.findtext("title", default=""),
                clean_html(full) or clean_html(desc),
                item.findtext("pubDate", default=""),
            )
        )
    return _dedupe(out)


# ---------------------------------------------------------------- Tier 3: HTML
def parse_listing(html_text: str, base_url: str) -> list[Entry]:
    soup = BeautifulSoup(html_text, "lxml")
    out: list[Entry] = []
    for box in soup.select(".uc_post_list_box"):
        a = box.select_one(".uc_post_list_title a") or box.select_one("a[href]")
        if not a or not a.get("href"):
            continue
        snippet = box.select_one(".uc_post_content")
        meta = [t.get_text(" ") for t in box.select('.ue-meta-data a[rel~="tag"]')]
        meta += [s.get_text(" ") for s in box.select(".ue-meta-data span")]
        text = clean_html(snippet.get_text("\n") if snippet else "")
        text = f"{text} {META_SEP} {clean_html(' '.join(meta))}".strip()
        out.append(_make_entry(urljoin(base_url, a["href"]), a.get_text(" ") or a.get("title", ""), text))
    if out:
        return _dedupe(out)
    return _dedupe(_generic_links(soup, base_url))


_SKIP_PATH = re.compile(r"/(page/\d+|feed|wp-content|wp-json|tag|category|kategoria[^/]*)(/|$)")


def _generic_links(soup: BeautifulSoup, base_url: str) -> list[Entry | None]:
    for tag in soup(["nav", "header", "footer", "aside", "script", "style"]):
        tag.decompose()
    root = soup.select_one("main, article, #content, .entry-content, .site-content") or soup.body or soup
    host = urlsplit(base_url).netloc.lower()
    base_c = canonical_link(base_url)
    out = []
    for a in root.find_all("a", href=True):
        text = clean_html(a.get_text(" "))
        if len(text) < MIN_LINK_TEXT:
            continue
        href = urljoin(base_url, a["href"])
        parts = urlsplit(href)
        if parts.scheme not in ("http", "https") or parts.netloc.lower() != host:
            continue
        if canonical_link(href) == base_c or _SKIP_PATH.search(parts.path):
            continue
        out.append(_make_entry(href, text, ""))
    return out


def _num_pages(html_text: str) -> int:
    m = re.search(r"querydata='([^']*)'", html_text)
    if m:
        try:
            return int(json.loads(unescape(m.group(1))).get("num_pages", 1))
        except (ValueError, TypeError):
            pass
    return 1


def fetch_html(src: dict, fetcher: Fetcher, use_browser: bool = False) -> list[Entry]:
    base = src["url"]
    entries: list[Entry] = []
    pages = 1
    page = 1
    prev = None
    while page <= min(pages, MAX_HTML_PAGES):
        url = base if page == 1 else base.rstrip("/") + f"/page/{page}/"
        try:
            if use_browser:
                body = fetcher.get_html_browser(url)
            else:
                try:
                    body = fetcher.get(url, kind="html", referer=prev).text
                except BlockedError:
                    log("  strona zablokowała zwykłe zapytanie – używam przeglądarki")
                    use_browser = True  # kolejne strony od razu przez przeglądarkę
                    body = fetcher.get_html_browser(url)
        except FetchError as e:
            if page > 1 and e.status in (404, 410):
                break  # brak dalszych stron (np. stronicowanie przez AJAX)
            raise
        if page == 1:
            pages = _num_pages(body)
        got = parse_listing(body, url)
        if page > 1 and not any(e.id not in {x.id for x in entries} for e in got):
            break
        entries += got
        prev = url
        page += 1
    return _dedupe(entries)


# ---------------------------------------------------------------- całość
def fetch_source(src: dict, fetcher: Fetcher, force: str | None = None) -> tuple[list[Entry], str]:
    """Zwraca (wpisy, nazwa_użytej_metody). Rzuca SourceError, gdy wszystkie metody zawiodą."""
    force = (force or "").strip().lower() or None
    if force == "browser":
        tiers = ["browser"]
    elif force in TIERS:
        tiers = [force]
    else:
        tiers = [t for t in TIERS if t != "api" or src.get("api")]
    errors = []
    for tier in tiers:
        try:
            if tier == "api":
                if not src.get("api"):
                    raise FetchError("brak adresu API w konfiguracji")
                entries = fetch_api(src, fetcher)
            elif tier == "rss":
                entries = fetch_rss(src, fetcher)
            elif tier == "html":
                entries = fetch_html(src, fetcher)
            else:
                entries = fetch_html(src, fetcher, use_browser=True)
            if entries:
                return entries, tier
            errors.append(f"{tier}: 0 wpisów")
        except Exception as e:
            errors.append(f"{tier}: {e}")
        log(f"  metoda {tier} nie zadziałała: {errors[-1]}")
    raise SourceError("; ".join(errors))
