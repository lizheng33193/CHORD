function DataAgentRunForm({
  draft,
  currentCountry = 'mx',
  loading = false,
  error = '',
  onChange,
  onSubmit,
  canCreate = true,
}) {
  const resolvedCountry = (draft && draft.target_country) || currentCountry || 'mx';
  const runType = (draft && draft.run_type) || 'cohort_query';

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">新建 Data Agent SQL 审核任务</h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">显式创建 SQL review run，不影响当前 NL Chat 会话与 orchestrator 路由。</p>
        </div>
        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-semibold text-blue-700">M1 SQL HITL</span>
      </div>
      <div className="mt-4 grid gap-3">
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
          自然语言取数需求
          <textarea
            value={(draft && draft.natural_language_request) || ''}
            onChange={(e) => onChange({ ...draft, natural_language_request: e.target.value })}
            rows={3}
            disabled={loading || !canCreate}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none transition-colors focus:border-blue-400 disabled:bg-slate-50"
            placeholder="例如：查询最近 7 天高风险用户"
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            国家
            <select
              value={resolvedCountry}
              onChange={(e) => onChange({ ...draft, target_country: e.target.value })}
              disabled={loading || !canCreate}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none transition-colors focus:border-blue-400 disabled:bg-slate-50"
            >
              <option value="mx">墨西哥 (MX)</option>
              <option value="th">泰国 (TH)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            Run Type
            <select
              value={runType}
              onChange={(e) => onChange({ ...draft, run_type: e.target.value })}
              disabled={loading || !canCreate}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none transition-colors focus:border-blue-400 disabled:bg-slate-50"
            >
              <option value="cohort_query">cohort_query</option>
              <option value="bucket_writeback">bucket_writeback</option>
            </select>
          </label>
        </div>
        {runType === 'bucket_writeback' ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
              Output Bucket
              <select
                value={(draft && draft.output_bucket) || 'behavior'}
                onChange={(e) => onChange({ ...draft, output_bucket: e.target.value })}
                disabled={loading || !canCreate}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none transition-colors focus:border-blue-400 disabled:bg-slate-50"
              >
                <option value="app">app</option>
                <option value="behavior">behavior</option>
                <option value="credit">credit</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
              Output Format
              <select
                value={(draft && draft.output_format) || 'json'}
                onChange={(e) => onChange({ ...draft, output_format: e.target.value })}
                disabled={loading || !canCreate}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none transition-colors focus:border-blue-400 disabled:bg-slate-50"
              >
                <option value="json">json</option>
                <option value="csv">csv</option>
              </select>
            </label>
          </div>
        ) : null}
        {error ? <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div> : null}
        {!canCreate ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            当前身份缺少 `data:query:generate` 或 `data:query:view_sql`，无法创建 Data Agent run。
          </div>
        ) : null}
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => onSubmit && onSubmit()}
            disabled={loading || !canCreate || !((draft && draft.natural_language_request || '').trim())}
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? '生成中...' : '生成 SQL 草稿'}
          </button>
        </div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.DataAgentRunForm = DataAgentRunForm;
