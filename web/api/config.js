// GET  /api/config  -> {config, sha}
// PUT  /api/config  -> body {config, sha}; zapisuje config.json w repozytorium
import {
  CONFIG_PATH, HttpError, decodeContent, githubFailure, gh, readJsonBody, readRepoFile, route, validateConfig,
} from './_lib.js';

export default route(['GET', 'PUT'], async (req, cfg) => {
  if (req.method === 'GET') {
    const r = await readRepoFile(cfg, CONFIG_PATH);
    if (!r.ok) throw githubFailure(r, 'odczyt config.json');
    let config;
    try {
      config = JSON.parse(decodeContent(r.data.content));
    } catch {
      throw new HttpError(502, 'Plik config.json w repozytorium jest uszkodzony.');
    }
    return { config, sha: r.data.sha };
  }

  const body = await readJsonBody(req);
  if (!body || typeof body.sha !== 'string' || !body.sha) {
    throw new HttpError(400, 'Brak identyfikatora wersji (sha) – odśwież stronę.');
  }
  const config = validateConfig(body.config);
  const content = Buffer.from(JSON.stringify(config, null, 2) + '\n', 'utf8').toString('base64');
  const r = await gh(cfg, `/contents/${CONFIG_PATH}`, {
    method: 'PUT',
    body: { message: 'Aktualizacja konfiguracji (panel)', content, sha: body.sha, branch: cfg.branch },
  });
  if (r.status === 409 || r.status === 422) {
    throw new HttpError(409, 'Ktoś zmienił konfigurację w międzyczasie — odśwież');
  }
  if (!r.ok) throw githubFailure(r, 'zapis config.json');
  return { ok: true, sha: r.data.content.sha, config };
});
