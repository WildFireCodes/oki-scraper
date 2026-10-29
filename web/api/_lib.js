// Wspólne funkcje dla endpointów panelu: autoryzacja, GitHub, walidacja konfiguracji.
// Plik zaczyna się od "_", więc Vercel nie traktuje go jako osobnego adresu API.
import { createHash, timingSafeEqual } from 'node:crypto';

export const WORKFLOW_FILE = 'scraper.yml';
export const CONFIG_PATH = 'config.json';
export const STATE_PATH = 'data/state.json';
export const DEFAULT_MESSAGE = 'Jest nowy wpis';

export class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// ---------------------------------------------------------------- środowisko i autoryzacja
export function getEnv(env = process.env) {
  const missing = ['GH_TOKEN', 'GH_REPO', 'PANEL_PASSWORD'].filter((k) => !env[k]);
  if (missing.length) {
    throw new HttpError(
      500,
      `Panel nie jest skonfigurowany – brakuje zmiennych środowiskowych w Vercel: ${missing.join(', ')}.`,
    );
  }
  if (!/^[\w.-]+\/[\w.-]+$/.test(env.GH_REPO)) {
    throw new HttpError(500, 'Zmienna GH_REPO ma zły format – powinno być: właściciel/nazwa-repozytorium.');
  }
  return {
    token: env.GH_TOKEN,
    repo: env.GH_REPO,
    branch: env.GH_BRANCH || 'main',
    password: env.PANEL_PASSWORD,
  };
}

const sha256 = (s) => createHash('sha256').update(String(s), 'utf8').digest();

export function checkPassword(provided, expected) {
  if (typeof provided !== 'string' || !provided) return false;
  // Porównujemy skróty o stałej długości, więc timingSafeEqual nie rzuca wyjątku.
  return timingSafeEqual(sha256(provided), sha256(expected));
}

export function requireAuth(req, cfg) {
  const header = req.headers?.['x-panel-password'];
  if (!checkPassword(Array.isArray(header) ? header[0] : header, cfg.password)) {
    throw new HttpError(401, 'Nieprawidłowe hasło.');
  }
}

