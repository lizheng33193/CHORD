const { FileText, FolderTree } = window.LucideReact || {};

function KnowledgeDocumentPanel({
  selectedKb = null,
  documents = [],
  selectedDocumentId = '',
  draft,
  onDraftChange,
  onCreate,
  onSelectDocument,
  loading = false,
  creating = false,
  errorMessage = '',
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)]">
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            {FolderTree ? <FolderTree className="h-5 w-5 text-indigo-600" /> : null}
            <h3 className="text-base font-semibold text-slate-900">Documents</h3>
          </div>
          {selectedKb ? (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {selectedKb.kb_id}
            </span>
          ) : null}
        </div>
        {selectedKb ? (
          <div className="mb-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
            <div className="font-semibold text-slate-900">{selectedKb.name}</div>
            <div className="mt-1">状态：{selectedKb.status}</div>
            {selectedKb.description ? <div className="mt-2">{selectedKb.description}</div> : null}
          </div>
        ) : (
          <div className="mb-4 rounded-2xl border border-dashed border-slate-300 px-4 py-6 text-sm text-slate-500">
            先从左侧选择一个知识库，再管理文档。
          </div>
        )}
        {errorMessage ? (
          <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorMessage}
          </div>
        ) : null}
        <div className="space-y-3">
          {(documents || []).map((item) => {
            const isActive = selectedDocumentId === item.document_id;
            return (
              <button
                key={item.document_id}
                type="button"
                onClick={() => onSelectDocument && onSelectDocument(item.document_id)}
                className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                  isActive
                    ? 'border-indigo-500 bg-indigo-50 shadow-sm'
                    : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">{item.title}</div>
                    <div className="mt-1 text-xs text-slate-500">{item.document_id}</div>
                  </div>
                  <span className="rounded-full bg-white px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                    {item.status}
                  </span>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
                  <div>版本数：{item.version_count}</div>
                  <div>Active 版本：{item.active_version_id || '暂无'}</div>
                </div>
              </button>
            );
          })}
          {!loading && selectedKb && !(documents || []).length ? (
            <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
              当前知识库还没有文档，先创建一个 metadata 记录。
            </div>
          ) : null}
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          {FileText ? <FileText className="h-5 w-5 text-amber-600" /> : null}
          <h3 className="text-base font-semibold text-slate-900">Create Document</h3>
        </div>
        <div className="space-y-4">
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">Title</div>
            <input
              type="text"
              value={draft.title}
              onChange={(event) => onDraftChange && onDraftChange({ ...draft, title: event.target.value })}
              className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
              placeholder="贷前风控知识库"
              disabled={!selectedKb}
            />
          </label>
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">Source Type</div>
            <input
              type="text"
              value={draft.source_type}
              onChange={(event) => onDraftChange && onDraftChange({ ...draft, source_type: event.target.value })}
              className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
              disabled={!selectedKb}
            />
          </label>
          <label className="block">
            <div className="mb-1 text-sm font-medium text-slate-700">Source URI</div>
            <input
              type="text"
              value={draft.source_uri}
              onChange={(event) => onDraftChange && onDraftChange({ ...draft, source_uri: event.target.value })}
              className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
              placeholder="optional://source"
              disabled={!selectedKb}
            />
          </label>
          <button
            type="button"
            onClick={() => onCreate && onCreate()}
            disabled={!selectedKb || creating}
            className="inline-flex items-center justify-center rounded-2xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {creating ? '创建中...' : '创建文档'}
          </button>
        </div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.KnowledgeDocumentPanel = KnowledgeDocumentPanel;
