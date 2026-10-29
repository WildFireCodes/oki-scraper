# Instrukcja uruchomienia – krok po kroku

Ta instrukcja prowadzi przez całą konfigurację. Nie musisz nic programować – wystarczy klikać i kopiować.
Całość zajmie ok. 30–40 minut i **nic nie kosztuje**.

## 1. Jak to działa

```
 GitHub Actions  ──(co kilka godzin)──►  strona OIL Kraków
       │                                      │
       │ ◄──────── lista kursów i konferencji ┘
       ▼
 porównanie z tym, co już było (plik data/state.json)
       │
       ▼
   Telegram  ──►  wiadomość na Twoim telefonie

 Panel na Vercel  ──►  zapisuje ustawienia w pliku config.json w Twoim repozytorium na GitHubie
                       (słowa kluczowe, teksty powiadomień, źródła)
```

- **GitHub Actions** to darmowy „budzik z komputerem”: o ustalonych godzinach uruchamia program.
- **Telegram** dostarcza powiadomienia na telefon.
- **Panel (Vercel)** to strona internetowa, na której zmieniasz ustawienia bez grzebania w plikach.

Potrzebujesz kont: Telegram (już pewnie masz), GitHub i Vercel (oba darmowe).

---

## 2. Telegram: bot i numer czatu

### 2.1. Utworzenie bota
1. W Telegramie wyszukaj **@BotFather** (z niebieskim znaczkiem weryfikacji) i otwórz rozmowę.
2. Wyślij komendę `/newbot`.
3. Podaj nazwę bota (np. „OIL Kraków powiadomienia”), a potem nazwę użytkownika, która musi kończyć się na `bot` (np. `oil_krakow_jan_bot`).
4. BotFather odpowie wiadomością z **tokenem** – długim ciągiem znaków, np. `123456789:AAH...`. **Skopiuj go i zachowaj w bezpiecznym miejscu.** Token to hasło do bota – nikomu go nie pokazuj.

### 2.2. Napisz do swojego bota
Wyszukaj swojego nowego bota po nazwie użytkownika, otwórz rozmowę i wyślij `/start`.
(Bez tego bot nie może do Ciebie pisać.)

### 2.3. Sprawdź numer swojego czatu
1. W przeglądarce otwórz adres (wstaw swój token w miejsce `<TOKEN>`):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
2. Na stronie znajdź fragment w rodzaju `"chat":{"id":123456789,...}`. **Liczba po `"id":` to numer Twojego czatu.**
3. Jeśli widzisz tylko `{"ok":true,"result":[]}`, wyślij botowi jeszcze jedną wiadomość i odśwież stronę.

**Alternatywa:** w Telegramie wyszukaj **@userinfobot**, wyślij mu `/start` – odpowie Twoim numerem („Id”).

### 2.4. (Opcjonalnie) Powiadomienia w grupie
Jeśli chcesz, by powiadomienia dostawało więcej osób:
1. Utwórz grupę w Telegramie i **dodaj do niej swojego bota**.
2. Napisz w grupie dowolną wiadomość (np. `/start@nazwa_twojego_bota`).
3. Otwórz ponownie `getUpdates` – numer grupy jest **ujemny**, np. `-1001234567890`.
4. W sekrecie `TELEGRAM_CHAT_ID` (krok 3.4) możesz podać kilka numerów **oddzielonych przecinkami**,
   np. `123456789,-1001234567890`.

---

## 3. GitHub: własna kopia programu

### 3.1. Konto
Załóż darmowe konto na <https://github.com> (jeśli jeszcze go nie masz).

### 3.2. Własne, prywatne repozytorium
1. Otwórz stronę repozytorium, które dostałeś od autora programu (jest oznaczone jako **Template** – szablon).
   Jeśli to repozytorium jest prywatne, autor musi najpierw dodać Cię jako współpracownika
   (**Settings → Collaborators**), inaczej nie zobaczysz przycisku z kroku 2.
2. Kliknij zielony przycisk **Use this template → Create a new repository**.
3. Wybierz swoje konto jako właściciela, wpisz nazwę (np. `oki-scraper`) i zaznacz **Private** (prywatne).
4. Kliknij **Create repository**.

> **Dlaczego nie „Fork”?** W forkach GitHub wyłącza harmonogramy (zaplanowane uruchomienia),
> więc program nie sprawdzałby strony sam. Szablon tego problemu nie ma.