// ---------------------------------------------------------------- GitHub
export async function gh(cfg, path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(`https://api.github.com/repos/${cfg.repo}${path}`, {
      method,
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${cfg.token}`,
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'oki-scraper-panel',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new HttpError(502, 'Nie udało się połączyć z GitHubem. Spróbuj ponownie za chwilę.');
  }
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { message: text.slice(0, 200) };
    }
  }
  return { status: res.status, ok: res.ok, data };
}

// Zamienia błąd GitHuba na zrozumiały komunikat po polsku.
export function githubFailure(r, what) {
  if (r.status === 401) {
    return new HttpError(502, 'GitHub odrzucił token (GH_TOKEN) – jest nieprawidłowy lub wygasł. Wygeneruj nowy i wpisz go w Vercel.');
  }
  if (r.status === 403 || r.status === 404) {
    return new HttpError(
      502,
      `GitHub nie pozwala na dostęp (${what}). Sprawdź GH_REPO oraz uprawnienia tokena (Contents i Actions: Read and write).`,
    );
  }
  return new HttpError(502, `GitHub zwrócił błąd ${r.status} (${what}): ${r.data?.message ?? 'brak szczegółów'}`);
}

export function decodeContent(b64) {
  return Buffer.from(String(b64 || '').replace(/\n/g, ''), 'base64').toString('utf8');
}

export async function readRepoFile(cfg, path) {
  const r = await gh(cfg, `/contents/${path}?ref=${encodeURIComponent(cfg.branch)}`);
  return r;
}

// ---------------------------------------------------------------- walidacja konfiguracji
const isHttpUrl = (s) => {
  try {
    const u = new URL(s);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
};
const str = (v) => (typeof v === 'string' ? v.trim() : '');

export function validateConfig(input) {
  const fail = (msg) => {
    throw new HttpError(400, msg);
  };
  if (!input || typeof input !== 'object' || Array.isArray(input)) fail('Konfiguracja ma zły format.');

  if (!Array.isArray(input.sources)) fail('Brak listy źródeł.');
  if (input.sources.length < 1) fail('Dodaj przynajmniej jedno źródło.');
  if (input.sources.length > 20) fail('Maksymalnie 20 źródeł.');
  const sources = input.sources.map((s, i) => {
    const n = i + 1;
    const name = str(s?.name);
    const url = str(s?.url);
    const api = str(s?.api);
    if (!name) fail(`Źródło nr ${n}: wpisz nazwę.`);
    if (name.length > 100) fail(`Źródło nr ${n}: nazwa jest za długa (maks. 100 znaków).`);
    if (!isHttpUrl(url) || url.length > 500) fail(`Źródło „${name}”: adres strony musi zaczynać się od http:// lub https://.`);
    if (api && (!isHttpUrl(api) || api.length > 500)) fail(`Źródło „${name}”: adres API musi zaczynać się od http:// lub https:// (albo zostaw puste).`);
    const out = { name, url };
    if (api) out.api = api;
    out.enabled = s?.enabled !== false;
    return out;
  });

  if (input.keywords !== undefined && !Array.isArray(input.keywords)) fail('Lista słów kluczowych ma zły format.');
  const rawKw = input.keywords ?? [];
  if (rawKw.length > 50) fail('Maksymalnie 50 słów kluczowych.');
  const keywords = rawKw.map((k, i) => {
    const word = str(k?.word);
    const message = str(k?.message);
    if (!word) fail(`Słowo kluczowe nr ${i + 1}: wpisz słowo.`);
    if (word.length > 100) fail(`Słowo kluczowe „${word.slice(0, 20)}…” jest za długie (maks. 100 znaków).`);
    if (message.length > 300) fail(`Tekst powiadomienia dla „${word}” jest za długi (maks. 300 znaków).`);
    return { word, message };
  });

  const defaultMessage = str(input.defaultMessage) || DEFAULT_MESSAGE;
  if (defaultMessage.length > 300) fail('Domyślny tekst powiadomienia jest za długi (maks. 300 znaków).');

  const config = {
    sources,
    keywords,
    notifyAllNew: input.notifyAllNew !== false,
    defaultMessage,
  };
  if (JSON.stringify(config).length > 60_000) fail('Konfiguracja jest za duża.');
  return config;
}

// ---------------------------------------------------------------- obsługa żądań
export async function readJsonBody(req) {
  let body = req.body;
  if (body === undefined || body === null) {
    const chunks = [];
    for await (const c of req) chunks.push(typeof c === 'string' ? Buffer.from(c) : c);
    body = Buffer.concat(chunks).toString('utf8');
  }
  if (Buffer.isBuffer(body)) body = body.toString('utf8');
  if (typeof body === 'string') {
    if (!body.trim()) return {};
    try {
      return JSON.parse(body);
    } catch {
      throw new HttpError(400, 'Nieprawidłowe dane żądania (JSON).');
    }
  }
  return body;
}

export function send(res, status, payload) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(payload));
}

// Opakowanie: środowisko -> hasło -> metoda -> właściwa funkcja; błędy zamienia na odpowiedź JSON.
export function route(methods, fn) {
  return async function handler(req, res) {
    try {
      const cfg = getEnv();
      requireAuth(req, cfg);
      if (!methods.includes(req.method)) {
        res.setHeader('Allow', methods.join(', '));
        throw new HttpError(405, 'Niedozwolona metoda.');
      }
      send(res, 200, await fn(req, cfg));
    } catch (err) {
      if (err instanceof HttpError) {
        send(res, err.status, { error: err.message });
      } else {
        console.error(err);
        send(res, 500, { error: 'Nieoczekiwany błąd serwera.' });
      }
    }
  };
}
