// POST /api/run  body {test: boolean} -> uruchamia workflow scraper.yml
import { HttpError, WORKFLOW_FILE, githubFailure, gh, readJsonBody, route } from './_lib.js';

export default route(['POST'], async (req, cfg) => {
  const body = await readJsonBody(req);
  const test = body?.test === true;
  const r = await gh(cfg, `/actions/workflows/${WORKFLOW_FILE}/dispatches`, {
    method: 'POST',
    body: { ref: cfg.branch, inputs: { test_telegram: test ? 'true' : 'false' } },
  });
  if (r.status === 422) {
    throw new HttpError(502, `GitHub odrzucił uruchomienie (sprawdź GH_BRANCH): ${r.data?.message ?? ''}`);
  }
  if (!r.ok) throw githubFailure(r, 'uruchomienie workflow');
  return { ok: true, test };
});
