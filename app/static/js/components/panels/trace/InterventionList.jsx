// Trace UI / InterventionList — intervention suggestion cards.
// MarkdownBlock signature is `{ text }` — see invariant 1.4 in
// docs/plans/trace-ui-plan.md.

const { MarkdownBlock } = window.AppComponents;

function InterventionList({ suggestions }) {
  const items = Array.isArray(suggestions) ? suggestions : [];

  if (items.length === 0) {
    return (
      <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
        <h3 className="mb-3 text-base font-semibold text-slate-800">干预建议</h3>
        <div className="text-sm text-slate-400 py-4">暂无干预建议</div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
      <h3 className="mb-4 text-base font-semibold text-slate-800">干预建议</h3>
      <div className="space-y-4">
        {items.map((item, idx) => {
          const hotspot = (item && item.hotspot) || '未知热点';
          const advice = (item && item.advice) || '暂无干预建议。';
          const channelHint = item && item.channel_hint;
          return (
            <div
              key={idx}
              className="relative rounded-xl border border-slate-200 bg-slate-50 p-4"
            >
              <span className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
                {hotspot}
              </span>
              <div className="mt-3 text-slate-800">
                <MarkdownBlock text={advice || '暂无干预建议。'} />
              </div>
              {channelHint && (
                <div className="mt-2 text-right text-xs text-slate-400">
                  {channelHint}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.InterventionList = InterventionList;
