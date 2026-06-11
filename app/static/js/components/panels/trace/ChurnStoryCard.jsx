// Trace UI / ChurnStoryCard — narrative card for response.churn_story.
// Cross-link: visual style mirrors OpsAdvicePanel retention_pitch region
// (app/static/js/components/panels/OpsAdvicePanel.jsx). OpsAdvicePanel itself
// is not modified — see docs/plans/trace-ui-plan.md invariant 0.3.

const { MarkdownBlock } = window.AppComponents;

function ChurnStoryCard({ story, modelTrace }) {
  const isFallback = modelTrace && modelTrace.used_llm === false;
  const text = story || '暂无行为故事线。';

  return (
    <div className="relative rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 p-6 shadow-lg">
      {isFallback && (
        <span className="absolute top-3 right-3 inline-flex items-center rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-700">
          模板兜底（model_unavailable）
        </span>
      )}
      <h3 className="mb-3 text-base font-semibold text-white">流失归因故事线</h3>
      <div className="rounded-xl bg-white/95 p-4 text-slate-800">
        <MarkdownBlock text={text} />
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChurnStoryCard = ChurnStoryCard;
