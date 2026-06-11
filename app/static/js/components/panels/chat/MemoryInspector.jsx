const {
  archiveMemory,
  createMemory,
  deleteMemory,
  fetchOrchestratorSessions,
  fetchMemoryStatus,
  listMemories,
  queryMemory,
  restoreMemory,
  updateMemory,
} = window.AppServices.api;
const { useCallback, useEffect, useMemo, useState } = React;
const {
  Archive,
  Database,
  Edit3,
  History,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} = window.LucideReact || {};
const { createPortal } = ReactDOM;

const CATEGORY_OPTIONS = ['preference', 'feedback', 'project', 'reference', 'task', 'insight'];
const STATUS_OPTIONS = ['active', 'archived', 'deleted', 'all'];

function MemoryInspector({ open, onClose, onOpenSession, onRestoreSession }) {
  const [status, setStatus] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [sessionQuery, setSessionQuery] = useState('');
  const [sessionStatusFilter, setSessionStatusFilter] = useState('all');
  const [sessionCountryFilter, setSessionCountryFilter] = useState('mx');
  const [sessionLimit, setSessionLimit] = useState(20);
  const [results, setResults] = useState([]);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [topK, setTopK] = useState(8);
  const [userId, setUserId] = useState('local-default-user');
  const [projectId, setProjectId] = useState('agent-user-profile-fork');
  const [country, setCountry] = useState('mx');
  const [draft, setDraft] = useState(_emptyDraft());
  const [editingId, setEditingId] = useState('');
  const [editDraft, setEditDraft] = useState(_emptyDraft());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const identity = useMemo(() => ({
    user_id: userId.trim() || undefined,
    project_id: projectId.trim() || undefined,
    country: country.trim() || undefined,
  }), [country, projectId, userId]);

  const loadStatus = useCallback(async () => {
    const body = await fetchMemoryStatus();
    setStatus(body);
  }, []);

  const loadSessions = useCallback(async () => {
    const payload = await fetchOrchestratorSessions({
      user_id: identity.user_id,
      project_id: identity.project_id,
      country: sessionCountryFilter || undefined,
      limit: Number(sessionLimit) || 20,
    });
    setSessions(Array.isArray(payload.sessions) ? payload.sessions : []);
  }, [identity, sessionCountryFilter, sessionLimit]);

  const loadList = useCallback(async (overrides = {}) => {
    const nextQuery = Object.prototype.hasOwnProperty.call(overrides, 'query') ? overrides.query : query;
    const nextCategory = Object.prototype.hasOwnProperty.call(overrides, 'category') ? overrides.category : category;
    const nextStatus = Object.prototype.hasOwnProperty.call(overrides, 'status') ? overrides.status : statusFilter;
    setLoading(true);
    setError('');
    try {
      const payload = nextQuery.trim()
        ? await queryMemory({
            query: nextQuery,
            ...identity,
            category: nextCategory || undefined,
            top_k: Number(topK) || 8,
          })
        : await listMemories({
            ...identity,
            category: nextCategory || undefined,
            status: nextStatus || 'active',
            limit: Number(topK) || 8,
          });
      setResults(Array.isArray(payload.results) ? payload.results : []);
      await loadStatus();
    } catch (err) {
      setError(String((err && err.message) || err));
    } finally {
      setLoading(false);
    }
  }, [category, identity, loadStatus, query, statusFilter, topK]);

  useEffect(() => {
    if (!open) return;
    loadStatus().catch((err) => setError(String((err && err.message) || err)));
    loadSessions().catch((err) => setError(String((err && err.message) || err)));
    loadList();
  }, [open]);

  const create = useCallback(async () => {
    if (!draft.content.trim()) return;
    setLoading(true);
    setError('');
    try {
      await createMemory({
        ...identity,
        content: draft.content,
        category: draft.category,
        tags: _tags(draft.tags),
        importance: Number(draft.importance),
        confidence: Number(draft.confidence),
      });
      setDraft(_emptyDraft());
      await loadList({ query: '' });
    } catch (err) {
      setError(String((err && err.message) || err));
    } finally {
      setLoading(false);
    }
  }, [draft, identity, loadList]);

  const startEdit = (item) => {
    setEditingId(item.memory_id);
    setEditDraft({
      content: item.content || '',
      category: item.category || 'reference',
      tags: Array.isArray(item.tags) ? item.tags.join(', ') : '',
      importance: item.importance ?? 0.7,
      confidence: item.confidence ?? 0.8,
    });
  };

  const saveEdit = useCallback(async (memoryId) => {
    setLoading(true);
    setError('');
    try {
      await updateMemory(memoryId, {
        ...identity,
        content: editDraft.content,
        category: editDraft.category,
        tags: _tags(editDraft.tags),
        importance: Number(editDraft.importance),
        confidence: Number(editDraft.confidence),
      });
      setEditingId('');
      await loadList();
    } catch (err) {
      setError(String((err && err.message) || err));
    } finally {
      setLoading(false);
    }
  }, [editDraft, identity, loadList]);

  const setRowStatus = useCallback(async (item, action) => {
    setLoading(true);
    setError('');
    try {
      if (action === 'archive') await archiveMemory(item.memory_id, identity);
      if (action === 'restore') await restoreMemory(item.memory_id, identity);
      if (action === 'delete') await deleteMemory(item.memory_id, identity);
      await loadList({ query: '' });
    } catch (err) {
      setError(String((err && err.message) || err));
    } finally {
      setLoading(false);
    }
  }, [identity, loadList]);

  const byCategory = status && status.by_category ? Object.entries(status.by_category) : [];
  const byStatus = status && status.by_status ? Object.entries(status.by_status) : [];
  const activeTotal = status && status.by_status && typeof status.by_status.active === 'number'
    ? status.by_status.active
    : 0;
  const filteredSessions = useMemo(() => {
    const q = sessionQuery.trim().toLowerCase();
    return sessions.filter((item) => {
      if (sessionStatusFilter !== 'all' && item.status !== sessionStatusFilter) return false;
      if (q) {
        const haystack = [
          item.session_id,
          item.last_user_message_preview,
          item.final_message_preview,
        ].map((v) => String(v || '').toLowerCase()).join(' ');
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [sessionQuery, sessionStatusFilter, sessions]);

  useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && onClose) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div className="fixed inset-0 z-[80]">
      <div className="absolute inset-0 bg-slate-950/35 backdrop-blur-[2px]" onClick={onClose}></div>
      <div className="absolute inset-y-3 right-3 w-[min(94vw,920px)] overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-[0_32px_80px_rgba(15,23,42,0.22)]">
        <div className="flex h-full flex-col" onClick={(event) => event.stopPropagation()}>
          <div className="flex items-center justify-between gap-4 border-b border-slate-200 px-5 py-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                {Database ? <Database className="h-4 w-4 shrink-0 text-slate-500" /> : null}
                <span className="font-semibold text-slate-800">历史记忆</span>
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">{activeTotal}</span>
              </div>
              <p className="mt-1 text-sm text-slate-500">短期会话历史与长期记忆统一放在抽屉中查看与管理。</p>
            </div>
            <button type="button" onClick={onClose} className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 text-slate-500 hover:bg-slate-100">
              {X ? <X className="h-4 w-4" /> : null}
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-5">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {History ? <History className="h-4 w-4 text-slate-500" /> : null}
                <h3 className="text-sm font-semibold text-slate-800">短期会话历史</h3>
                <Badge>{filteredSessions.length}/{sessions.length}</Badge>
              </div>
              <button type="button" onClick={() => loadSessions()} disabled={loading} className="text-sm font-semibold text-slate-600 hover:text-slate-900">
                刷新
              </button>
            </div>
            <p className="mt-1 text-sm leading-6 text-slate-500">
              短期会话历史来自 outputs/orchestrator_sessions，只用于恢复聊天上下文，不参与长期记忆召回。
            </p>
            <div className="mt-3 grid gap-2 md:grid-cols-[1fr_0.36fr_0.32fr_0.28fr]">
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-slate-500">搜索会话</span>
                <input
                  value={sessionQuery}
                  onChange={(e) => setSessionQuery(e.target.value)}
                    className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-400"
                    placeholder="session id / 最近问题 / 最终回复"
                />
              </label>
              <SelectField label="会话状态" value={sessionStatusFilter} onChange={setSessionStatusFilter} options={['all', 'completed', 'error', 'budget_exceeded']} />
              <SelectField label="会话国家" value={sessionCountryFilter} onChange={setSessionCountryFilter} options={['', 'mx', 'th']} emptyLabel="全部国家" />
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-slate-500">会话 Limit</span>
                <input
                  type="number"
                  min="1"
                  max="50"
                  value={sessionLimit}
                  onChange={(e) => setSessionLimit(e.target.value)}
                  className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-400"
                />
              </label>
            </div>
            <div className="mt-3 space-y-2">
              {filteredSessions.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-3 text-sm text-slate-500">暂无可恢复会话。</div>
              ) : filteredSessions.map((item) => (
                <div
                  key={item.session_id}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2"
                >
                  <button
                    type="button"
                    onClick={() => onOpenSession && onOpenSession(item.session_id)}
                    className="block w-full text-left hover:bg-slate-50"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                      <span className="font-mono font-semibold text-slate-700">{item.session_id}</span>
                      <span className="text-slate-400">{item.updated_at}</span>
                    </div>
                    <div className="mt-1 truncate text-sm text-slate-600">{item.last_user_message_preview || '暂无用户消息'}</div>
                    {item.final_message_preview ? <div className="mt-1 truncate text-sm text-slate-400">{item.final_message_preview}</div> : null}
                  </button>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => onOpenSession && onOpenSession(item.session_id)}
                      className="inline-flex items-center rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                    >
                      查看历史会话
                    </button>
                    <button
                      type="button"
                      onClick={() => onRestoreSession && onRestoreSession(item.session_id)}
                      className="inline-flex items-center rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-100"
                    >
                      恢复该次分析结果
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-slate-200 p-3">
            <div className="flex items-center gap-2">
              {Database ? <Database className="h-4 w-4 text-slate-500" /> : null}
              <h3 className="text-sm font-semibold text-slate-800">长期记忆</h3>
              <Badge tone="blue">active: {activeTotal}</Badge>
            </div>
            <p className="mt-1 text-sm leading-6 text-slate-500">
              active 会被召回；archived 不参与召回但可恢复；deleted 是软删除，不参与召回但仍可列表查看和恢复。删除操作会“移入已删除”，不会永久清空。
            </p>
            <div className="mt-3 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm leading-6 text-blue-800">
              <span className="font-semibold">为什么会被召回：</span>
              当前 identity 下的 active 记忆，若与本轮问题、Query、Category、Country 或 tags 命中，就可能进入 Agent 上下文；archived / deleted 不参与召回，但可查看和恢复。
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-[1.2fr_0.75fr_0.55fr_0.45fr]">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-slate-500">Query</span>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') loadList();
                }}
                className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-blue-400"
                placeholder="空查询返回列表"
              />
            </label>
            <SelectField label="Category" value={category} onChange={setCategory} options={['', ...CATEGORY_OPTIONS]} emptyLabel="全部" />
            <SelectField label="Status" value={statusFilter} onChange={setStatusFilter} options={STATUS_OPTIONS} />
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-slate-500">Limit</span>
              <input
                type="number"
                min="1"
                max="50"
                value={topK}
                onChange={(e) => setTopK(e.target.value)}
                className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-blue-400"
              />
            </label>
          </div>

          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <input value={userId} onChange={(e) => setUserId(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-blue-400" aria-label="user id" />
            <input value={projectId} onChange={(e) => setProjectId(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-blue-400" aria-label="project id" />
            <input value={country} onChange={(e) => setCountry(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-blue-400" aria-label="country" />
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => loadList()} disabled={loading} className="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-900 px-3 text-sm font-semibold text-white disabled:opacity-60">
              {loading && RefreshCw ? <RefreshCw className="h-4 w-4 animate-spin" /> : Search ? <Search className="h-4 w-4" /> : null}
              查询
            </button>
            <button type="button" onClick={() => { setQuery(''); loadList({ query: '' }); }} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700">
              {SlidersHorizontal ? <SlidersHorizontal className="h-4 w-4" /> : null}
              列表
            </button>
            {byCategory.map(([key, value]) => <Badge key={key} tone="blue">{key}: {value}</Badge>)}
            {byStatus.map(([key, value]) => <Badge key={key}>{_statusLabel(key)}: {value}</Badge>)}
          </div>

          <div className="mt-4 rounded-lg border border-slate-200 p-3">
            <div className="grid gap-3 md:grid-cols-[1fr_0.32fr]">
              <textarea
                value={draft.content}
                onChange={(e) => setDraft({ ...draft, content: e.target.value })}
                className="min-h-[74px] rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                placeholder="新增记忆内容"
              />
              <div className="grid gap-2">
                <SelectField value={draft.category} onChange={(v) => setDraft({ ...draft, category: v })} options={CATEGORY_OPTIONS} />
                <input value={draft.tags} onChange={(e) => setDraft({ ...draft, tags: e.target.value })} className="h-9 rounded-lg border border-slate-200 px-3 text-xs outline-none focus:border-blue-400" placeholder="tags" />
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <NumberField label="importance" value={draft.importance} onChange={(v) => setDraft({ ...draft, importance: v })} />
              <NumberField label="confidence" value={draft.confidence} onChange={(v) => setDraft({ ...draft, confidence: v })} />
              <button type="button" onClick={create} disabled={loading || !draft.content.trim()} className="inline-flex h-9 items-center gap-2 rounded-lg bg-blue-600 px-3 text-sm font-semibold text-white disabled:opacity-60">
                {Plus ? <Plus className="h-4 w-4" /> : null}
                新增
              </button>
            </div>
          </div>

          {status && status.db_path ? <div className="mt-3 truncate text-sm text-slate-500">{status.db_path}</div> : null}
          {error ? <div className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div> : null}

          <div className="mt-4 space-y-2">
            {results.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">暂无结果</div>
            ) : results.map((item) => (
              <article key={item.memory_id} className="rounded-lg border border-slate-200 px-3 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-semibold text-slate-700">{item.category}</span>
                    <span className="text-slate-500">{item.status}</span>
                    {item.score !== undefined ? <span className="text-slate-500">score {item.score}</span> : null}
                    <span className="text-slate-500">importance {item.importance}</span>
                    <span className="text-slate-500">confidence {item.confidence}</span>
                    <span className="text-slate-400">{item.source}</span>
                    <span className="text-slate-400">{item.created_at}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <IconButton title="编辑" onClick={() => startEdit(item)} icon={Edit3} />
                    {item.status === 'active' ? <IconButton title="归档" onClick={() => setRowStatus(item, 'archive')} icon={Archive} /> : null}
                    {item.status !== 'active' && item.status !== 'deleted' ? <IconButton title="恢复" onClick={() => setRowStatus(item, 'restore')} icon={RotateCcw} /> : null}
                    {item.status !== 'deleted' ? <IconButton title="移入已删除" onClick={() => setRowStatus(item, 'delete')} icon={Trash2} /> : null}
                  </div>
                </div>
                {editingId === item.memory_id ? (
                  <EditForm draft={editDraft} setDraft={setEditDraft} onSave={() => saveEdit(item.memory_id)} onCancel={() => setEditingId('')} loading={loading} />
                ) : (
                  <>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-800">{item.content}</p>
                    <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-500">{_recallExplanation(item)}</p>
                  </>
                )}
              </article>
            ))}
          </div>
        </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

function SelectField({ label, value, onChange, options, emptyLabel }) {
  return (
    <label className="block">
      {label ? <span className="mb-1 block text-sm font-semibold text-slate-500">{label}</span> : null}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-blue-400">
        {options.map((option) => <option key={option || 'empty'} value={option}>{option || emptyLabel || option}</option>)}
      </select>
    </label>
  );
}

function NumberField({ label, value, onChange }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500">
      {label}
      <input type="number" min="0" max="1" step="0.05" value={value} onChange={(e) => onChange(e.target.value)} className="h-9 w-20 rounded-lg border border-slate-200 px-2 text-sm outline-none focus:border-blue-400" />
    </label>
  );
}

function EditForm({ draft, setDraft, onSave, onCancel, loading }) {
  return (
    <div className="mt-3 rounded-lg bg-slate-50 p-3">
      <textarea value={draft.content} onChange={(e) => setDraft({ ...draft, content: e.target.value })} className="min-h-[86px] w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
      <div className="mt-2 grid gap-2 md:grid-cols-[0.7fr_1fr_0.4fr_0.4fr_auto]">
        <SelectField value={draft.category} onChange={(v) => setDraft({ ...draft, category: v })} options={CATEGORY_OPTIONS} />
        <input value={draft.tags} onChange={(e) => setDraft({ ...draft, tags: e.target.value })} className="h-10 rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-blue-400" placeholder="tags" />
        <NumberField label="importance" value={draft.importance} onChange={(v) => setDraft({ ...draft, importance: v })} />
        <NumberField label="confidence" value={draft.confidence} onChange={(v) => setDraft({ ...draft, confidence: v })} />
        <div className="flex items-center gap-1">
          <IconButton title="保存" onClick={onSave} icon={Save} disabled={loading} />
          <IconButton title="取消" onClick={onCancel} icon={X} />
        </div>
      </div>
    </div>
  );
}

function IconButton({ title, onClick, icon: Icon, disabled }) {
  return (
    <button type="button" title={title} aria-label={title} onClick={onClick} disabled={disabled} className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50">
      {Icon ? <Icon className="h-4 w-4" /> : title.slice(0, 1)}
    </button>
  );
}

function Badge({ children, tone }) {
  const cls = tone === 'blue'
    ? 'rounded bg-blue-50 px-2 py-1 text-sm font-semibold text-blue-700'
    : 'rounded bg-slate-100 px-2 py-1 text-sm font-semibold text-slate-600';
  return <span className={cls}>{children}</span>;
}

function _statusLabel(status) {
  return {
    active: 'active 会被召回',
    archived: 'archived 不参与召回',
    deleted: 'deleted 已删除不召回',
    superseded: 'superseded 已替换',
  }[status] || status;
}

function _recallExplanation(item) {
  const status = item && item.status;
  if (status === 'active') {
    return '会被召回：active + 当前 identity + 查询相关。若本轮问题、Query、Category、Country 或 tags 命中，这条长期记忆可能进入 Agent 上下文。';
  }
  if (status === 'archived') {
    return '不参与召回：archived 已归档，仍可查看并恢复为 active。';
  }
  if (status === 'deleted') {
    return '不参与召回：deleted 已删除不召回，但这是软删除，仍可查看并恢复。';
  }
  return '不参与召回：仅 active 长期记忆会进入后续 Agent 上下文。';
}

function _emptyDraft() {
  return { content: '', category: 'preference', tags: '', importance: 0.75, confidence: 0.8 };
}

function _tags(value) {
  return String(value || '').split(',').map((item) => item.trim()).filter(Boolean);
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.MemoryInspector = MemoryInspector;
