# Obserwator OIL Kraków

Darmowy program, który co kilka godzin sprawdza stronę
[Okręgowej Izby Lekarskiej w Krakowie – Kursy i szkolenia](https://oilkrakow.pl/kursy-i-szkolenia/)
oraz [Konferencje](https://oilkrakow.pl/konferencje/) i wysyła powiadomienie na **Telegram**,
gdy pojawi się nowy wpis. Możesz ustawić własne słowa kluczowe i teksty powiadomień
w prostym panelu w przeglądarce (działa też na telefonie).

Wszystko działa za darmo: GitHub Actions (sprawdzanie), Vercel Hobby (panel) i Telegram Bot API (powiadomienia).

## Jak zacząć

Krok po kroku (bez programowania) opisuje to **[INSTRUKCJA.md](INSTRUKCJA.md)**.

## Co jest w środku

| Plik / folder | Do czego służy |
|---|---|
| `config.json` | Ustawienia: źródła, słowa kluczowe, teksty powiadomień (edytowane z panelu) |
| `data/state.json` | Pamięć programu: które wpisy już widział (zapisuje go sam program) |
| `scraper/` | Program sprawdzający stronę (Python) |
| `.github/workflows/scraper.yml` | Harmonogram uruchamiania na GitHub Actions |
| `web/` | Panel ustawień (Vercel) |
| `dev/server.mjs` | Lokalny podgląd panelu z udawanym GitHubem |
| `tests/` | Testy automatyczne |

## Dla programistów

```bash
pip install -r requirements.txt
python -m scraper --dry-run                 # pokazuje wiadomości zamiast je wysyłać
python -m scraper --test-telegram           # test (wymaga TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID)
SCRAPER_FORCE=api|rss|html|browser python -m scraper --dry-run   # wymuszenie jednej metody pobierania
python -m unittest discover -s tests -t .   # testy Pythona
node --test tests/api.test.mjs              # testy panelu
node dev/server.mjs                         # podgląd panelu: http://localhost:8765 (hasło: test)
```
