function StatusBadge({ label, tone = 'slate' }) {
  const tones = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    emerald: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    rose: 'bg-rose-50 text-rose-700 border-rose-200',
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
  };
  return <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${tones[tone] || tones.slate}`}>{label}</span>;
}

function safetyTone(status) {
  if (status === 'passed') return 'emerald';
  if (status === 'review_only') return 'amber';
  if (status === 'blocked') return 'rose';
  return 'slate';
}

function SQLReviewCard({
  run,
  loading = false,
  canViewSql = false,
  canReview = false,
  canReviewSql = false,
  canRevise = false,
  canExecute = false,
  canWriteback = false,
  onApprove,
  onReject,
  onEdit,
  onRevise,
  onExecute,
}) {
  if (!run) return null;
  const currentSql = run.current_sql || null;
  const safety = currentSql && currentSql.safety_result ? currentSql.safety_result : {};
  const blockedReasons = Array.isArray(safety.blocked_reasons) ? safety.blocked_reasons : [];
  const warnings = Array.isArray(safety.warnings) ? safety.warnings : [];
  const isWriteback = run.run_type === 'bucket_writeback';
  const canExecuteThisRun = run.sql_kind === 'query_only' && run.status === 'approved' && canExecute && (!isWriteback || canWriteback);
  const missingWritebackPermission = isWriteback && canExecute && !canWriteback;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-800">{run.natural_language_request}</h3>
            <StatusBadge label={run.status} tone={run.status === 'approved' || run.status === 'executed' ? 'emerald' : (run.status === 'rejected' ? 'rose' : 'slate')} />
            {run.sql_kind ? <StatusBadge label={run.sql_kind} tone={run.sql_kind === 'query_only' ? 'blue' : 'amber'} /> : null}
            <StatusBadge label={run.run_type} tone={isWriteback ? 'amber' : 'blue'} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span>Run ID: <span className="font-mono text-slate-700">{run.run_id}</span></span>
            <span>Country: {(run.target_country || 'mx').toUpperCase()}</span>
            {currentSql ? <span>SQL Hash: <span className="font-mono text-slate-700">{currentSql.sql_hash}</span></span> : null}
          </div>
        </div>
        {currentSql ? <StatusBadge label={`Safety: ${currentSql.safety_status}`} tone={safetyTone(currentSql.safety_status)} /> : null}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
        <div className="space-y-3">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">SQL Preview</div>
            {canViewSql && currentSql && currentSql.sql_text ? (
              <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-white p-3 text-xs leading-5 text-slate-700">{currentSql.sql_text}</pre>
            ) : (
              <div className="mt-2 rounded-lg bg-white p-3 text-xs leading-5 text-slate-500">
                {currentSql ? 'SQL 已生成，但当前身份没有查看 SQL 明文的权限。' : '当前 run 还没有 SQL 版本。'}
              </div>
            )}
          </div>
          {blockedReasons.length > 0 ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-rose-700">Blocked Reasons</div>
              <ul className="mt-2 space-y-1 text-xs text-rose-700">
                {blockedReasons.map((reason, idx) => <li key={`${run.run_id}-blocked-${idx}`}>{reason}</li>)}
              </ul>
            </div>
          ) : null}
          {warnings.length > 0 ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-amber-700">Warnings</div>
              <ul className="mt-2 space-y-1 text-xs text-amber-700">
                {warnings.map((warning, idx) => <li key={`${run.run_id}-warning-${idx}`}>{warning}</li>)}
              </ul>
            </div>
          ) : null}
        </div>

        <div className="space-y-3">
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">执行摘要</div>
            {run.execution ? (
              <div className="mt-2 space-y-1 text-xs text-slate-700">
                <div>status: {run.execution.status}</div>
                <div>rows_estimated: {run.execution.rows_estimated ?? '-'}</div>
                <div>rows_actual: {run.execution.rows_actual ?? '-'}</div>
                <div>uids: {Array.isArray(run.execution.uids) ? run.execution.uids.length : 0}</div>
              </div>
            ) : (
              <div className="mt-2 text-xs text-slate-500">尚未执行。</div>
            )}
          </div>

          {run.writeback ? (
            <div className="rounded-xl border border-slate-200 p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Writeback</div>
              <div className="mt-2 space-y-1 text-xs text-slate-700">
                <div>bucket: {run.writeback.output_bucket}</div>
                <div>format: {run.writeback.output_format}</div>
                <div>written_uid_count: {run.writeback.written_uid_count ?? '-'}</div>
                <div>target_dir: {run.writeback.target_dir || '-'}</div>
              </div>
            </div>
          ) : null}

          <div className="rounded-xl border border-slate-200 p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Review Actions</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {canReviewSql ? (
                <>
                  <button type="button" disabled={loading} onClick={() => onEdit && onEdit(run)} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-100 disabled:opacity-50">Edit SQL</button>
                  <button type="button" disabled={loading || run.sql_kind !== 'query_only' || !currentSql || currentSql.safety_status !== 'passed'} onClick={() => onApprove && onApprove(run)} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-50">Approve</button>
                </>
              ) : null}
              {canRevise ? (
                <button type="button" disabled={loading} onClick={() => onRevise && onRevise(run)} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-100 disabled:opacity-50">Ask Agent Revise</button>
              ) : null}
              {canReview ? (
                <button type="button" disabled={loading} onClick={() => onReject && onReject(run)} className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-rose-500 disabled:opacity-50">Reject</button>
              ) : null}
              {!canReview ? (
                <div className="text-xs text-slate-500">当前身份没有 `data:query:review`，只能查看状态。</div>
              ) : null}
              {canReview && !canReviewSql ? (
                <div className="text-xs text-amber-700">当前身份可以执行拒绝操作，但缺少 `data:query:view_sql`，不能 approve 或 edit SQL。</div>
              ) : null}
            </div>
            <div className="mt-3">
              <button
                type="button"
                disabled={loading || !canExecuteThisRun}
                onClick={() => onExecute && onExecute(run)}
                className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-slate-700 disabled:opacity-50"
              >
                {isWriteback ? 'Execute & Write Back' : 'Execute Query'}
              </button>
              {missingWritebackPermission ? (
                <div className="mt-2 text-xs text-amber-700">当前身份可以执行普通查询，但缺少 `data:bucket:writeback`，不能写回画像数据目录。</div>
              ) : null}
              {run.sql_kind === 'build_table_script' ? (
                <div className="mt-2 text-xs text-amber-700">M1 当前只支持 `query_only` 执行，`build_table_script` 仅支持 review-only。</div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.SQLReviewCard = SQLReviewCard;
