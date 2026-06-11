// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// Note: '\\n+' (L823), /^\\[/ and /\\]$/ (L846) are Python-escape un-nesting fixes,
// extending Plan G.3 关键改动 2 (UID_PATTERN precedent) per user authorization.

const { Activity } = window.LucideReact || {};
const { arrayValue, objectValue, stringValue, numberValue } = window.AppUtils.normalize;

function BehaviorPanel({ profile }) {
  const structured = objectValue(profile?.structured_result);
  const evidence = objectValue(structured.evidence);
  const metrics = objectValue(structured.metrics);
  const modelTrace = objectValue(structured.model_trace);
  const llmAccepted = Boolean(modelTrace.used_llm);
  const llmStatusLabel = llmAccepted ? 'LLM 推理完成' : '规则降级结果';
  const llmStatusClass = llmAccepted ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200';
  const llmProfile = objectValue(evidence.llm_profile).hasOwnProperty('behavior_summary')
    ? objectValue(evidence.llm_profile)
    : objectValue(evidence.llm_behavior_profile);
  const behaviorNarrative = objectValue(evidence.behavior_profile_narrative);
  const timelineNarrative = objectValue(evidence.timeline_narrative);
  const llmTimeline = objectValue(evidence.llm_timeline).hasOwnProperty('sections')
    ? objectValue(evidence.llm_timeline)
    : timelineNarrative;
  const timelineSectionsCompact = arrayValue(evidence.timeline_sections_compact).length
    ? arrayValue(evidence.timeline_sections_compact)
    : arrayValue(evidence.timeline_sections);
  const timelineSectionsRaw = arrayValue(evidence.timeline_sections_raw).length
    ? arrayValue(evidence.timeline_sections_raw)
    : timelineSectionsCompact;
  const timelineInsights = arrayValue(evidence.timeline_insights);
  const globalInfo = objectValue(evidence.global_info).hasOwnProperty('UID')
    ? objectValue(evidence.global_info)
    : objectValue(objectValue(evidence.profile_header).global_info);
  const profileUid = stringValue(globalInfo['UID'], stringValue(structured.uid, '未知'));
  const deviceModel = stringValue(globalInfo['手机机型'], '未知');
  const osVersion = stringValue(globalInfo['系统版本'], '未知');
  const firstIp = stringValue(globalInfo['网络IP'], '').split(',')[0]?.trim() || '未知';
  const appVersion = stringValue(globalInfo['App版本'], '未知');
  const totalEvents = numberValue(
    metrics.interaction_count,
    timelineSectionsRaw.reduce((total, section) => total + arrayValue(section.events).length, 0)
  );
  const compactEvents = numberValue(
    metrics.timeline_event_count_compact,
    timelineSectionsCompact.reduce((total, section) => total + arrayValue(section.events).length, 0)
  );
  const warningSections = numberValue(
    metrics.abnormal_risk_count,
    timelineSectionsCompact.filter((section) =>
      arrayValue(section.events).some((event) => Boolean(event?.is_warning))
    ).length
  );
  const timelineSectionCount = numberValue(metrics.page_node_count, timelineSectionsCompact.length);
  const isDataMissing = stringValue(structured.status, 'ok') === 'data_missing';
  const summary = stringValue(profile?.summary, '暂无行为摘要');
  const narrativeSummary = stringValue(
    behaviorNarrative.behavior_summary,
    stringValue(llmProfile.behavior_summary, summary)
  );
  const businessAdviceText = stringValue(
    behaviorNarrative.business_advice,
    stringValue(llmProfile.business_advice, '暂无经营建议')
  );
  const businessAdviceItems = String(businessAdviceText || '')
    .split(new RegExp('\n+'))
    .map((item) => item.trim())
    .filter(Boolean);
  const journeyInsight = stringValue(
    behaviorNarrative.journey_insight,
    stringValue(timelineInsights[0], '')
  );
  const usedLlmProfile = Boolean(evidence.used_llm_profile);
  const usedLlmTimeline = Boolean(evidence.used_llm_timeline);
  const confidenceLabel = stringValue(
    behaviorNarrative.confidence,
    stringValue(llmProfile.confidence, 'medium')
  );
  const narrativeBySection = arrayValue(llmTimeline.sections).reduce((acc, item) => {
    const sectionId = stringValue(item?.section_id, '');
    if (sectionId) {
      acc[sectionId] = objectValue(item);
    }
    return acc;
  }, {});

  function normalizeTimeLabel(value) {
    if (!value) return '耗时待定';
    return String(value).replace(/^\[/, '').replace(/\]$/, '').trim() || '耗时待定';
  }

  function compactEventCount(section) {
    const explicitCount = numberValue(section.compact_event_count, -1);
    if (explicitCount >= 0) return explicitCount;
    return arrayValue(section.events).length;
  }

  function rawEventCount(section) {
    const explicitCount = numberValue(section.raw_event_count, -1);
    if (explicitCount >= 0) return explicitCount;
    return arrayValue(section.events).length;
  }

  function buildSectionSummary(section, sectionNarrative) {
    // Priority: LLM narrative > rule-based summary from section metadata
    const narrative = stringValue(sectionNarrative.narrative, '');
    if (narrative) return narrative;
    const title = stringValue(section.title, '');
    const compact = compactEventCount(section);
    const raw = rawEventCount(section);
    const warns = numberValue(section.warning_count, 0);
    const dur = stringValue(section.duration_hint, '');
    const bucket = stringValue(section.journey_bucket, '');
    const parts = [];
    if (dur) parts.push(`耗时${dur}`);
    parts.push(`压缩 ${compact} 条动作（原始 ${raw} 条）`);
    if (warns > 0) parts.push(`发现 ${warns} 个异常卡点`);
    if (bucket === 'correction_retry') parts.push('用户在此阶段反复尝试纠错');
    else if (bucket === 'card_bindretry') parts.push('银行卡绑定环节存在重试');
    else if (bucket === 'deep_churn') parts.push('用户在此阶段出现深度沉默或流失信号');
    else if (bucket === 'init') parts.push('用户完成初始化流程');
    else if (bucket === 'basic_profile') parts.push('用户填写基础资料信息');
    return parts.join('，') + '。';
  }

  function scrollToSection(sectionId) {
    const target = document.getElementById(sectionId);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  if (isDataMissing) {
    return (
      <div className="animate-in fade-in duration-500 space-y-6">
        <div className="flex items-center gap-3 mb-2 pb-4 border-b border-slate-100">
          <Activity className="w-8 h-8 text-orange-500" />
          <h2 className="text-2xl font-bold text-slate-800">Skill 2: 行为画像 Agent 分析报告</h2>
        </div>
        <div className="rounded-[28px] border border-slate-200 bg-white px-7 py-8 shadow-sm">
          <div className="text-lg font-semibold text-slate-800 mb-3">暂未识别到可用行为数据</div>
          <p className="text-sm leading-8 text-slate-600">{summary}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 font-sans text-slate-800 animate-in fade-in duration-500">
      <header className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between rounded-[34px] border border-slate-200 bg-white p-7 shadow-sm md:p-10">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-4">
            <span className="inline-flex items-center rounded-full bg-blue-600 px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-white">
              全链路行为画像
            </span>
            <span className="text-[28px] font-bold text-slate-800">UID {profileUid}</span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-600 border border-emerald-200">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
                AI 置信度: {confidenceLabel}
            </span>
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold border ${
              usedLlmProfile || usedLlmTimeline
                ? 'border-blue-200 bg-blue-50 text-blue-600'
                : 'border-slate-200 bg-slate-50 text-slate-500'
            }`}>
              {usedLlmProfile || usedLlmTimeline ? '双链路 LLM 已启用' : '规则摘要回退'}
            </span>
            <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${llmStatusClass}`}>{llmStatusLabel}</span>
          </div>
          <div className="flex flex-wrap gap-3 text-sm text-slate-500">
            <span className="rounded-full bg-slate-50 border border-slate-200 px-4 py-1.5">
              设备: {deviceModel}
            </span>
            <span className="rounded-full bg-slate-50 border border-slate-200 px-4 py-1.5">
              系统: Android {osVersion}
            </span>
            <span className="rounded-full bg-slate-50 border border-slate-200 px-4 py-1.5">
              IP: {firstIp}
            </span>
            <span className="rounded-full bg-slate-50 border border-slate-200 px-4 py-1.5">
              App版本: {appVersion}
            </span>
          </div>
        </div>
        <div className="flex gap-6">
          <div className="text-right">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">页面节点</div>
            <div className="mt-1 text-[28px] font-bold text-slate-700">{timelineSectionCount}</div>
          </div>
          <div className="text-right">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">原始动作</div>
            <div className="mt-1 text-[28px] font-bold text-slate-700">{totalEvents}</div>
          </div>
          <div className="text-right">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">压缩动作</div>
            <div className="mt-1 text-[28px] font-bold text-blue-600">{compactEvents}</div>
          </div>
          <div className="text-right">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">警示/异常</div>
            <div className="mt-1 text-[28px] font-bold text-red-500">{warningSections}</div>
          </div>
        </div>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 items-stretch">
        <article className="flex flex-col rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4">还款意愿</div>
          <div className="flex items-baseline gap-3">
            <span className="text-[28px] font-bold text-slate-800">
              {stringValue(objectValue(llmProfile.repayment_willingness).label, '未知')}
            </span>
            <span className="text-sm font-medium text-amber-500">
              {stringValue(objectValue(llmProfile.repayment_willingness).score, 'N/A')}
            </span>
          </div>
          <hr className="my-5 border-dashed border-slate-200" />
          <p className="text-sm text-slate-500 leading-relaxed flex-1">
            {stringValue(objectValue(llmProfile.repayment_willingness).logic_basis, '暂无明确判断依据')}
          </p>
        </article>

        <article className="flex flex-col rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4">产品意愿</div>
          <div className="flex flex-col gap-2">
            <div className="flex justify-between items-center">
              <span className="text-base font-semibold text-slate-700">提额意愿</span>
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                stringValue(objectValue(llmProfile.product_intent).upgrade_intent, '未知') === '高'
                  ? 'bg-blue-50 text-blue-600'
                  : 'bg-slate-100 text-slate-500'
              }`}>
                {stringValue(objectValue(llmProfile.product_intent).upgrade_intent, '未知')}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-base font-semibold text-slate-700">续贷意愿</span>
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                stringValue(objectValue(llmProfile.product_intent).reloan_intent, '未知') === '高'
                  ? 'bg-blue-50 text-blue-600'
                  : 'bg-slate-100 text-slate-500'
              }`}>
                {stringValue(objectValue(llmProfile.product_intent).reloan_intent, '未知')}
              </span>
            </div>
          </div>
          <hr className="my-5 border-dashed border-slate-200" />
          <p className="text-sm text-slate-500 leading-relaxed flex-1">
            {stringValue(objectValue(llmProfile.product_intent).logic_basis, '暂无明确判断依据')}
          </p>
        </article>

        <article className="flex flex-col rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm relative overflow-hidden">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4">流失风险</div>
          <div className="flex items-baseline gap-3">
            <span className={`text-[28px] font-bold ${
              stringValue(objectValue(llmProfile.churn_risk).level, '未知') === '高'
                ? 'text-red-600'
                : 'text-emerald-600'
            }`}>
              {stringValue(objectValue(llmProfile.churn_risk).level, '未知')}
            </span>
            <span className="text-sm font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
              趋势{stringValue(objectValue(llmProfile.churn_risk).active_trend, '未知')}
            </span>
          </div>
          {stringValue(objectValue(llmProfile.churn_risk).last_active_days_ago, '') && (
            <div className="absolute top-6 right-6 text-xs font-semibold text-slate-400 flex items-center gap-1">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {stringValue(objectValue(llmProfile.churn_risk).last_active_days_ago, '')}
            </div>
          )}
          <hr className="my-5 border-dashed border-slate-200" />
          <p className="text-sm text-slate-500 leading-relaxed flex-1">
            {stringValue(objectValue(llmProfile.churn_risk).last_active_context, '暂无明确流失说明')}
          </p>
        </article>

        <article className="flex flex-col rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm bg-gradient-to-br from-white to-slate-50">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4">最优触达策略</div>
          <div className="space-y-3">
            <div>
              <div className="text-xs text-slate-400 mb-1">首选渠道</div>
              <div className="text-xl font-bold text-blue-600">
                {stringValue(objectValue(llmProfile.contact_preference).best_channel, '未知')}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-xs text-slate-400 mb-1">黄金时段</div>
                <div className="text-sm font-semibold text-slate-700">
                  {stringValue(objectValue(llmProfile.contact_preference).best_time, '未知')}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-400 mb-1">Push 打开率估算</div>
                <div className="text-sm font-semibold text-slate-700">
                  {stringValue(objectValue(llmProfile.contact_preference).push_open_rate, 'N/A')}
                </div>
              </div>
            </div>
          </div>
          <hr className="my-4 border-dashed border-slate-200" />
          <p className="text-xs text-slate-400 leading-relaxed mt-auto">
            {stringValue(objectValue(llmProfile.contact_preference).reason, '基于用户底层埋点（权限授权、表单交互、回流节奏）综合推算。')}
          </p>
        </article>
      </section>

      <section className="rounded-[32px] bg-blue-50/70 p-6 md:p-8 border border-blue-100/50 shadow-sm flex flex-col md:flex-row gap-6 items-start">
        <div className="shrink-0 flex items-center justify-center h-14 w-14 rounded-2xl bg-blue-600 text-white shadow-md">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <div className="flex-1">
          <div>
            <h3 className="text-lg font-bold text-slate-800">全景行为画像</h3>
            <p className="mt-3 text-base text-slate-700 leading-8">
              {narrativeSummary}
            </p>
          </div>

          <div className="mt-6 pt-6 border-t border-dashed border-blue-200/70">
            <h3 className="text-lg font-bold text-slate-800">经营干预建议 (Next Action)</h3>
            {businessAdviceItems.length ? (
              <ol className="mt-3 space-y-2 text-base text-slate-700 leading-8 list-decimal pl-6">
                {businessAdviceItems.map((item, index) => (
                  <li key={`${index}-${item.slice(0, 12)}`}>{item.replace(/^\d+[\.|?]?\s*/, '')}</li>
                ))}
              </ol>
            ) : (
              <p className="mt-3 text-base text-slate-700 leading-8">暂无经营建议</p>
            )}
          </div>
          {journeyInsight && (
            <p className="mt-4 text-xs text-slate-500">
              Journey Insight: {journeyInsight}
            </p>
          )}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-[320px_1fr]">
        <aside className="rounded-[34px] border border-slate-200 bg-white p-6 shadow-sm xl:sticky xl:top-6 xl:max-h-[86vh] xl:overflow-y-auto">
          <h3 className="text-base font-bold text-slate-800 mb-5">页面流转大纲</h3>
          <div className="space-y-3">
            {timelineSectionsCompact.map((section) => (
              <button
                key={stringValue(section.id, '')}
                type="button"
                onClick={() => scrollToSection(stringValue(section.id, ''))}
                className="w-full rounded-[20px] border border-slate-100 bg-slate-50 px-4 py-4 text-left transition hover:bg-blue-50 hover:border-blue-200 group"
              >
                <div className="flex items-center gap-2 text-sm font-bold text-slate-700 group-hover:text-blue-700">
                  <span className="h-2 w-2 rounded-full bg-blue-400"></span>
                  <span className="truncate">{stringValue(section.title, '当前阶段')}</span>
                </div>
                <p className="mt-1.5 text-xs text-slate-400 pl-4">
                  压缩 {compactEventCount(section)} 条 / 原始 {rawEventCount(section)} 条
                </p>
                <p className="mt-1.5 text-xs text-blue-500 pl-4 line-clamp-2">
                  {buildSectionSummary(section, objectValue(narrativeBySection[stringValue(section.id, '')]))}
                </p>
              </button>
            ))}
          </div>
        </aside>

        <main className="space-y-6">
          {timelineSectionsCompact.map((section, sectionIndex) => {
            const sectionId = stringValue(section.id, '');
            const sectionNarrative = objectValue(narrativeBySection[sectionId]);
            const sectionEvents = arrayValue(section.events);
            const displayEvents = sectionEvents.slice(0, 8);
            const hiddenEventCount = Math.max(0, sectionEvents.length - displayEvents.length);
            return (
              <article
                key={sectionId}
                id={sectionId}
                className="rounded-[34px] border border-slate-200 bg-white p-6 shadow-sm md:p-8"
              >
                <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-6">
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-sm font-bold text-blue-600">
                      {sectionIndex + 1}
                    </div>
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">页面节点</p>
                      <h3 className="mt-1 text-xl font-bold tracking-tight text-slate-800">
                        {stringValue(section.title, '当前阶段')}
                      </h3>
                      <p className="mt-2 text-sm text-slate-500 leading-relaxed max-w-xl">
                        {buildSectionSummary(section, sectionNarrative)}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 justify-end">
                    <span className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-600 border border-amber-200">
                      耗时提示: {normalizeTimeLabel(stringValue(section.duration_hint, ''))}
                    </span>
                    {stringValue(sectionNarrative.stage_label, '') && (
                      <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-bold text-blue-600 border border-blue-200">
                        {stringValue(sectionNarrative.stage_label, '')}
                      </span>
                    )}
                    {stringValue(sectionNarrative.friction_label, '') && (
                      <span className="rounded-full bg-rose-50 px-3 py-1.5 text-xs font-bold text-rose-600 border border-rose-200">
                        {stringValue(sectionNarrative.friction_label, '')}
                      </span>
                    )}
                  </div>
                </header>

                {(stringValue(sectionNarrative.narrative, '') || stringValue(sectionNarrative.turning_point, '') || stringValue(sectionNarrative.warning_summary, '') || stringValue(sectionNarrative.pause_summary, '')) && (
                  <div className="mb-6 rounded-[24px] border border-blue-100 bg-blue-50/60 p-5">
                    {stringValue(sectionNarrative.narrative, '') && (
                      <p className="text-sm leading-7 text-slate-700">{stringValue(sectionNarrative.narrative, '')}</p>
                    )}
                    {stringValue(sectionNarrative.turning_point, '') && (
                      <p className="mt-3 text-xs font-semibold text-blue-700">关键转折：{stringValue(sectionNarrative.turning_point, '')}</p>
                    )}
                    {stringValue(sectionNarrative.warning_summary, '') && (
                      <p className="mt-2 text-xs font-semibold text-red-600">异常归因：{stringValue(sectionNarrative.warning_summary, '')}</p>
                    )}
                    {stringValue(sectionNarrative.pause_summary, '') && (
                      <p className="mt-2 text-xs font-semibold text-amber-600">停顿说明：{stringValue(sectionNarrative.pause_summary, '')}</p>
                    )}
                  </div>
                )}

                <div className="space-y-4">
                  {displayEvents.map((event, eventIndex) => (
                    <div
                      key={`${sectionId}-${eventIndex}-${stringValue(event?.action, '')}`}
                      className={`rounded-[24px] border px-6 py-5 ${
                        Boolean(event?.is_warning)
                          ? 'border-red-100 bg-red-50/40'
                          : 'border-slate-100 bg-slate-50/70'
                      }`}
                    >
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
                            <span className="font-semibold text-slate-500">{normalizeTimeLabel(stringValue(event?.time, ''))}</span>
                            {stringValue(event?.kind, '') === 'macro_event' && (
                              <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-bold text-blue-600 border border-blue-200">压缩动作</span>
                            )}
                            {Boolean(event?.is_warning) && (
                              <span className="rounded-full bg-red-50 px-2.5 py-1 text-[11px] font-bold text-red-600 border border-red-200">异常卡点</span>
                            )}
                          </div>
                          <div className="mt-2 text-[28px] font-bold tracking-tight text-slate-800 break-words">
                            {stringValue(event?.action, '未命名动作')}
                          </div>
                          {stringValue(event?.note, '') && (
                            <p className="mt-2 text-sm leading-6 text-slate-500">{stringValue(event?.note, '')}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {hiddenEventCount > 0 && (
                  <div className="mt-4 rounded-[20px] border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
                    当前阶段还有 {hiddenEventCount} 条压缩动作未展开，已优先展示对归因更关键的动作。
                  </div>
                )}
              </article>
            );
          })}
        </main>
      </section>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.BehaviorPanel = BehaviorPanel;
