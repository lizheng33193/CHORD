const { UploadCloud, RefreshCcw, PlayCircle, RotateCcw, ShieldCheck } = window.LucideReact || {};

function formatKnowledgeDate(value) {
  if (!value) return '暂无';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatKnowledgeDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '暂无';
  const totalSeconds = Math.max(0, Number(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  if (minutes <= 0) return `${remainingSeconds}s`;
  return `${minutes}m ${remainingSeconds}s`;
}

function KnowledgeVersionJobsPanel({
  selectedDocument = null,
  versions = [],
  selectedVersionId = '',
  versionDetail = null,
  jobs = [],
  uploadDraft,
  onUploadDraftChange,
  onUpload,
  onSelectVersion,
  onIndex,
  onRebuild,
  onActivate,
  onRetryJob,
  onCancelJob,
  onRefresh,
  loading = false,
  submitting = false,
  actionMessage = '',
  errorMessage = '',
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              {UploadCloud ? <UploadCloud className="h-5 w-5 text-sky-600" /> : null}
              <h3 className="text-base font-semibold text-slate-900">Versions</h3>
            </div>
            <button
              type="button"
              onClick={() => onRefresh && onRefresh()}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              {RefreshCcw ? <RefreshCcw className="h-4 w-4" /> : null}
              刷新
            </button>
          </div>
          {selectedDocument ? (
            <div className="mb-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
              <div className="font-semibold text-slate-900">{selectedDocument.title}</div>
              <div className="mt-1">{selectedDocument.document_id}</div>
            </div>
          ) : (
            <div className="mb-4 rounded-2xl border border-dashed border-slate-300 px-4 py-6 text-sm text-slate-500">
              先选择一个文档，再上传版本或触发索引任务。
            </div>
          )}
          {actionMessage ? (
            <div className="mb-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {actionMessage}
            </div>
          ) : null}
          {errorMessage ? (
            <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {errorMessage}
            </div>
          ) : null}
          <div className="space-y-3">
            {(versions || []).map((version) => {
              const isActive = selectedVersionId === version.version_id;
              return (
                <button
                  key={version.version_id}
                  type="button"
                  onClick={() => onSelectVersion && onSelectVersion(version.version_id)}
                  className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                    isActive
                      ? 'border-sky-500 bg-sky-50 shadow-sm'
                      : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-slate-900">{version.version_label}</div>
                      <div className="mt-1 text-xs text-slate-500">{version.version_id}</div>
                    </div>
                    <span className="rounded-full bg-white px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                      {version.status}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
                    <div>Last Job：{version.last_job_id || '暂无'}</div>
                    <div>Active Manifest：{version.active_manifest_index_id || '暂无'}</div>
                  </div>
                </button>
              );
            })}
            {!loading && selectedDocument && !(versions || []).length ? (
              <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
                当前文档还没有上传版本。
              </div>
            ) : null}
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            {UploadCloud ? <UploadCloud className="h-5 w-5 text-sky-600" /> : null}
            <h3 className="text-base font-semibold text-slate-900">Upload Version</h3>
          </div>
          <div className="space-y-4">
            <label className="block">
              <div className="mb-1 text-sm font-medium text-slate-700">File</div>
              <input
                type="file"
                accept=".pdf,.docx,.md,.txt"
                onChange={(event) => onUploadDraftChange && onUploadDraftChange({ ...uploadDraft, file: event.target.files && event.target.files[0] ? event.target.files[0] : null })}
                className="block w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                disabled={!selectedDocument}
              />
            </label>
            <label className="block">
              <div className="mb-1 text-sm font-medium text-slate-700">Version Label</div>
              <input
                type="text"
                value={uploadDraft.version_label}
                onChange={(event) => onUploadDraftChange && onUploadDraftChange({ ...uploadDraft, version_label: event.target.value })}
                className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                placeholder="v2026-07-01"
                disabled={!selectedDocument}
              />
            </label>
            <label className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={Boolean(uploadDraft.auto_index)}
                onChange={(event) => onUploadDraftChange && onUploadDraftChange({ ...uploadDraft, auto_index: event.target.checked })}
                disabled={!selectedDocument}
              />
              上传完成后自动触发 index
            </label>
            <label className="block">
              <div className="mb-1 text-sm font-medium text-slate-700">Metadata JSON</div>
              <textarea
                value={uploadDraft.metadataText}
                onChange={(event) => onUploadDraftChange && onUploadDraftChange({ ...uploadDraft, metadataText: event.target.value })}
                rows={4}
                className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                placeholder='{"source":"manual"}'
                disabled={!selectedDocument}
              />
            </label>
            <div className="text-xs text-slate-500">
              支持 pdf / docx / md / txt。metadata 仅做轻量 JSON 校验，最终以后端契约为准。
            </div>
            <button
              type="button"
              onClick={() => onUpload && onUpload()}
              disabled={!selectedDocument || submitting}
              className="inline-flex items-center justify-center rounded-2xl bg-sky-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {submitting ? '上传中...' : '上传新版本'}
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            {PlayCircle ? <PlayCircle className="h-5 w-5 text-violet-600" /> : null}
            <h3 className="text-base font-semibold text-slate-900">Version Actions</h3>
          </div>
          {versionDetail ? (
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
                <div className="font-semibold text-slate-900">{versionDetail.version_label}</div>
                <div className="mt-1">状态：{versionDetail.status}</div>
                <div className="mt-1">Last Job：{versionDetail.last_job_id || '暂无'}</div>
                <div className="mt-1">Latest Manifest：{versionDetail.latest_manifest_index_id || '暂无'}</div>
                <div className="mt-1">Active Manifest：{versionDetail.active_manifest_index_id || '暂无'}</div>
              </div>
              <div className="flex flex-wrap gap-3">
                <button type="button" onClick={() => onIndex && onIndex()} className="inline-flex items-center gap-2 rounded-2xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white hover:bg-violet-700">
                  {PlayCircle ? <PlayCircle className="h-4 w-4" /> : null}
                  Index
                </button>
                <button type="button" onClick={() => onRebuild && onRebuild()} className="inline-flex items-center gap-2 rounded-2xl border border-violet-200 bg-violet-50 px-4 py-3 text-sm font-semibold text-violet-700 hover:bg-violet-100">
                  {RotateCcw ? <RotateCcw className="h-4 w-4" /> : null}
                  Rebuild
                </button>
                <button type="button" onClick={() => onActivate && onActivate()} className="inline-flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700 hover:bg-emerald-100">
                  {ShieldCheck ? <ShieldCheck className="h-4 w-4" /> : null}
                  Activate Latest Manifest
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
              先从左侧选择一个版本，再执行 index / rebuild / activate。
            </div>
          )}
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            {RotateCcw ? <RotateCcw className="h-5 w-5 text-rose-600" /> : null}
            <h3 className="text-base font-semibold text-slate-900">Indexing Jobs</h3>
          </div>
          <div className="space-y-3">
            {(jobs || []).map((job) => (
              <div key={job.job_id} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-900">{job.job_id}</div>
                    <div className="mt-1 text-xs text-slate-500">{job.trigger} / {job.current_step}</div>
                  </div>
                  <span className="rounded-full bg-white px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                    {job.status}
                  </span>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
                  <div>Attempt：{job.attempt} / {job.max_attempts}</div>
                  <div>Runtime：{job.runtime_status || 'durable-only'}</div>
                  <div>Started：{formatKnowledgeDate(job.started_at)}</div>
                  <div>Completed：{formatKnowledgeDate(job.completed_at)}</div>
                  <div>Heartbeat：{formatKnowledgeDate(job.last_heartbeat_at)}</div>
                  <div>Lease Expires：{formatKnowledgeDate(job.lease_expires_at)}</div>
                  <div>Cancel Requested：{formatKnowledgeDate(job.cancel_requested_at)}</div>
                  <div>Stale Detected：{formatKnowledgeDate(job.stale_detected_at)}</div>
                  <div>Elapsed：{formatKnowledgeDuration(job.elapsed_seconds)}</div>
                </div>
                {job.stale_reason ? (
                  <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                    Stale Reason：{job.stale_reason}
                  </div>
                ) : null}
                {(job.progress_completed_steps !== null && job.progress_completed_steps !== undefined) || job.embedding_batches_completed ? (
                  <div className="mt-3 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
                    <div>
                      Stage Progress：{job.progress_completed_steps ?? '-'} / {job.progress_total_steps ?? '-'}
                    </div>
                    <div>
                      Embedding Batches：{job.embedding_batches_completed ?? '-'} / {job.embedding_batch_count ?? '-'}
                    </div>
                  </div>
                ) : null}
                {job.progress_message ? <div className="mt-3 rounded-xl bg-white px-3 py-2 text-xs text-slate-500">{job.progress_message}</div> : null}
                {job.error_message ? (
                  <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                    Guard Failure：{job.error_message}
                  </div>
                ) : null}
                {(job.chunk_count || job.embedding_count || job.vector_mapping_count || job.page_count) ? (
                  <div className="mt-3 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
                    <div>Pages：{job.page_count || '暂无'}</div>
                    <div>Chunks：{job.chunk_count || '暂无'}</div>
                    <div>Embeddings：{job.embedding_count || '暂无'}</div>
                    <div>Vector Mappings：{job.vector_mapping_count || '暂无'}</div>
                  </div>
                ) : null}
                {job.status === 'failed' ? (
                  <div className="mt-3 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={() => onRetryJob && onRetryJob(job.job_id)}
                      className="inline-flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100"
                    >
                      {RotateCcw ? <RotateCcw className="h-4 w-4" /> : null}
                      Retry Failed Job
                    </button>
                    {(job.status === 'queued' || job.status === 'running') ? (
                      <button
                        type="button"
                        onClick={() => onCancelJob && onCancelJob(job.job_id)}
                        className="inline-flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-100"
                      >
                        Cancel Job
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {(job.status === 'queued' || job.status === 'running') && job.status !== 'failed' ? (
                  <div className="mt-3 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={() => onCancelJob && onCancelJob(job.job_id)}
                      className="inline-flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-100"
                    >
                      Cancel Job
                    </button>
                  </div>
                ) : null}
              </div>
            ))}
            {!loading && !(jobs || []).length ? (
              <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
                当前版本还没有可展示的 indexing job。
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.KnowledgeVersionJobsPanel = KnowledgeVersionJobsPanel;
