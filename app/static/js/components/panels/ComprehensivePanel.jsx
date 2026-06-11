// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// Source: ComprehensivePanelV2 at L490-L663.
// File / NS name preserved as ComprehensivePanel (user direction);
// legacy ComprehensivePanel at L440 is dead code and intentionally dropped.

const {
  Network,
  Calendar,
  UserCheck,
  Target,
  ShieldCheck,
  Award,
  User,
  Activity,
  CreditCard,
  AlertTriangle,
  AlertCircle,
  ChevronRight,
  BrainCircuit,
  CheckCircle2,
  Bot,
  Lightbulb,
  MessageSquare
} = window.LucideReact || {};
const { objectValue, arrayValue, stringValue, numberValue } = window.AppUtils.normalize;
const { MarkdownBlock } = window.AppComponents;
const {
  toConfidenceDisplay,
  toSegmentDisplay,
  toSegmentFeature,
  toRiskDisplay,
  toValueSignalDisplay
} = window.AppUtils.displayMappers;
const { buildComprehensiveMarketingSuggestion, buildComprehensiveRiskSuggestion } = window.AppUtils.advice;

function ComprehensivePanel({ profile }) {
  const structured = profile?.structured_result || {};
  const metrics = objectValue(structured.metrics);
  const tags = arrayValue(structured.tags);
  const modelTrace = objectValue(structured.model_trace);
  const upstreamSummaries = objectValue(structured.upstream_summaries);
  const overview = objectValue(structured.overview);
  const foundation = objectValue(structured.foundation);
  const behaviorInsight = objectValue(structured.behavior_insight);
  const riskFinance = objectValue(structured.risk_finance);
  const conflictResolution = objectValue(structured.conflict_resolution);
  const llmDiagnosis = objectValue(structured.llm_diagnosis);
  const riskLevel = stringValue(metrics.risk_level, 'unknown');
  const segment = stringValue(overview.segment, stringValue(metrics.segment, 'S6'));
  const valueSignal = stringValue(metrics.value_signal_level, 'low');
  const confidenceLevel = stringValue(metrics.confidence_level, 'low');
  const conflictCount = numberValue(metrics.conflict_count, 0);
  const conflictExplanations = arrayValue(metrics.conflict_explanations);
  const conflictText = stringValue(conflictResolution.conflict_text, stringValue(conflictExplanations[0], '暂无明显的跨信号冲突说明。'));
  const persona = stringValue(foundation.persona, stringValue(structured.persona, 'unknown'));
  const llmAccepted = Boolean(modelTrace.used_llm);
  const llmStatus = llmAccepted ? 'LLM 推理完成' : '规则降级结果';
  const llmStatusClass = llmAccepted ? 'bg-green-50 text-green-700 border-green-200' : 'bg-amber-50 text-amber-700 border-amber-200';
  const appSummary = stringValue(upstreamSummaries.app_profile, '暂无 App 画像摘要');
  const behaviorSummary = stringValue(behaviorInsight.summary, stringValue(upstreamSummaries.behavior_profile, '暂无行为画像摘要'));
  const creditSummary = stringValue(riskFinance.note, stringValue(upstreamSummaries.credit_profile, '暂无信用画像摘要'));
  const headline = stringValue(structured.headline, stringValue(llmDiagnosis.primary_text, stringValue(profile.summary, '暂无综合画像结论')));
  const resolutionText = stringValue(conflictResolution.resolution_text, stringValue(profile.summary, '暂无综合判定。'));
  const growthActions = arrayValue(llmDiagnosis.growth_actions);
  const riskActions = arrayValue(llmDiagnosis.risk_actions);
  const marketingSuggestion = stringValue(growthActions[0], buildComprehensiveMarketingSuggestion(segment, valueSignal, llmAccepted));
  const marketingSuggestionSecondary = stringValue(growthActions[1], `建议结合 ${toSegmentDisplay(segment)} 的客群定位，优先展示与 ${toValueSignalDisplay(valueSignal)} 匹配的权益或额度方案。`);
  const riskSuggestion = stringValue(riskActions[0], buildComprehensiveRiskSuggestion(riskLevel, conflictCount, confidenceLevel));
  const riskSuggestionSecondary = stringValue(riskActions[1], llmAccepted ? '当前综合结果已被 LLM 成功采纳，可作为页面主展示结论。' : `当前展示为回退结果，原因：${stringValue(modelTrace.fallback_reason, '模型输出未被采纳')}`);
  const reportMarkdown = stringValue(profile.report_markdown, '');
  return (
    <div className="animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-100 flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Network className="w-8 h-8 text-fuchsia-600" />
          <h2 className="text-2xl font-bold text-slate-800">Skill 4: 综合画像与客群归属分析</h2>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium ${llmStatusClass}`}>{llmStatus}</span>
          <span className="bg-slate-100 px-3 py-1.5 rounded-md text-xs font-medium text-slate-600 flex items-center gap-1.5">
            <Calendar className="w-4 h-4" />
            置信度 {toConfidenceDisplay(confidenceLevel)}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div className="bg-gradient-to-br from-fuchsia-600 to-indigo-700 rounded-2xl p-6 shadow-lg text-white relative overflow-hidden group">
          <div className="absolute -right-6 -bottom-6 opacity-20 transform group-hover:scale-110 transition-transform duration-500">
            <UserCheck className="w-36 h-36" />
          </div>
          <div className="relative z-10">
            <p className="text-white/80 text-sm font-semibold mb-2 flex items-center gap-1.5">
              <Target className="w-4 h-4" />
              最终客群分层
            </p>
            <h3 className="text-3xl font-black mb-3 tracking-wide">{toSegmentDisplay(segment)}</h3>
            <div className="inline-block bg-white/20 px-3 py-1 rounded-full text-xs font-medium backdrop-blur-sm border border-white/20 shadow-sm">
              {segment} · {toSegmentFeature(segment)}
            </div>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex items-center justify-between relative overflow-hidden">
          <div className="absolute top-0 right-0 w-16 h-16 bg-green-50 rounded-bl-full z-0"></div>
          <div className="relative z-10">
            <p className="text-slate-500 text-sm font-bold mb-1">综合风险等级</p>
            <h3 className="text-2xl font-bold text-green-600 mb-1">{toRiskDisplay(riskLevel)}</h3>
            <p className="text-xs text-slate-400">{conflictCount > 0 ? `存在 ${conflictCount} 个跨信号冲突，已纳入解释。` : '当前未发现明显跨信号冲突。'}</p>
          </div>
          <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center text-green-500 relative z-10 shadow-sm border border-green-200/50">
            <ShieldCheck className="w-7 h-7" />
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex items-center justify-between relative overflow-hidden">
          <div className="absolute top-0 right-0 w-16 h-16 bg-amber-50 rounded-bl-full z-0"></div>
          <div className="relative z-10">
            <p className="text-slate-500 text-sm font-bold mb-1">综合价值等级</p>
            <h3 className="text-2xl font-bold text-amber-600 mb-1">{toValueSignalDisplay(valueSignal)}</h3>
            <p className="text-xs text-slate-400">{stringValue(profile.summary, '暂无综合画像结论')}</p>
          </div>
          <div className="w-14 h-14 rounded-full bg-amber-100 flex items-center justify-center text-amber-500 relative z-10 shadow-sm border border-amber-200/50">
            <Award className="w-7 h-7" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div className="bg-slate-50/70 border border-slate-200 rounded-2xl p-5 hover:bg-white transition-colors duration-300">
          <h4 className="text-sm font-bold text-slate-700 mb-5 flex items-center gap-2">
            <User className="w-4 h-4 text-blue-500" />
            基础归属
          </h4>
          <ul className="space-y-4">
            <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">Persona</span><span className="font-semibold text-slate-800 text-sm text-right">{persona}</span></li>
            <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">Segment</span><span className="font-semibold text-slate-800 text-sm">{segment}</span></li>
            <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">价值层级</span><span className="font-semibold text-slate-800 text-sm">{toValueSignalDisplay(valueSignal)}</span></li>
            <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">当前状态</span><span className={`text-[11px] font-bold px-2 py-0.5 rounded border ${llmAccepted ? 'bg-green-100 text-green-700 border-green-200' : 'bg-amber-100 text-amber-700 border-amber-200'}`}>{llmStatus}</span></li>
          </ul>
        </div>

        <div className="bg-slate-50/70 border border-slate-200 rounded-2xl p-5 hover:bg-white transition-colors duration-300">
          <h4 className="text-sm font-bold text-slate-700 mb-5 flex items-center gap-2">
            <Activity className="w-4 h-4 text-green-500" />
            行为与偏好
          </h4>
          <div className="space-y-4">
            <div>
              <div className="text-slate-500 text-xs mb-1">App 画像摘要</div>
              <p className="font-medium text-slate-800 text-sm leading-relaxed">{appSummary}</p>
            </div>
            <div>
              <div className="text-slate-500 text-xs mb-1">行为画像摘要</div>
              <p className="font-medium text-slate-800 text-sm leading-relaxed">{behaviorSummary}</p>
            </div>
          </div>
        </div>

        <div className="bg-slate-50/70 border border-slate-200 rounded-2xl p-5 hover:bg-white transition-colors duration-300">
          <h4 className="text-sm font-bold text-slate-700 mb-5 flex items-center gap-2">
            <CreditCard className="w-4 h-4 text-orange-500" />
            风险与金融
          </h4>
          <ul className="space-y-3.5">
            <li className="flex items-center justify-between"><span className="text-slate-500 text-sm">综合风险</span><span className="font-semibold text-slate-800 text-sm">{toRiskDisplay(riskLevel)}</span></li>
            <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">信用画像摘要</span><span className="font-semibold text-slate-800 text-sm text-right max-w-[58%]">{creditSummary}</span></li>
            <li className="flex items-center justify-between"><span className="text-slate-500 text-sm">客群特征</span><span className="font-semibold text-slate-800 text-sm">{toSegmentFeature(segment)}</span></li>
            <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">核心标签</span><span className="font-semibold text-slate-800 text-sm text-right max-w-[58%]">{tags.slice(0, 2).join(' / ') || '暂无标签'}</span></li>
          </ul>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-gradient-to-b from-amber-50 to-white border border-amber-200 rounded-2xl p-6 shadow-sm relative overflow-hidden flex flex-col">
          <div className="absolute top-0 left-0 w-1.5 h-full bg-amber-400"></div>
          <h4 className="text-sm font-bold text-amber-900 mb-5 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
            多智能体信号冲突校验
          </h4>
          <div className="flex-1 flex flex-col justify-center space-y-4">
            <div className="bg-white p-4 rounded-xl border border-amber-100 shadow-sm relative">
              <div className="absolute -left-2 top-4 w-4 h-4 bg-white border border-amber-200 rotate-45 transform -translate-x-1/2"></div>
              <p className="text-xs text-amber-700 font-bold mb-2 flex items-center gap-1.5"><AlertCircle className="w-4 h-4" /> 发现的主要冲突</p>
              <p className="text-[13px] text-slate-700 leading-relaxed text-justify">{conflictText}</p>
            </div>
            <div className="flex justify-center -my-2"><ChevronRight className="w-6 h-6 text-amber-300 rotate-90" /></div>
            <div className="bg-amber-500 text-white p-4 rounded-xl shadow-md relative overflow-hidden">
              <div className="absolute -right-4 -bottom-4 opacity-10"><BrainCircuit className="w-24 h-24" /></div>
              <p className="text-xs text-amber-100 font-bold mb-2 flex items-center gap-1.5 relative z-10"><CheckCircle2 className="w-4 h-4" /> 综合判定</p>
              <p className="text-[13px] leading-relaxed relative z-10 text-justify">{profile.summary || '暂无综合判定。'}</p>
            </div>
          </div>
        </div>

        <div className="lg:col-span-2 bg-slate-800 rounded-2xl p-6 shadow-md relative overflow-hidden text-slate-300 flex flex-col">
          <div className="absolute top-0 right-0 w-64 h-64 bg-fuchsia-600/20 rounded-full blur-3xl mix-blend-screen pointer-events-none"></div>
          <div className="absolute bottom-0 left-10 w-40 h-40 bg-blue-500/20 rounded-full blur-2xl mix-blend-screen pointer-events-none"></div>
          <div className="flex items-center gap-2 mb-5 relative z-10">
            <Bot className="w-5 h-5 text-fuchsia-400" />
            <h4 className="text-sm font-bold text-white tracking-wide">LLM 业务研判与运营建议</h4>
          </div>
          <div className="bg-slate-900/60 rounded-xl p-5 mb-5 border border-slate-700/50 relative z-10 shadow-inner">
            <p className="text-[13px] leading-relaxed text-slate-200 text-justify">{headline}</p>
          </div>

          <div className="grid grid-cols-1 gap-4 relative z-10 mb-5">
            <div className="bg-slate-800/80 border border-slate-600/50 rounded-xl p-4">
              <p className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider mb-3 flex items-center gap-1.5"><Activity className="w-3.5 h-3.5" /> 三维画像融合摘要</p>
              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <span className="shrink-0 text-[10px] font-bold text-blue-400 bg-blue-500/20 rounded px-1.5 py-0.5 mt-0.5">APP</span>
                  <span className="text-xs text-slate-300 leading-relaxed">{appSummary}</span>
                </div>
                <div className="flex items-start gap-3">
                  <span className="shrink-0 text-[10px] font-bold text-orange-400 bg-orange-500/20 rounded px-1.5 py-0.5 mt-0.5">行为</span>
                  <span className="text-xs text-slate-300 leading-relaxed">{behaviorSummary}</span>
                </div>
                <div className="flex items-start gap-3">
                  <span className="shrink-0 text-[10px] font-bold text-slate-400 bg-slate-500/20 rounded px-1.5 py-0.5 mt-0.5">征信</span>
                  <span className="text-xs text-slate-300 leading-relaxed">{creditSummary}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 relative z-10 mt-auto">
            <div className="bg-slate-800/80 border border-slate-600/50 p-4.5 rounded-xl hover:border-fuchsia-500/50 transition-colors">
              <p className="text-[11px] font-bold text-fuchsia-400 uppercase tracking-wider mb-3 flex items-center gap-1.5"><Lightbulb className="w-3.5 h-3.5" /> 营销触达策略</p>
              <ul className="space-y-3">
                <li className="flex items-start gap-2.5"><div className="w-1.5 h-1.5 rounded-full bg-fuchsia-500 mt-1.5 shrink-0 shadow-[0_0_8px_rgba(217,70,239,0.8)]"></div><span className="text-xs text-slate-300 leading-relaxed">{marketingSuggestion}</span></li>
                <li className="flex items-start gap-2.5"><div className="w-1.5 h-1.5 rounded-full bg-fuchsia-500 mt-1.5 shrink-0 shadow-[0_0_8px_rgba(217,70,239,0.8)]"></div><span className="text-xs text-slate-300 leading-relaxed">{marketingSuggestionSecondary}</span></li>
              </ul>
            </div>
            <div className="bg-slate-800/80 border border-slate-600/50 p-4.5 rounded-xl hover:border-blue-500/50 transition-colors">
              <p className="text-[11px] font-bold text-blue-400 uppercase tracking-wider mb-3 flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5" /> 风险控制策略</p>
              <ul className="space-y-3">
                <li className="flex items-start gap-2.5"><div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 shrink-0 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></div><span className="text-xs text-slate-300 leading-relaxed">{riskSuggestion}</span></li>
                <li className="flex items-start gap-2.5"><div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 shrink-0 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></div><span className="text-xs text-slate-300 leading-relaxed">{riskSuggestionSecondary}</span></li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {reportMarkdown && (
        <div className="mt-6 bg-white p-8 rounded-2xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
            <h3 className="text-xl font-bold text-slate-800">综合画像大模型分析报告</h3>
            <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${llmStatusClass}`}>{llmStatus}</span>
          </div>
          {MarkdownBlock ? <MarkdownBlock text={reportMarkdown} /> : <p className="text-sm text-slate-700 leading-7">{reportMarkdown}</p>}
        </div>
      )}
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ComprehensivePanel = ComprehensivePanel;
