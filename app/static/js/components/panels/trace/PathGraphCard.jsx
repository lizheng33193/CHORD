// Trace UI / PathGraphCard — top_pages table + top_transitions list.
// Two-column on desktop (md:grid-cols-2), single column on mobile.

const { ArrowRight } = window.LucideReact;

function PathGraphCard({ pathGraph }) {
  const topPages = (pathGraph && pathGraph.top_pages) || [];
  const topTransitions = (pathGraph && pathGraph.top_transitions) || [];

  const sortedPages = [...topPages].sort(
    (a, b) => (b.visit_count || 0) - (a.visit_count || 0)
  );

  function formatStay(p) {
    const v = p && p.avg_stay_seconds;
    if (v === null || v === undefined || Number.isNaN(v)) return '-';
    return `${Number(v).toFixed(1)}s`;
  }

  function transitionEnds(t) {
    const from = (t && (t.from || t.from_page)) || '?';
    const to = (t && (t.to || t.to_page)) || '?';
    return { from, to };
  }

  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
      <h3 className="mb-4 text-base font-semibold text-slate-800">操作路径</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            热门页面 (top_pages)
          </div>
          {sortedPages.length === 0 ? (
            <div className="text-sm text-slate-400 py-4">暂无页面访问数据</div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">页面</th>
                    <th className="px-3 py-2 text-right font-medium">访问</th>
                    <th className="px-3 py-2 text-right font-medium">平均停留</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPages.map((p, idx) => (
                    <tr key={idx} className="border-t border-slate-100">
                      <td className="px-3 py-2 text-slate-800 font-mono text-xs">{p.page || '-'}</td>
                      <td className="px-3 py-2 text-right text-slate-700">{p.visit_count ?? 0}</td>
                      <td className="px-3 py-2 text-right text-slate-500">{formatStay(p)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            主要跳转 (top_transitions)
          </div>
          {topTransitions.length === 0 ? (
            <div className="text-sm text-slate-400 py-4">暂无跳转数据</div>
          ) : (
            <div className="space-y-2">
              {topTransitions.map((t, idx) => {
                const { from, to } = transitionEnds(t);
                const count = t.count ?? 0;
                return (
                  <div
                    key={idx}
                    className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
                  >
                    <span className="font-mono text-xs text-slate-700 truncate">{from}</span>
                    <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />
                    <span className="font-mono text-xs text-slate-700 truncate">{to}</span>
                    <span className="ml-auto inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                      ×{count}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.PathGraphCard = PathGraphCard;
