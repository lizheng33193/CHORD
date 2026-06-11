// Trace UI / FrictionHotspotGrid — severity-colored hotspot cards.
// Kept in sync with app/static/js/components/panels/OpsAdvicePanel.jsx churnLevelBadgeClass
// (lines 12-24 there). OpsAdvicePanel itself is not modified — invariant 0.3.

function churnLevelBadgeClass(level) {
  const l = (level || '').toLowerCase();
  if (l.includes('高') || l.includes('high')) {
    return 'bg-red-100 text-red-700 border-red-200';
  }
  if (l.includes('中') || l.includes('medium')) {
    return 'bg-amber-100 text-amber-700 border-amber-200';
  }
  if (l.includes('低') || l.includes('low')) {
    return 'bg-green-100 text-green-700 border-green-200';
  }
  return 'bg-slate-100 text-slate-700 border-slate-200';
}

function severityBarClass(severity) {
  const s = (severity || '').toLowerCase();
  if (s === 'high') return 'bg-red-500';
  if (s === 'medium') return 'bg-amber-500';
  return 'bg-slate-400';
}

function severityRank(severity) {
  const s = (severity || '').toLowerCase();
  if (s === 'high') return 3;
  if (s === 'medium') return 2;
  if (s === 'low') return 1;
  return 0;
}

function FrictionHotspotGrid({ hotspots }) {
  const items = Array.isArray(hotspots) ? hotspots : [];

  const sorted = [...items].sort((a, b) => {
    const sd = severityRank(b && b.severity) - severityRank(a && a.severity);
    if (sd !== 0) return sd;
    const aRetry = (a && a.retry_count) || 0;
    const aErr = (a && a.error_count) || 0;
    const bRetry = (b && b.retry_count) || 0;
    const bErr = (b && b.error_count) || 0;
    return (bRetry + bErr) - (aRetry + aErr);
  });

  if (sorted.length === 0) {
    return (
      <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
        <h3 className="mb-3 text-base font-semibold text-slate-800">摩擦热点</h3>
        <div className="text-sm text-slate-400 py-4">暂无摩擦点</div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
      <h3 className="mb-4 text-base font-semibold text-slate-800">摩擦热点</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {sorted.map((h, idx) => {
          const step = (h && h.step) || '未知步骤';
          const severity = (h && h.severity) || '';
          const retry = (h && h.retry_count) || 0;
          const errs = (h && h.error_count) || 0;
          const stay = (h && h.avg_stay_seconds) || 0;
          return (
            <div
              key={idx}
              className="relative flex overflow-hidden rounded-xl border border-slate-200 bg-slate-50"
            >
              <div className={'w-1 shrink-0 ' + severityBarClass(severity)} />
              <div className="flex-1 p-4">
                <div className="mb-3 flex items-center gap-2">
                  <span className="font-mono text-sm text-slate-800 truncate">{step}</span>
                  <span
                    className={
                      'ml-auto inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ' +
                      churnLevelBadgeClass(severity)
                    }
                  >
                    {severity || 'unknown'}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-xs text-slate-600">
                  <div>
                    <div className="text-slate-400">重试</div>
                    <div className="text-sm font-semibold text-slate-800">{retry}</div>
                  </div>
                  <div>
                    <div className="text-slate-400">错误</div>
                    <div className="text-sm font-semibold text-slate-800">{errs}</div>
                  </div>
                  <div>
                    <div className="text-slate-400">停留</div>
                    <div className="text-sm font-semibold text-slate-800">{Number(stay).toFixed(1)}s</div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.FrictionHotspotGrid = FrictionHotspotGrid;
