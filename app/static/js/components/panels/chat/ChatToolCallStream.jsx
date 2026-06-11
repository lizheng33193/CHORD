function ChatToolCallStream({ toolCalls, now }) {
  if (!toolCalls || toolCalls.length === 0) return null;
  const tickNow = now || Date.now();
  return (
    <div className="mt-4 border-t border-dashed border-slate-200 pt-3">
      <div className="mb-2 text-xs font-semibold text-slate-500">工具调用</div>
      <div className="space-y-1.5">
        {toolCalls.map((t) => {
          const isCancelled = t.status === 'cancelled';
          const isRunning = t.status !== 'ok' && t.status !== 'error' && !isCancelled;
          const label = t.status === 'ok' ? 'DONE' : t.status === 'error' ? 'ERROR' : isCancelled ? 'CANCELLED' : 'RUN';
          const labelColor = t.status === 'ok'
            ? 'text-emerald-600'
            : t.status === 'error'
              ? 'text-rose-600'
              : isCancelled
                ? 'text-slate-500'
                : 'text-blue-600';
          // 2026-05-04 方案 A v3：每个工具显示已用时长（运行中/已完成皆有）。
          const startedAt = t.startedAtMs;
          const finishedAt = t.finishedAtMs || tickNow;
          const elapsedSec = startedAt ? Math.max(0, Math.floor((finishedAt - startedAt) / 1000)) : null;
          const elapsedLabel = elapsedSec != null ? `${Math.floor(elapsedSec/60)}:${String(elapsedSec%60).padStart(2,'0')}` : null;
          const progress = Array.isArray(t.progress) ? t.progress : [];
          const latestProgress = progress.length ? progress[progress.length - 1] : null;
          return (
            <div key={t.tool_call_id} className="space-y-1">
              <div className="flex items-center gap-2 font-mono text-xs">
                {isRunning ? (
                  <svg className="h-3.5 w-3.5 animate-spin text-blue-600" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                ) : (
                  <span className={`inline-block h-2 w-2 rounded-full ${t.status === 'ok' ? 'bg-emerald-500' : t.status === 'error' ? 'bg-rose-500' : 'bg-slate-400'}`}></span>
                )}
                <span className={`font-semibold ${labelColor}`}>{label}</span>
                <span className="text-slate-700">{t.tool_name || t.tool_call_id}</span>
                {isRunning ? <span className="text-slate-400">运行中…</span> : null}
                {isCancelled ? <span className="text-slate-400">已停止</span> : null}
                {latestProgress ? (
                  <span className="text-slate-400">
                    模块 {latestProgress.completed || progress.length}/{latestProgress.total || '?'}
                  </span>
                ) : null}
                {elapsedLabel ? <span className="text-slate-400 ml-auto">{elapsedLabel}</span> : null}
              </div>
              {progress.length > 0 ? (
                <div className="ml-5 flex flex-wrap gap-1.5">
                  {progress.map((p, idx) => (
                    <span key={`${p.uid || 'uid'}-${p.module || idx}-${idx}`} className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${p.status === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                      {p.module || 'module'} {p.status === 'ok' ? '完成' : '失败'}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatToolCallStream = ChatToolCallStream;
