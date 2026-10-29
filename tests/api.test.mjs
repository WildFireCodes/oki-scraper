// Testy endpointów panelu (bez sieci): node --test tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import configHandler from '../web/api/config.js';
import statusHandler from '../web/api/status.js';
import runHandler from '../web/api/run.js';
import { validateConfig } from '../web/api/_lib.js';

process.env.GH_TOKEN = 'tok';
process.env.GH_REPO = 'jan/oki';
process.env.PANEL_PASSWORD = 'sekret';

function mockRes() {
  return {
    headers: {}, statusCode: 0, body: null,
    setHeader(k, v) { this.headers[k.toLowerCase()] = v; },
    end(b) { this.body = JSON.parse(b); },
  };
}
const req = (method, body, pass = 'sekret') => ({ method, headers: pass === null ? {} : { 'x-panel-password': pass }, body });
const b64 = (o) => Buffer.from(typeof o === 'string' ? o : JSON.stringify(o), 'utf8').toString('base64');
const goodConfig = {
  sources: [{ name: ' Kursy ', url: 'https://oilkrakow.pl/kursy-i-szkolenia/', api: '', enabled: true }],
  keywords: [{ word: ' konferencja ', message: 'Jest nowa konferencja!' }],
  notifyAllNew: true, defaultMessage: '',
};

function mockFetch(handler) {
  const calls = [];
  globalThis.fetch = async (url, opts = {}) => {
    calls.push({ url, opts });
    const r = await handler(url, opts);
    return { ok: r.status >= 200 && r.status < 300, status: r.status, text: async () => (r.json === undefined ? '' : JSON.stringify(r.json)) };
  };
  return calls;
}
async function call(handler, r) { const res = mockRes(); await handler(r, res); return res; }

test('brak zmiennych środowiskowych -> 500', async () => {
  const saved = process.env.PANEL_PASSWORD; delete process.env.PANEL_PASSWORD;
  const res = await call(configHandler, req('GET'));
  process.env.PANEL_PASSWORD = saved;
  assert.equal(res.statusCode, 500);
  assert.match(res.body.error, /PANEL_PASSWORD/);
});

test('złe lub brakujące hasło -> 401', async () => {
  for (const p of ['zle', '', null]) {
    const res = await call(configHandler, req('GET', undefined, p));
    assert.equal(res.statusCode, 401);
  }
});

test('GET /api/config dekoduje UTF-8 i zwraca sha', async () => {
  const calls = mockFetch(() => ({ status: 200, json: { sha: 'abc', content: b64({ defaultMessage: 'Żółć' }).replace(/(.{20})/g, '$1\n') } }));
  const res = await call(configHandler, req('GET'));
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.sha, 'abc');
  assert.equal(res.body.config.defaultMessage, 'Żółć');
  assert.match(calls[0].url, /repos\/jan\/oki\/contents\/config\.json\?ref=main/);
  assert.equal(calls[0].opts.headers['X-GitHub-Api-Version'], '2022-11-28');
  assert.equal(calls[0].opts.headers.Accept, 'application/vnd.github+json');
});

test('PUT /api/config: walidacja, commit, nowe sha', async () => {
  const calls = mockFetch(() => ({ status: 200, json: { content: { sha: 'nowe' } } }));
  const res = await call(configHandler, req('PUT', { config: goodConfig, sha: 'stare' }));
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.sha, 'nowe');
  const sent = JSON.parse(calls[0].opts.body);
  assert.equal(sent.message, 'Aktualizacja konfiguracji (panel)');
  assert.equal(sent.sha, 'stare');
  const saved = JSON.parse(Buffer.from(sent.content, 'base64').toString('utf8'));
  assert.equal(saved.keywords[0].word, 'konferencja');
  assert.equal(saved.sources[0].name, 'Kursy');
  assert.equal(saved.defaultMessage, 'Jest nowy wpis');
});

test('PUT /api/config: konflikt sha (409 i 422) -> 409', async () => {
  for (const st of [409, 422]) {
    mockFetch(() => ({ status: st, json: { message: 'sha mismatch' } }));
    const res = await call(configHandler, req('PUT', { config: goodConfig, sha: 'x' }));
    assert.equal(res.statusCode, 409);
    assert.match(res.body.error, /Ktoś zmienił konfigurację w międzyczasie/);
  }
});

test('PUT /api/config: zła konfiguracja -> 400 i brak wywołania GitHuba', async () => {
  const calls = mockFetch(() => ({ status: 200, json: {} }));
  const bad = { ...goodConfig, sources: [{ name: 'X', url: 'ftp://x' }] };
  const res = await call(configHandler, req('PUT', { config: bad, sha: 'x' }));
  assert.equal(res.statusCode, 400);
  assert.equal(calls.length, 0);
});

test('walidacja: limity i puste słowa', () => {
  assert.throws(() => validateConfig({ ...goodConfig, keywords: [{ word: '  ', message: '' }] }), /wpisz słowo/);
  assert.throws(() => validateConfig({ ...goodConfig, keywords: Array(51).fill({ word: 'a', message: '' }) }), /50/);
  assert.throws(() => validateConfig({ ...goodConfig, sources: Array(21).fill(goodConfig.sources[0]) }), /20/);
  assert.throws(() => validateConfig({ ...goodConfig, sources: [{ name: '', url: 'https://a.pl' }] }), /nazwę/);
  assert.throws(() => validateConfig({ ...goodConfig, sources: [{ name: 'a', url: 'https://a.pl', api: 'nie-url' }] }), /API/);
});

test('GET /api/status: uruchomienia + recent, brak pliku stanu -> pusta lista', async () => {
  mockFetch((url) => {
    if (url.includes('/actions/workflows/scraper.yml/runs')) {
      return { status: 200, json: { workflow_runs: [{ id: 1, status: 'completed', conclusion: 'success', event: 'schedule', created_at: 't', html_url: 'u', extra: 1 }] } };
    }
    return { status: 404, json: { message: 'Not Found' } };
  });
  const res = await call(statusHandler, req('GET'));
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body.recent, []);
  assert.deepEqual(Object.keys(res.body.runs[0]).sort(), ['conclusion', 'created_at', 'event', 'html_url', 'id', 'status']);
});

test('POST /api/run wysyła workflow_dispatch', async () => {
  const calls = mockFetch(() => ({ status: 204 }));
  const res = await call(runHandler, req('POST', { test: true }));
  assert.equal(res.statusCode, 200);
  assert.match(calls[0].url, /workflows\/scraper\.yml\/dispatches$/);
  assert.deepEqual(JSON.parse(calls[0].opts.body), { ref: 'main', inputs: { test_telegram: 'true' } });
  const res2 = await call(runHandler, req('GET'));
  assert.equal(res2.statusCode, 405);
});

test('nieprawidłowy token GitHub -> czytelny błąd', async () => {
  mockFetch(() => ({ status: 401, json: { message: 'Bad credentials' } }));
  const res = await call(configHandler, req('GET'));
  assert.equal(res.statusCode, 502);
  assert.match(res.body.error, /token/i);
});
