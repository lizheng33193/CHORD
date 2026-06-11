const {
  Headphones,
  AlertTriangle,
  Phone,
  Gift,
  TrendingDown,
  Lightbulb
} = window.LucideReact || {};
const { MarkdownBlock } = window.AppComponents;
const { objectValue, arrayValue, stringValue, numberValue } = window.AppUtils.normalize;

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

function StrategyCard({ icon: Icon, title, primary, secondary, accent, children }) {
  return (
    <div className="bg-slate-50/70 border border-slate-200 rounded-2xl p-5 hover:bg-white transition-colors duration-300">
      <h4 className="text-sm font-bold text-slate-700 mb-4 flex items-center gap-2">
        {Icon ? <Icon className={`w-4 h-4 ${accent || 'text-violet-500'}`} /> : null}
        {title}
      </h4>
      <div className="space-y-2">
        {primary ? <p className="text-base font-semibold text-slate-800">{primary}</p> : null}
        {secondary ? <p className="text-xs text-slate-500 leading-relaxed">{secondary}</p> : null}
        {children}
      </div>
    </div>
  );
}

function OpsAdvicePanel({ profile }) {
  const structured = objectValue(profile?.structured_result);
  const hasData = profile && profile.structured_result && Object.keys(structured).length > 0;

  if (!hasData) {
    return (
      <div className="animate-in fade-in duration-500">
        <div className="bg-white border border-slate-200 rounded-2xl p-10 text-center text-slate-400 text-sm">
          暂无运营策略数据
        </div>
      </div>
    );
  }

  const segmentName = stringValue(structured.segment_name, '未分层');
  const collection = objectValue(structured.collection_strategy);
  const churn = objectValue(structured.churn_warning);
  const churnLevel = stringValue(churn.level, '');
  const churnSignals = arrayValue(churn.signals);
  const outreach = objectValue(structured.outreach_channel);
  const offer = objectValue(structured.retention_offer);
  const validDays = numberValue(offer.valid_days, null);
  const tags = arrayValue(structured.tags);
  const churnRootCause = arrayValue(structured.churn_root_cause);

  const churnRootCauseLabels = {
    credit_limit_unmet: '额度不及预期',
    interest_perception_high: '利息感知过高',
    competitor_poaching: '竞品挖角',
    ux_friction: '操作体验差',
    repayment_burden: '还款压力大',
    no_clear_signal: '无明确信号',
  };

  const explanation = objectValue(structured.explanation);
  const retentionPitch = stringValue(explanation.retention_pitch, '');
  const reportMarkdown = stringValue(profile.report_markdown, '');

  return (
    <div className="animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-100 flex-wrap gap-4">
        <div className="flex items-center gap-3">
          {Headphones ? <Headphones className="w-8 h-8 text-violet-600" /> : null}
          <div>
            <h2 className="text-2xl font-bold text-slate-800">Skill 6: 运营策略建议</h2>
            <p className="text-sm text-slate-500 mt-1">{segmentName}</p>
          </div>
        </div>
        {churnLevel ? (
          <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium ${churnLevelBadgeClass(churnLevel)}`}>
            流失风险 {churnLevel}
          </span>
        ) : null}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <StrategyCard
          icon={AlertTriangle}
          title="催收策略"
          primary={stringValue(collection.intensity, '—')}
          secondary={collection.trigger ? `触发条件：${stringValue(collection.trigger, '')}` : ''}
          accent="text-orange-500"
        />
        <StrategyCard
          icon={TrendingDown}
          title="流失预警"
          primary={churnLevel || '—'}
          accent="text-red-500"
        >
          {churnSignals.length > 0 ? (
            <ul className="text-xs text-slate-600 list-disc pl-4 space-y-1 mt-1">
              {churnSignals.map((sig, idx) => (
                <li key={`${idx}-${sig}`}>{stringValue(sig, '')}</li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-400">暂无预警信号</p>
          )}
          {churnRootCause.length > 0 && churnRootCause[0] !== 'no_clear_signal' ? (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {churnRootCause.map((cause, idx) => (
                <span key={`rc-${idx}`} className="bg-red-50 text-red-600 border border-red-200 rounded-full px-2 py-0.5 text-xs">
                  {churnRootCauseLabels[cause] || cause}
                </span>
              ))}
            </div>
          ) : null}
        </StrategyCard>
        <StrategyCard
          icon={Phone}
          title="触达渠道"
          primary={stringValue(outreach.primary, '—')}
          secondary={outreach.best_time ? `最佳时段：${stringValue(outreach.best_time, '')}` : ''}
          accent="text-blue-500"
        />
        <StrategyCard
          icon={Gift}
          title="留存优惠"
          primary={stringValue(offer.type, '—')}
          secondary={validDays !== null ? `有效期 ${validDays} 天` : ''}
          accent="text-pink-500"
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

      {retentionPitch ? (
        <div className="bg-gradient-to-br from-violet-50 to-purple-50 border border-violet-200 rounded-2xl p-6 mb-6">
          <h4 className="text-sm font-bold text-violet-900 mb-3 flex items-center gap-2">
            {Lightbulb ? <Lightbulb className="w-4 h-4" /> : null}
            留存话术建议
          </h4>
          <MarkdownBlock content={retentionPitch} />
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
window.AppComponents.OpsAdvicePanel = OpsAdvicePanel;
