// Lokalny podgląd panelu bez Vercela i bez prawdziwego GitHuba.
//   node dev/server.mjs            -> http://localhost:8765  (hasło: test)
//   PORT=3000 PANEL_PASSWORD=x node dev/server.mjs
// Endpointy z web/api/ działają naprawdę; zapytania do api.github.com są
// obsługiwane w pamięci (config.json z repozytorium + przykładowe dane).
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT) || 8765;

process.env.GH_TOKEN ||= 'dev-token';
process.env.GH_REPO ||= 'dev/oki-scraper';
process.env.GH_BRANCH ||= 'main';
process.env.PANEL_PASSWORD ||= 'test';

// ---------------------------------------------------------------- udawany GitHub
const sha = (s) => createHash('sha1').update(s).digest('hex');
const files = new Map();
function putFile(path, text) {
  files.set(path, { text, sha: sha(text) });
}
putFile('config.json', await readFile(join(root, 'config.json'), 'utf8'));

const ago = (min) => new Date(Date.now() - min * 60_000).toISOString().replace(/\.\d+Z$/, 'Z');
putFile('data/state.json', JSON.stringify({
  sources: {},
  recent: [
    { title: 'Kurs EPALS (European Paediatric Advanced Life Support) – Zaawansowane zabiegi resuscytacyjne u dzieci',
      link: 'https://oilkrakow.pl/kursy-i-szkolenia/kurs-epals-european-paediatric-advanced-life-support-zaawansowane-zabiegi-resuscytacyjne-u-dzieci/',
      source: 'Kursy i szkolenia', foundAt: ago(95), matched: [] },
    { title: 'XX Zjazd Polskiego Towarzystwa Nadciśnienia Tętniczego',
      link: 'https://oilkrakow.pl/konferencje/xx-zjazd-polskiego-towarzystwa-nadcisnienia-tetniczego/',
      source: 'Konferencje', foundAt: ago(60 * 26), matched: [] },
    { title: 'VII Międzynarodowa Konferencja „Medical Review Auschwitz: Medicine Behind the Barbed Wire”',
      link: 'https://oilkrakow.pl/konferencje/vii-miedzynarodowa-konferencja-medical-review-auschwitz-medicine-behind-the-barbed-wire/',
      source: 'Konferencje', foundAt: ago(60 * 50), matched: ['konferenc'] },
  ],
}, null, 2));

let runId = 1000;
const run = (minAgo, event, conclusion) => ({
  id: ++runId, status: conclusion ? 'completed' : 'in_progress', conclusion, event,
  created_at: ago(minAgo), html_url: `https://github.com/${process.env.GH_REPO}/actions/runs/${runId}`,
});
const runs = [run(43, 'schedule', 'success'), run(163, 'schedule', 'success'), run(283, 'workflow_dispatch', 'success'),
  run(403, 'schedule', 'failure'), run(523, 'schedule', 'success'), run(643, 'schedule', 'success')];

const json = (status, body) => new Response(body === undefined ? null : JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});

async function fakeGithub(url, opts = {}) {
  const u = new URL(url);
  const prefix = `/repos/${process.env.GH_REPO}`;
  const path = u.pathname.startsWith(prefix) ? u.pathname.slice(prefix.length) : u.pathname;
  const method = opts.method || 'GET';
  await new Promise((r) => setTimeout(r, 250 + Math.random() * 300)); // realistyczne opóźnienie

  const fileMatch = path.match(/^\/contents\/(.+)$/);
  if (fileMatch) {
    const f = files.get(fileMatch[1]);
    if (method === 'GET') {
      return f ? json(200, { sha: f.sha, content: Buffer.from(f.text).toString('base64') }) : json(404, { message: 'Not Found' });
    }
    if (method === 'PUT') {
      const body = JSON.parse(opts.body);
      if (f && body.sha !== f.sha) return json(409, { message: 'sha mismatch' });
      putFile(fileMatch[1], Buffer.from(body.content, 'base64').toString('utf8'));
      return json(200, { content: { sha: files.get(fileMatch[1]).sha } });
    }
  }
  if (path.endsWith('/runs') && method === 'GET') return json(200, { workflow_runs: runs.slice(0, 10) });
  if (path.endsWith('/dispatches') && method === 'POST') {
    const r = run(0, 'workflow_dispatch', null);
    runs.unshift(r);
    setTimeout(() => { r.status = 'completed'; r.conclusion = 'success'; }, 20_000);
    return json(204);
  }
  return json(404, { message: `dev: brak atrapy dla ${method} ${path}` });
}

const realFetch = globalThis.fetch;
globalThis.fetch = (url, opts) =>
  String(url).startsWith('https://api.github.com/') ? fakeGithub(String(url), opts) : realFetch(url, opts);

// ---------------------------------------------------------------- serwer
const handlers = {
  '/api/config': (await import('../web/api/config.js')).default,
  '/api/status': (await import('../web/api/status.js')).default,
  '/api/run': (await import('../web/api/run.js')).default,
};

createServer(async (req, res) => {
  const { pathname } = new URL(req.url, 'http://localhost');
  if (handlers[pathname]) return handlers[pathname](req, res);
  if (pathname === '/' || pathname === '/index.html') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    return res.end(await readFile(join(root, 'web/index.html')));
  }
  res.statusCode = 404;
  res.end('Not found');
}).listen(PORT, () => {
  console.log(`Panel: http://localhost:${PORT}  (hasło: ${process.env.PANEL_PASSWORD})`);
});