### 3.3. Pozwól programowi zapisywać swoją pamięć
W swoim repozytorium: **Settings → Actions → General**, przewiń do **Workflow permissions**,
wybierz **Read and write permissions** i kliknij **Save**.

Jeśli w zakładce **Actions** widzisz komunikat z przyciskiem
„I understand my workflows, go ahead and enable them” – kliknij go.

### 3.4. Sekrety (dane do Telegrama)
**Settings → Secrets and variables → Actions → New repository secret**. Dodaj dwa sekrety:

| Name | Secret (wartość) |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token z kroku 2.1 |
| `TELEGRAM_CHAT_ID` | numer czatu z kroku 2.3 (lub kilka po przecinku) |

Nazwy muszą być wpisane dokładnie tak, wielkimi literami.

### 3.5. Pierwsze uruchomienie
1. Zakładka **Actions** → po lewej **Sprawdzanie strony OIL** → przycisk **Run workflow** (po prawej).
2. Najpierw możesz zaznaczyć **Wyślij tylko testowe powiadomienie** i kliknąć zielone **Run workflow** –
   po chwili dostaniesz na Telegramie wiadomość testową.
3. Potem uruchom jeszcze raz, **bez** zaznaczania tej opcji. Po ok. minucie dostaniesz wiadomości
   „✅ Zaczynam obserwować: Kursy i szkolenia (…)” oraz to samo dla Konferencji.
   Od tej pory powiadomienia będą przychodzić tylko o **nowych** wpisach.

### 3.6. Klucz dla panelu (token dostępu)
Panel musi mieć prawo zmieniać plik z ustawieniami i uruchamiać sprawdzanie.
1. Kliknij swoje zdjęcie profilowe (prawy górny róg) → **Settings** → na samym dole lewego menu **Developer settings**.
2. **Personal access tokens → Fine-grained tokens → Generate new token**.
3. Wypełnij:
   - **Token name:** np. `panel-oki`
   - **Expiration:** wybierz **najdłuższy możliwy** okres (do 1 roku). **Zapisz sobie w kalendarzu przypomnienie** o odnowieniu tokena
     na ok. 2 tygodnie przed terminem (patrz rozdział 8).
   - **Repository access:** **Only select repositories** → wybierz tylko swoje repozytorium `oki-scraper`.
   - **Permissions → Repository permissions:**
     - **Contents:** *Read and write*
     - **Actions:** *Read and write*
     - (*Metadata: Read-only* ustawia się samo.)
4. Kliknij **Generate token** i **od razu skopiuj token** (zaczyna się od `github_pat_…`) – GitHub pokaże go tylko raz.

---

## 4. Vercel: panel ustawień

1. Wejdź na <https://vercel.com/signup>, wybierz plan **Hobby** (darmowy) i **Continue with GitHub**.
2. Po zalogowaniu: **Add New… → Project**.
3. Na liście repozytoriów znajdź swoje `oki-scraper` i kliknij **Import**.
   (Jeśli go nie widać: **Adjust GitHub App Permissions** i zezwól Vercelowi na dostęp do tego repozytorium.)
4. W konfiguracji projektu:
   - **Root Directory:** kliknij **Edit** i wybierz folder **`web`**.
   - **Framework Preset:** **Other**.
   - **Environment Variables** – dodaj cztery zmienne:

     | Name | Wartość |
     |---|---|
     | `GH_TOKEN` | token z kroku 3.6 (`github_pat_…`) |
     | `GH_REPO` | `twoj-login/oki-scraper` (login GitHuba, ukośnik, nazwa repozytorium) |
     | `GH_BRANCH` | `main` |
     | `PANEL_PASSWORD` | wymyślone przez Ciebie **długie** hasło do panelu |

5. Kliknij **Deploy**. Po minucie dostaniesz adres panelu (np. `oki-scraper-xyz.vercel.app`).
6. Otwórz go, wpisz hasło z `PANEL_PASSWORD` i zaloguj się. Dodaj adres do zakładek w telefonie.

> Panel zabezpiecza tylko to hasło – wybierz długie i unikalne.
> Zmiany w ustawieniach (`config.json`) i pamięci programu nie powodują ponownego budowania panelu, więc nie zużywasz limitów Vercela.

