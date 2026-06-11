// Trace UI / TimePatternCard — 24-bar pure-CSS hour histogram.
// Color tiers locked by Design Doc §5.5 (5 fixed bands on violet scale).

function TimePatternCard({ timePattern }) {
  const rawHistogram = (timePattern && timePattern.hour_histogram) || [];
  const hours = [];
  for (let i = 0; i < 24; i++) {
    const v = rawHistogram[i];
    hours.push(typeof v === 'number' && !Number.isNaN(v) ? v : 0);
  }
  const activeWindowLabel = (timePattern && timePattern.active_window_label) || '暂无活跃窗口';
  const max = Math.max(...hours, 0);

  function colorClass(count) {
    if (count === 0 || max === 0) return 'bg-slate-100';
    const ratio = count / max;
    if (ratio <= 0.25) return 'bg-violet-300';
    if (ratio <= 0.5) return 'bg-violet-400';
    if (ratio <= 0.75) return 'bg-violet-500';
    return 'bg-violet-600';
  }

  function heightPct(count) {
    if (count === 0 || max === 0) return 4;
    const ratio = count / max;
    return Math.max(4, ratio * 100);
  }

  const ticks = [0, 6, 12, 18, 23];

  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-800">活跃时段分布</h3>
        <span className="inline-flex items-center rounded-full bg-violet-100 px-3 py-1 text-xs font-medium text-violet-700">
          {activeWindowLabel}
        </span>
      </div>

      <div className="flex items-end gap-px h-32">
        {hours.map((count, hour) => (
          <div
            key={hour}
            className={'flex-1 rounded-t ' + colorClass(count)}
            style={{ height: heightPct(count) + '%' }}
            title={hour + ':00 → ' + count + ' 事件'}
          />
        ))}
      </div>

      <div className="mt-2 flex text-xs text-slate-500">
        {Array.from({ length: 24 }, (_, h) => (
          <div key={h} className="flex-1 text-center">
            {ticks.includes(h) ? h : ''}
          </div>
        ))}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.TimePatternCard = TimePatternCard;
