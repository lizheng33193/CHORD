const { Database, PlusCircle } = window.LucideReact || {};

function KnowledgeBaseListPanel({
  items = [],
  selectedKbId = '',
  createDraft,
  onDraftChange,
  onCreate,
  onSelect,
  loading = false,
  creating = false,
  errorMessage = '',
}) {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          {Database ? <Database className="h-5 w-5 text-blue-600" /> : null}
          <h3 className="text-base font-semibold text-slate-900">Knowledge Bases</h3>
        </div>
        {errorMessage ? (
          <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorMessage}
          </div>
        ) : null}
        <div className="space-y-3">
          {(items || []).map((item) => {
            const isActive = selectedKbId === item.kb_id;
            return (
              <button
                key={item.kb_id}
                type="button"
                onClick={() => onSelect && onSelect(item.kb_id)}
                className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                  isActive
                    ? 'border-blue-500 bg-blue-50 shadow-sm'
                    : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">{item.name}</div>
                    <div className="mt-1 text-xs text-slate-500">{item.kb_id}</div>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                    {item.status}
                  </span>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
                  <div>文档数：{item.document_count}</div>
                  <div>Active 文档：{item.active_document_count}</div>
                </div>
                {item.description ? <div className="mt-3 text-sm text-slate-600">{item.description}</div> : null}
              </button>
            );
          })}
          {!loading && !(items || []).length ? (
            <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
              还没有知识库，先创建一个 Risk Knowledge Base。
            </div>
          ) : null}
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          {PlusCircle ? <PlusCircle className="h-5 w-5 text-emerald-600" /> : null}
          <h3 className="text-base font-semibold text-slate-900">Create KB</h3>
        </div>
        <div className="space-y-4">
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">KB ID</div>
            <input
              type="text"
              value={createDraft.kb_id}
              onChange={(event) => onDraftChange && onDraftChange({ ...createDraft, kb_id: event.target.value })}
              className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
              placeholder="risk_domain_knowledge"
            />
          </label>
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">Name</div>
            <input
              type="text"
              value={createDraft.name}
              onChange={(event) => onDraftChange && onDraftChange({ ...createDraft, name: event.target.value })}
              className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
              placeholder="Risk Domain Knowledge"
            />
          </label>
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">Description</div>
            <textarea
              value={createDraft.description}
              onChange={(event) => onDraftChange && onDraftChange({ ...createDraft, description: event.target.value })}
              rows={4}
              className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
              placeholder="Describe this knowledge base..."
            />
          </label>
          <button
            type="button"
            onClick={() => onCreate && onCreate()}
            disabled={creating}
            className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {creating ? '创建中...' : '创建知识库'}
          </button>
        </div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.KnowledgeBaseListPanel = KnowledgeBaseListPanel;
