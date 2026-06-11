// Trace UI / KeyEventsTimeline — collapsible event log (default folded).
// Default-folded behavior locked by Design Doc §11.

const { ChevronDown, ChevronRight } = window.LucideReact;

function KeyEventsTimeline({ events }) {
  const [expanded, setExpanded] = React.useState(false);
  const items = Array.isArray(events) ? events : [];

  const sorted = [...items].sort((a, b) => {
    const ao = (a && a.ts_offset) || 0;
    const bo = (b && b.ts_offset) || 0;
    return ao - bo;
  });

  if (sorted.length === 0) {
    return (
      <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
        <h3 className="mb-3 text-base font-semibold text-slate-800">关键事件</h3>
        <div className="text-sm text-slate-400 py-4">暂无事件</div>
      </div>
    );
  }

  const Icon = expanded ? ChevronDown : ChevronRight;

  function onToggle() {
    setExpanded(!expanded);
  }

  function onKey(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onToggle();
    }
  }

  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={onKey}
        className="flex items-center gap-2 cursor-pointer rounded-lg px-1 py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
      >
        <Icon className="w-4 h-4 text-slate-500" />
        <h3 className="text-base font-semibold text-slate-800">
          最后 {sorted.length} 步事件
        </h3>
      </div>

      {expanded && (
        <div className="mt-4 relative pl-6">
          <div className="absolute left-2 top-1 bottom-1 w-px bg-slate-200" />
          <ul className="space-y-2">
            {sorted.map((ev, idx) => {
              const ts = (ev && ev.ts_offset) || 0;
              const page = (ev && ev.page) || '未知页面';
              const event = (ev && ev.event) || '未知事件';
              const fieldPart = ev && ev.field ? ` · ${ev.field}` : '';
              return (
                <li key={idx} className="relative">
                  <span className="absolute -left-[18px] top-1.5 inline-block w-2 h-2 rounded-full bg-violet-500" />
                  <div className="font-mono text-xs text-slate-700">
                    [+{ts}s] {page} · {event}{fieldPart}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.KeyEventsTimeline = KeyEventsTimeline;
