// ProgressView — SSE-driven 6-row skill progress + multi-UID collapse.
// Design: docs/specs/sse-progress-design.md §5

const SKILL_ORDER = [
  { key: 'app_profile',           label: 'App 画像' },
  { key: 'behavior_profile',      label: '行为画像' },
  { key: 'credit_profile',        label: '征信画像' },
  { key: 'comprehensive_profile', label: '综合画像' },
  { key: 'product_advice',        label: '产品策略' },
  { key: 'ops_advice',            label: '运营策略' }
];

const ICON = {
  pending:   '⚪',
  running:   '⏳',
  done:      '✅',
  failed:    '⚠️'
};

function _formatDuration(ms) {
  if (ms == null) return '';
  const sec = ms / 1000;
  return `${sec.toFixed(1)}s`;
}

function SkillRow({ label, status, durationMs }) {
  const tail = status === 'done' || status === 'failed'
    ? _formatDuration(durationMs)
    : status === 'running' ? '进行中…'
    : status === 'pending' ? '等待中'
    : '';
  return (
    <div className="flex items-center justify-between py-2 px-4 border-b border-slate-700/40 last:border-b-0">
      <div className="flex items-center gap-3">
        <span className="text-xl">{ICON[status] || ICON.pending}</span>
        <span className="text-slate-200">{label}</span>
        {status === 'failed' && (
          <span className="text-xs text-amber-400 ml-1">降级运行</span>
        )}
      </div>
      <span className="text-slate-400 text-sm">{tail}</span>
    </div>
  );
}

function UidProgressBlock({ uid, progress }) {
  return (
    <div className="bg-slate-800/60 rounded-lg overflow-hidden border border-slate-700/40">
      {SKILL_ORDER.map(({ key, label }) => (
        <SkillRow
          key={key}
          label={label}
          status={(progress[key] && progress[key].status) || 'pending'}
          durationMs={progress[key] && progress[key].durationMs}
        />
      ))}
    </div>
  );
}

function CollapsedUidRow({ uid, status, durationMs, onExpand }) {
  const icon = status === 'done' ? ICON.done
             : status === 'pending' ? ICON.pending
             : ICON.running;
  const tail = status === 'done' ? _formatDuration(durationMs)
             : status === 'pending' ? '等待中'
             : '进行中…';
  return (
    <button
      type="button"
      onClick={status === 'done' ? onExpand : undefined}
      className={`w-full flex items-center justify-between py-2 px-4 ${
        status === 'done' ? 'hover:bg-slate-800/40 cursor-pointer' : 'cursor-default'
      } border-b border-slate-700/40 last:border-b-0`}
    >
      <div className="flex items-center gap-3">
        <span className="text-xl">{icon}</span>
        <span className="text-slate-200">UID {uid}</span>
      </div>
      <span className="text-slate-400 text-sm">{tail}</span>
    </button>
  );
}

function ProgressView({
  uids,
  activeUid,
  progressByUid,    // { uid: { skill_key: { status, durationMs } } }
  uidStatus,        // { uid: 'pending' | 'running' | 'done' }
  uidDurations,     // { uid: totalMs }
  elapsedSec,
  completedCount,
  totalCount,
  onExpandUid
}) {
  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center text-white p-8">
      <div className="w-full max-w-2xl">
        <div className="mb-6 text-center">
          <h2 className="text-2xl font-semibold mb-2 bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-400">
            AI 智能体矩阵分析中
          </h2>
          <p className="text-slate-400 text-sm">
            分析进度：{completedCount} / {totalCount} 完成 ⏱ 已用 {elapsedSec}s
          </p>
        </div>

        {(uids || []).map((uid) => {
          const isActive = uid === activeUid;
          if (isActive) {
            return (
              <div key={uid} className="mb-4">
                <p className="text-slate-300 text-sm mb-2">UID {uid}</p>
                <UidProgressBlock uid={uid} progress={progressByUid[uid] || {}} />
              </div>
            );
          }
          return (
            <CollapsedUidRow
              key={uid}
              uid={uid}
              status={uidStatus[uid] || 'pending'}
              durationMs={uidDurations[uid]}
              onExpand={() => onExpandUid && onExpandUid(uid)}
            />
          );
        })}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ProgressView = ProgressView;
