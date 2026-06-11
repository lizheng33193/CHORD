// Extracted from app/ui/live_frontend.py during UI separation Step-1.

const { stringValue, arrayValue, objectValue } = window.AppUtils.normalize;

function MetricHelpTip({ explanation, isOpen, onMouseEnter, onMouseLeave, onToggle }) {
  const hasContent = Object.keys(objectValue(explanation)).length > 0;
  return (
    <div className="relative" onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      <button
        type="button"
        className="w-5 h-5 rounded-full bg-slate-100 text-slate-500 text-xs font-bold hover:bg-slate-200 transition-colors"
        onClick={onToggle}
        aria-label="查看指标说明"
      >
        ❗
      </button>
      {isOpen && hasContent ? (
        <div className="absolute z-20 top-7 left-0 w-80 rounded-2xl border border-slate-200 bg-white shadow-xl p-4 text-xs text-slate-600 leading-6">
          <div className="font-semibold text-slate-800 mb-1">{stringValue(explanation.label, '指标说明')}</div>
          <div className="mb-2">{stringValue(explanation.meaning, '暂无说明。')}</div>
          <div className="text-slate-700 mb-1"><strong>分数规则：</strong>{stringValue(explanation.score_formula, '暂无规则')}</div>
          <div className="text-slate-700 mb-1"><strong>当前结果：</strong>{stringValue(explanation.inference_value, '暂无')}</div>
          <div className="mt-2 space-y-1">
            {arrayValue(explanation.evidence_lines).map((line, index) => (
              <div key={`${line}-${index}`} className="rounded-xl bg-slate-50 px-3 py-2 border border-slate-100">
                {line}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.MetricHelpTip = MetricHelpTip;
