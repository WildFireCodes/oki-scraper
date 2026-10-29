// GET /api/status -> {runs: [...ostatnie 10 uruchomień], recent: [...ostatnie znalezione wpisy]}
import { STATE_PATH, WORKFLOW_FILE, decodeContent, githubFailure, gh, readRepoFile, route } from './_lib.js';

export default route(['GET'], async (_req, cfg) => {
  const [runsRes, stateRes] = await Promise.all([
    gh(cfg, `/actions/workflows/${WORKFLOW_FILE}/runs?per_page=10`),
    readRepoFile(cfg, STATE_PATH),
  ]);
  if (!runsRes.ok) throw githubFailure(runsRes, 'lista uruchomień');

  const runs = (runsRes.data?.workflow_runs ?? []).slice(0, 10).map((r) => ({
    id: r.id,
    status: r.status,
    conclusion: r.conclusion,
    event: r.event,
    created_at: r.created_at,
    html_url: r.html_url,
  }));

  let recent = [];
  if (stateRes.ok) {
    try {
      const state = JSON.parse(decodeContent(stateRes.data.content));
      if (Array.isArray(state.recent)) recent = state.recent;
    } catch {
      /* uszkodzony plik stanu – pokazujemy pustą listę */
    }
  } else if (stateRes.status !== 404) {
    throw githubFailure(stateRes, 'odczyt data/state.json');
  }
  return { runs, recent };
});
