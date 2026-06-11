const {
  Package,
  Target,
  RefreshCw,
  TrendingUp,
  DollarSign,
  Send,
  Lightbulb
} = window.LucideReact || {};
const { MarkdownBlock } = window.AppComponents;
const { objectValue, arrayValue, stringValue } = window.AppUtils.normalize;

function priorityBadgeClass(priority) {
  const p = (priority || '').toLowerCase();
  if (p.includes('高') || p.includes('high') || p.includes('p0') || p.includes('p1')) {
    return 'bg-red-100 text-red-700 border-red-200';
  }
  if (p.includes('中') || p.includes('medium') || p.includes('p2')) {
    return 'bg-amber-100 text-amber-700 border-amber-200';
  }
  if (p.includes('低') || p.includes('low') || p.includes('p3')) {
    return 'bg-green-100 text-green-700 border-green-200';
  }
  return 'bg-slate-100 text-slate-700 border-slate-200';
}

function StrategyCard({ icon: Icon, title, primary, secondary, accent }) {
  return (
    <div className="bg-slate-50/70 border border-slate-200 rounded-2xl p-5 hover:bg-white transition-colors duration-300">
      <h4 className="text-sm font-bold text-slate-700 mb-4 flex items-center gap-2">
        {Icon ? <Icon className={`w-4 h-4 ${accent || 'text-emerald-500'}`} /> : null}
        {title}
      </h4>
      <div className="space-y-2">
        <p className="text-base font-semibold text-slate-800">{primary || '—'}</p>
        {secondary ? <p className="text-xs text-slate-500 leading-relaxed">{secondary}</p> : null}
      </div>
    </div>
  );
}

function ProductAdvicePanel({ profile }) {
  const structured = objectValue(profile?.structured_result);
  const hasData = profile && profile.structured_result && Object.keys(structured).length > 0;

  if (!hasData) {
    return (
      <div className="animate-in fade-in duration-500">
        <div className="bg-white border border-slate-200 rounded-2xl p-10 text-center text-slate-400 text-sm">
          暂无产品策略数据
        </div>
      </div>
    );
  }

  const segmentName = stringValue(structured.segment_name, '未分层');
  const priority = stringValue(structured.priority, '');
  const renewal = objectValue(structured.renewal_strategy);
  const creditLine = objectValue(structured.credit_line_action);
  const ratePlan = objectValue(structured.rate_plan);
  const channel = objectValue(structured.recommended_channel);
  const tags = arrayValue(structured.tags);
  const explanation = objectValue(structured.explanation);
  const recommendationSummary = stringValue(explanation.recommendation_summary, '');
  const reportMarkdown = stringValue(profile.report_markdown, '');

  return (
    <div className="animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-100 flex-wrap gap-4">
        <div className="flex items-center gap-3">
          {Package ? <Package className="w-8 h-8 text-emerald-600" /> : null}
          <div>
            <h2 className="text-2xl font-bold text-slate-800">Skill 5: 产品策略建议</h2>
            <p className="text-sm text-slate-500 mt-1">{segmentName}</p>
          </div>
        </div>
        {priority ? (
          <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium ${priorityBadgeClass(priority)}`}>
            优先级 {priority}
          </span>
        ) : null}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <StrategyCard
          icon={RefreshCw}
          title="续贷策略"
          primary={stringValue(renewal.action, '—')}
          secondary={stringValue(renewal.reason, '')}
          accent="text-emerald-500"
        />
        <StrategyCard
          icon={TrendingUp}
          title="额度动作"
          primary={stringValue(creditLine.action, '—')}
          secondary={stringValue(creditLine.reason, '')}
          accent="text-teal-500"
        />
        <StrategyCard
          icon={DollarSign}
          title="费率方案"
          primary={stringValue(ratePlan.plan, '—')}
          secondary={ratePlan.anchor_competitor ? `锚定竞品：${stringValue(ratePlan.anchor_competitor, '')}` : ''}
          accent="text-amber-500"
        />
        <StrategyCard
          icon={Send}
          title="推荐渠道"
          primary={stringValue(channel.primary, '—')}
          secondary={channel.best_time ? `最佳时段：${stringValue(channel.best_time, '')}` : ''}
          accent="text-blue-500"
        />
      </div>

      {tags.length > 0 ? (
        <div className="mb-6 flex flex-wrap gap-2">
          {tags.map((tag, idx) => (
            <span key={`${tag}-${idx}`} className="bg-blue-100 text-blue-700 rounded-full px-2 py-0.5 text-xs">
              {stringValue(tag, '')}
            </span>
          ))}
        </div>
      ) : null}

      {recommendationSummary ? (
        <div className="bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-200 rounded-2xl p-6 mb-6">
          <h4 className="text-sm font-bold text-emerald-900 mb-3 flex items-center gap-2">
            {Lightbulb ? <Lightbulb className="w-4 h-4" /> : null}
            LLM 业务解读
          </h4>
          <MarkdownBlock content={recommendationSummary} />
        </div>
      ) : null}

      {reportMarkdown ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-6">
          <h4 className="text-sm font-bold text-slate-700 mb-3">完整研判</h4>
          <MarkdownBlock content={reportMarkdown} />
        </div>
      ) : null}
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ProductAdvicePanel = ProductAdvicePanel;