---

## 5. Korzystanie z panelu

- **Słowa kluczowe** – tabela: *słowo* oraz *tekst powiadomienia*. Gdy nowy wpis zawiera słowo, dostaniesz
  powiadomienie z tym tekstem (np. „Jest nowa konferencja!”). Puste pole tekstu = tekst domyślny.
  Dodajesz wiersze przyciskiem **+ Dodaj słowo**, usuwasz przyciskiem **Usuń**.
  - Wielkość liter i polskie znaki nie mają znaczenia („lodz” znajdzie „Łódź”).
  - Słowo jest szukane także wewnątrz wyrazów – „konferenc” znajdzie „konferencja”, „konferencji”, „konferencje”.
    Dlatego lepiej wpisywać rdzeń słowa, a nie jego formę.
  - Szukamy w tytule i w całym opisie wpisu.
  - Gdy wpis pasuje do kilku słów, użyty jest tekst pierwszego z listy (od góry), a w wiadomości widać wszystkie pasujące słowa.
- **Ogólne**
  - **Powiadamiaj o każdym nowym wpisie** – włączone: dostajesz powiadomienie o wszystkim, co nowe
    (z tekstem domyślnym, jeśli nie pasuje żadne słowo). Wyłączone: tylko o wpisach ze słowami kluczowymi.
  - **Domyślny tekst powiadomienia** – domyślnie „Jest nowy wpis”.
- **Źródła** – strony, które są sprawdzane. Możesz dodać kolejną (wpisz nazwę i adres strony z listą wpisów)
  lub tymczasowo wyłączyć źródło. Adres API jest opcjonalny.
- **Zapisz** – zapisuje ustawienia. Obowiązują od następnego sprawdzania.
- **Uruchom sprawdzanie teraz** – od razu sprawdza stronę (używa zapisanych ustawień). Wynik widać w sekcji „Ostatnie uruchomienia” po ok. minucie.
- **Wyślij testowe powiadomienie** – wysyła na Telegram wiadomość z podsumowaniem ustawień. Dobry sposób, by sprawdzić, czy wszystko działa.
- **Ostatnie uruchomienia** i **Ostatnie znalezione wpisy** – podgląd, co się działo (ikony: ✅ udane, ❌ błąd, ⏳ w toku).

---

## 6. Harmonogram

Program sprawdza stronę o stałych godzinach **czasu polskiego**: **02:00** oraz **co 2 godziny od 08:00 do 20:00**
(8, 10, 12, 14, 16, 18, 20) – razem 8 razy na dobę. Faktycznie uruchomienia startują w okolicach **:17** po pełnej godzinie
(GitHub jest w pełnych godzinach mocno obciążony).

GitHub podaje godziny tylko w czasie UTC, a w Polsce zmienia się czas letni/zimowy. Dlatego w pliku
`.github/workflows/scraper.yml` są **dwie linie harmonogramu** (letnia i zimowa), a dodatkowy krok „Bramka”
przepuszcza zawsze tylko tę, która pasuje do aktualnej pory roku. Druga jest pomijana (to normalne – w Actions
zobaczysz wtedy krótkie, „puste” uruchomienie).

| Czas polski | UTC latem (CEST, +2 h) | UTC zimą (CET, +1 h) |
|---|---|---|
| 02:17 | 00:17 | 01:17 |
| 08:17 | 06:17 | 07:17 |
| 10:17 | 08:17 | 09:17 |
| 12:17 | 10:17 | 11:17 |
| 14:17 | 12:17 | 13:17 |
| 16:17 | 14:17 | 15:17 |
| 18:17 | 16:17 | 17:17 |
| 20:17 | 18:17 | 19:17 |

**Jak zmienić godziny:** w repozytorium otwórz plik `.github/workflows/scraper.yml`, kliknij ikonę ołówka (Edit)
i zmień **dwie linie `- cron:`** na górze pliku:
- **pierwsza** (letnia): godziny UTC = godzina polska minus 2,
- **druga** (zimowa): godziny UTC = godzina polska minus 1.

Zachowaj cudzysłowy i kolejność (pierwsza letnia, druga zimowa). Pierwsza liczba (`17`) to minuta. Zatwierdź zmianę przyciskiem **Commit changes**.
Pamiętaj, że godzina „0” w UTC to np. 02:00 latem, a 23 + 2 = 01:00 następnego dnia.

