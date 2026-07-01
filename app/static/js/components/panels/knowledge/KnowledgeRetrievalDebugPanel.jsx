const { SearchCode } = window.LucideReact || {};

function truncateKnowledgePreview(text) {
  const value = String(text || '');
  return value.length > 360 ? `${value.slice(0, 360)}...` : value;
}

function KnowledgeRetrievalDebugPanel({
  kbId = '',
  documentId = '',
  versionId = '',
  draft,
  onDraftChange,
  onSubmit,
  result = null,
  loading = false,
  errorMessage = '',
}) {
  const candidates = Array.isArray(result && result.candidates) ? result.candidates : [];

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(360px,0.85fr)_minmax(0,1.15fr)]">
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          {SearchCode ? <SearchCode className="h-5 w-5 text-cyan-600" /> : null}
          <h3 className="text-base font-semibold text-slate-900">Retrieval Debug</h3>
        </div>
        <div className="space-y-4">
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">KB ID</div>
            <input type="text" value={draft.kb_id} onChange={(event) => onDraftChange && onDraftChange({ ...draft, kb_id: event.target.value })} className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm" placeholder={kbId || 'risk_domain_knowledge'} />
          </label>
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">Query</div>
            <textarea value={draft.query} onChange={(event) => onDraftChange && onDraftChange({ ...draft, query: event.target.value })} rows={4} className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm" placeholder="什么是多头借贷风险？" />
          </label>
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">Document ID (optional)</div>
            <input type="text" value={draft.document_id} onChange={(event) => onDraftChange && onDraftChange({ ...draft, document_id: event.target.value })} className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm" placeholder={documentId || 'scope current document'} />
          </label>
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">Version ID (optional)</div>
            <input type="text" value={draft.version_id} onChange={(event) => onDraftChange && onDraftChange({ ...draft, version_id: event.target.value })} className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm" placeholder={versionId || 'scope current version'} />
          </label>
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">top_k</div>
            <input type="number" min="1" max="50" value={draft.top_k} onChange={(event) => onDraftChange && onDraftChange({ ...draft, top_k: Math.min(50, Math.max(1, Number(event.target.value) || 10)) })} className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm" />
          </label>
          {errorMessage ? <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{errorMessage}</div> : null}
          <button type="button" onClick={() => onSubmit && onSubmit()} disabled={loading} className="inline-flex items-center justify-center rounded-2xl bg-cyan-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-cyan-700 disabled:cursor-not-allowed disabled:bg-slate-400">
            {loading ? '调试中...' : '执行 retrieval debug'}
          </button>
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between gap-4">
          <h3 className="text-base font-semibold text-slate-900">Candidates & Diagnostics</h3>
          {result && result.diagnostics ? <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{result.diagnostics.candidate_count} candidates</span> : null}
        </div>
        {result ? (
          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
              <div><span className="font-semibold text-slate-900">query</span>：{result.query}</div>
              <div className="mt-1"><span className="font-semibold text-slate-900">kb_id</span>：{result.kb_id}</div>
              <div className="mt-1"><span className="font-semibold text-slate-900">scope</span>：{result.scope && result.scope.scope_type}</div>
              <div className="mt-1"><span className="font-semibold text-slate-900">diagnostics</span>：fusion={result.diagnostics && result.diagnostics.fusion_method} / latency={result.diagnostics && result.diagnostics.latency_ms}ms</div>
            </div>
            <div className="space-y-3">
              {candidates.map((candidate) => (
                <div key={`${candidate.chunk_id}-${candidate.rank}`} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-slate-900">#{candidate.rank} · {candidate.section_path || 'No section path'}</div>
                      <div className="mt-1 text-xs text-slate-500">{candidate.document_id} / {candidate.version_id}</div>
                    </div>
                    <div className="text-right text-xs text-slate-500">
                      <div>RRF：{candidate.scores && candidate.scores.rrf_score}</div>
                      <div>Vector：{candidate.scores && candidate.scores.vector_score != null ? candidate.scores.vector_score : 'n/a'}</div>
                      <div>BM25：{candidate.scores && candidate.scores.bm25_score != null ? candidate.scores.bm25_score : 'n/a'}</div>
                    </div>
                  </div>
                  <div className="mt-3 rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700">
                    {truncateKnowledgePreview(candidate.text_preview)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
            这里仅展示 retrieval-only v1 结果：query、kb_id、scope、candidates、diagnostics。
          </div>
        )}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.KnowledgeRetrievalDebugPanel = KnowledgeRetrievalDebugPanel;