**Opóźnienia:** GitHub nie gwarantuje punktualności – uruchomienie może się spóźnić o kilka, a czasem kilkanaście minut.
Dwa razy w roku, w noc zmiany czasu, jedno sprawdzenie może zostać pominięte – nie ma to znaczenia.

---

## 7. Koszty i limity

Wszystko jest **darmowe**:

- **GitHub Actions** – prywatne repozytorium ma 2000 darmowych minut miesięcznie. Pełne sprawdzenie zajmuje ok. 1 minuty:
  8 uruchomień × ok. 1 min × 30 dni ≈ **240 minut miesięcznie**. Do tego dochodzi 8 krótkich „pustych” uruchomień dziennie
  (linia harmonogramu nieodpowiednia dla pory roku, patrz rozdział 6), które GitHub też zaokrągla do 1 minuty – razem
  ok. **480 minut miesięcznie**, czyli ok. 24% limitu.
- **Vercel Hobby** – plan darmowy, przeznaczony do użytku **niekomercyjnego** (to Twoje osobiste użycie).
- **Telegram Bot API** – bezpłatne.
- Zalecamy **prywatne** repozytorium. Gdyby było publiczne, każdy mógłby zobaczyć Twoje słowa kluczowe i ustawienia,
  a GitHub **wyłącza harmonogramy w publicznych repozytoriach po 60 dniach bez aktywności**.
  (W prywatnym repozytorium program sam zapisuje stan co najmniej raz na dobę, więc nic nie wygasa.)

---

## 8. Rozwiązywanie problemów

**Nie przychodzą żadne powiadomienia**
1. W Actions otwórz ostatnie uruchomienie – czy jest zielone (✅)? Jeśli czerwone – kliknij je i przeczytaj błąd (patrz niżej).
2. W panelu kliknij **Wyślij testowe powiadomienie**. Jeśli test nie dochodzi: sprawdź sekrety `TELEGRAM_BOT_TOKEN` i
   `TELEGRAM_CHAT_ID` (bez spacji, token w całości) oraz czy napisałeś `/start` do bota.
3. Pamiętaj, że powiadomienia dostajesz tylko o **nowych** wpisach. Jeśli na stronie nic się nie zmieniło, nic nie przyjdzie.
4. Sprawdź, czy w ustawieniach „Powiadamiaj o każdym nowym wpisie” nie jest wyłączone, a słowa kluczowe pasują.

**Wiadomość „⚠️ Problem z obserwowaniem…”**
Program kilka razy z rzędu nie mógł pobrać strony (np. awaria strony OIL albo zmiana jej budowy).
Zwykle problem sam znika – wtedy przyjdzie „✅ … znów działa”. Jeśli ostrzeżenia się powtarzają, skontaktuj się z autorem programu
i prześlij mu link do czerwonego uruchomienia w Actions.

**Panel pokazuje „Nieprawidłowe hasło” (401)**
Wpisz hasło ustawione w Vercel jako `PANEL_PASSWORD`. Gdy go nie pamiętasz: Vercel → projekt → **Settings → Environment Variables**
→ zmień `PANEL_PASSWORD`, potem **Deployments → ⋯ → Redeploy**.

**Panel pokazuje błąd o tokenie GitHub / brak dostępu**
Token z kroku 3.6 wygasł lub ma za małe uprawnienia. Wygeneruj nowy (krok 3.6), a następnie w Vercel:
**Settings → Environment Variables → `GH_TOKEN` → Edit**, wklej nowy token, zapisz i zrób **Redeploy**.
Zapisz sobie datę następnego wygaśnięcia.

**Panel pokazuje „Ktoś zmienił konfigurację w międzyczasie – odśwież”**
Odśwież stronę (F5) i wprowadź zmiany jeszcze raz.

**Jak zobaczyć logi (dziennik działania)**
GitHub → Twoje repozytorium → **Actions** → kliknij uruchomienie → kliknij zadanie **scrape** → rozwiń krok
**Sprawdź stronę OIL**. Zobaczysz, ile wpisów pobrano i z jakiej metody, oraz ewentualne błędy.

**Chcę przestać dostawać powiadomienia**
Actions → **Sprawdzanie strony OIL** → menu **⋯** → **Disable workflow**.
