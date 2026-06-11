// Extracted from app/ui/live_frontend.py during UI separation Step-1.

const { useState } = React;
const { Smartphone, Database, Search, TrendingUp, MousePointerClick, PieChart, BrainCircuit } = window.LucideReact || {};
const { arrayValue, objectValue, stringValue, numberValue } = window.AppUtils.normalize;
const { findChart, chartSeriesData, findPrimaryCategoryIndex } = window.AppUtils.chartLookup;
const {
  tokenToBgClass,
  colorByIndex,
  softTagToneClass,
  formatInlineList,
  riskBadgeClass,
  toRiskLabel,
  toFinancialDisplayLabel,
  toConsumptionDisplayLabel,
  normalizeMetricKey,
} = window.AppUtils.displayMappers;
const {
  InteractiveDonutChart,
  LegendDot,
  MetricHelpTip,
  MarkdownBlock,
  TimelineItem,
  InstallBucketModal,
  CategoryAppsModal,
} = window.AppComponents;

function iconByName(iconName) {
  const mapping = {
    Smartphone,
    Database,
    Search,
    TrendingUp,
    MousePointerClick,
    PieChart
  };
  return mapping[iconName] || Database;
}

function AppPanel({ profile }) {
  const [hoveredCategoryIndex, setHoveredCategoryIndex] = useState(null);
  const [pinnedCategoryIndex, setPinnedCategoryIndex] = useState(null);
  const [hoveredHelpKey, setHoveredHelpKey] = useState('');
  const [pinnedHelpKey, setPinnedHelpKey] = useState('');
  const [selectedBucket, setSelectedBucket] = useState('');
  const [showCategoryDetail, setShowCategoryDetail] = useState(false);
  const structured = profile?.structured_result || {};
  const metrics = objectValue(structured.metrics);
  const evidence = objectValue(structured.evidence);
  const charts = arrayValue(profile?.charts);
  const categoryChart = findChart(charts, 'Installed Apps Category Share');
  const installChart = findChart(charts, 'Install Time Distribution');
  const signalChart = findChart(charts, 'Risk / Maturity / Consumption Signals');
  const visuals = objectValue(structured.visuals);
  const riskAssessment = objectValue(structured.risk_assessment);
  const financialMaturity = objectValue(structured.financial_maturity);
  const consumptionProfile = objectValue(structured.consumption_profile);
  const appInsight = objectValue(structured.app_insight);
  const modelTrace = objectValue(structured.model_trace);
  const categorySeries = arrayValue(arrayValue(categoryChart?.series)[0]?.data);
  const installBuckets = arrayValue(installChart?.x_axis);
  const installValues = chartSeriesData(installChart);
  const installBucketDetails = objectValue(evidence.install_bucket_details);
  const categoryAppDetails = objectValue(evidence.category_app_details);
  const progressMetrics = arrayValue(visuals.progress_metrics).length
    ? arrayValue(visuals.progress_metrics)
    : arrayValue(arrayValue(signalChart?.series)[0]?.data);
  const progressMetricExplanations = arrayValue(visuals.progress_metric_explanations);
  const explanationMap = progressMetricExplanations.reduce((accumulator, item) => {
    const key = stringValue(item?.key, normalizeMetricKey(item?.label));
    if (key) accumulator[key] = item;
    return accumulator;
  }, {});
  const timelineItems = arrayValue(structured.timeline);
  const tags = arrayValue(appInsight.labels).length ? arrayValue(appInsight.labels) : arrayValue(structured.tags);
  const installedCount = numberValue(metrics.installed_app_count, numberValue(visuals.installed_app_count, 0));
  const topCategory = stringValue(metrics.top_category, stringValue(visuals.top_category, 'unknown'));
  const activityLevel = stringValue(structured.activity_level, 'unknown');
  const summary = stringValue(profile.summary, 'No app profile result');
  const mainPreferenceShare = numberValue(objectValue(categoryChart?.meta).main_preference_share, numberValue(visuals.main_preference_share, 0));
  const recentInstallCount30d = numberValue(metrics.recent_install_count_30d, numberValue(visuals.recent_install_count_30d, 0));
  const riskLevel = stringValue(riskAssessment.level, stringValue(metrics.multi_loan_risk_level, 'unknown'));
  const financialLevel = stringValue(financialMaturity.level, stringValue(metrics.financial_maturity_level, 'unknown'));
  const consumptionLevel = stringValue(consumptionProfile.level, stringValue(metrics.consumption_ability_level, 'unknown'));
  const palette = arrayValue(objectValue(categoryChart?.meta).palette);
  const defaultCategoryIndex = findPrimaryCategoryIndex(categorySeries);
  const activeCategoryIndex = pinnedCategoryIndex !== null ? pinnedCategoryIndex : hoveredCategoryIndex !== null ? hoveredCategoryIndex : defaultCategoryIndex;
  const activeCategory = categorySeries[activeCategoryIndex] || null;
  const activeCategoryLabel = activeCategory ? stringValue(activeCategory.label, '其他-待归类') : '';
  const activeCategoryDetail = objectValue(categoryAppDetails[activeCategoryLabel]);
  const activeCategoryApps = arrayValue(activeCategoryDetail.apps);
  const activeHelpKey = pinnedHelpKey || hoveredHelpKey;
  const selectedBucketGroups = arrayValue(installBucketDetails[selectedBucket]);
  const llmStatusLabel = modelTrace.used_llm ? 'LLM 推理完成' : '规则降级结果';
  const llmStatusClass = modelTrace.used_llm ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200';
  const insightSummary = stringValue(appInsight.summary, summary);
  const insightReasons = arrayValue(appInsight.reasons);
  const predictionCards = [
    { title: '借贷风险等级', value: toRiskLabel(riskLevel), accentClass: 'text-amber-300', apps: arrayValue(riskAssessment.recent_30d_lending_apps), typeText: '同类应用多为竞品借贷 / 现金贷工具', reason: stringValue(riskAssessment.reasoning, insightReasons[0] || `近30天新增 ${arrayValue(riskAssessment.recent_30d_lending_apps).length} 个借贷相关 App，因此当前借贷风险信号为 ${toRiskLabel(riskLevel)}。`) },
    { title: '金融成熟度', value: toFinancialDisplayLabel(financialLevel), accentClass: 'text-cyan-300', apps: arrayValue(financialMaturity.supporting_apps), typeText: '代表应用通常覆盖银行、钱包、政府服务等金融基础设施', reason: stringValue(financialMaturity.reasoning, insightReasons[1] || `该判断综合银行 / 钱包 / 政务应用安装情况，支持当前“${toFinancialDisplayLabel(financialLevel)}”结论。`) },
    { title: '消费能力', value: toConsumptionDisplayLabel(consumptionLevel), accentClass: 'text-fuchsia-300', apps: arrayValue(consumptionProfile.preferred_categories), typeText: '重点关注出行、外卖、电商等消费相关类型', reason: stringValue(consumptionProfile.reasoning, insightReasons[2] || `主要依据消费相关 App 类型偏好与安装覆盖度，判断当前消费能力为“${toConsumptionDisplayLabel(consumptionLevel)}”。`) },
  ];
  return (
    <div className="animate-in fade-in duration-500">
      <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100"><Smartphone className="w-8 h-8 text-blue-500" /><h2 className="text-2xl font-bold text-slate-800">Skill 1: App画像 Agent</h2></div>
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        <div className="col-span-1 md:col-span-8 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gradient-to-br from-blue-50 to-cyan-50 p-5 rounded-2xl border border-blue-100 flex items-center gap-4"><div className="w-12 h-12 bg-blue-500 rounded-full flex items-center justify-center text-white shadow-lg shadow-blue-500/30"><Smartphone className="w-6 h-6" /></div><div><p className="text-sm text-blue-600/80 font-medium mb-0.5">安装 App 数量</p><p className="text-2xl font-bold text-slate-800">{installedCount} <span className="text-sm font-normal text-slate-500">apps</span></p></div></div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200 flex items-center gap-4 shadow-sm"><div className="w-12 h-12 bg-cyan-100 rounded-full flex items-center justify-center text-cyan-600"><Database className="w-6 h-6" /></div><div><p className="text-sm text-slate-500 font-medium mb-0.5">Top Category</p><p className="text-2xl font-bold text-slate-800">{topCategory}</p></div></div>
            <div className="bg-white p-5 rounded-2xl border border-slate-200 flex items-center gap-4 shadow-sm"><div className="w-12 h-12 bg-amber-100 rounded-full flex items-center justify-center text-amber-600"><TrendingUp className="w-6 h-6" /></div><div><p className="text-sm text-slate-500 font-medium mb-0.5">Multi-loan Risk</p><p className="text-2xl font-bold text-slate-800">{riskLevel}</p></div></div>
          </div>
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
            <h3 className="text-base font-bold text-slate-800 mb-6 flex items-center justify-between"><div className="flex items-center gap-2"><PieChart className="w-5 h-5 text-slate-400" />App 偏好分布与安装洞察</div><span className="text-xs font-normal text-slate-500 bg-slate-100 px-2 py-1 rounded-md">应用画像模型</span></h3>
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)] gap-8 items-start">
              <div className="space-y-5">
                <div className="flex flex-col items-center"><InteractiveDonutChart items={categorySeries} palette={palette} activeIndex={activeCategoryIndex} size={240} onHover={setHoveredCategoryIndex} onLeave={() => setHoveredCategoryIndex(null)} onSelect={(index) => setPinnedCategoryIndex(index === pinnedCategoryIndex ? null : index)} /></div>
                <div className="rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-blue-50/60 px-5 py-4 shadow-sm"><div className="flex items-start justify-between gap-4"><div><div className="text-xs text-slate-500 mb-1">当前选中类别</div><div className="text-xl font-bold text-slate-800">{activeCategory ? stringValue(activeCategory.label, '其他-待归类') : '暂无分类数据'}</div><div className="text-sm text-slate-600 mt-2">{activeCategory ? `${numberValue(activeCategory.value, 0)} 个 App，占比 ${numberValue(activeCategory.share, 0)}%。` : `主偏好占比 ${mainPreferenceShare}%。`}</div></div><button type="button" disabled={!activeCategoryApps.length} onClick={() => activeCategoryApps.length && setShowCategoryDetail(true)} className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${activeCategoryApps.length ? 'border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100' : 'border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed'}`}>{activeCategoryApps.length ? '(查看该类App)' : '(暂无明细)'}</button></div></div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-3 text-sm w-full">{categorySeries.length ? categorySeries.map((item, index) => (<button key={`${item.label || 'category'}-${index}`} type="button" className={`text-left rounded-2xl border px-4 py-3 transition-all ${activeCategoryIndex === index ? 'border-blue-300 bg-blue-50 shadow-sm' : 'border-slate-200 bg-white hover:bg-slate-50'}`} onMouseEnter={() => setHoveredCategoryIndex(index)} onMouseLeave={() => setHoveredCategoryIndex(null)} onClick={() => setPinnedCategoryIndex(index === pinnedCategoryIndex ? null : index)}><LegendDot color={tokenToBgClass(stringValue(item.color_token, colorByIndex(index)))} label={`${stringValue(item.label, 'Unknown')} (${numberValue(item.share, 0)}%)`} /></button>)) : <LegendDot color="bg-blue-500" label={`${topCategory} (${mainPreferenceShare}%)`} />}</div>
              </div>
              <div className="space-y-5">
                <div className="rounded-3xl border border-slate-200 bg-slate-50/80 p-5"><div className="grid grid-cols-1 gap-5">{progressMetrics.map((item, index) => { const metricKey = normalizeMetricKey(item.label); return (<div key={item.label} className="relative"><div className="flex justify-between items-end mb-2 gap-4"><div className="flex items-center gap-2"><span className="text-sm font-medium text-slate-700">{stringValue(item.label, `Metric ${index + 1}`)}</span><MetricHelpTip explanation={objectValue(explanationMap[metricKey])} isOpen={activeHelpKey === metricKey} onMouseEnter={() => setHoveredHelpKey(metricKey)} onMouseLeave={() => setHoveredHelpKey('')} onToggle={() => setPinnedHelpKey(activeHelpKey === metricKey ? '' : metricKey)} /></div><span className={riskBadgeClass(stringValue(item.risk_level, 'safe'))}>{stringValue(item.text, '')}</span></div><div className="w-full bg-slate-100 rounded-full h-1.5 flex items-center"><div className={`${tokenToBgClass(stringValue(item.color_token, 'blue'))} h-1.5 rounded-full transition-all duration-1000`} style={{ width: `${numberValue(item.value, 0)}%` }}></div><span className="text-xs text-slate-400 ml-3">{numberValue(item.value, 0)}</span></div></div>); })}</div></div>
                <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between gap-3 mb-4"><div><h4 className="text-base font-bold text-slate-800">用户核心标签</h4><p className="text-xs text-slate-500 mt-1">将核心偏好与风险判断一起展示，减少空白并提升可读性。</p></div><span className="text-xs text-slate-400">标签画像</span></div><div className="flex flex-wrap gap-3">{tags.length ? tags.map((tag, index) => (<span key={tag} className={`px-3.5 py-2 rounded-full text-sm font-medium border ${softTagToneClass(index)}`}>{tag}</span>)) : <span className="text-sm text-slate-400">暂无标签</span>}</div></div>
              </div>
            </div>
          </div>
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm"><h3 className="text-base font-bold text-slate-800 mb-6 flex items-center gap-2"><TrendingUp className="w-5 h-5 text-slate-400" />安装时间分布</h3><div className="space-y-4">{installBuckets.map((bucket, index) => { const value = installValues[index] || 0; const width = installedCount ? Math.max(8, Math.round((value / installedCount) * 100)) : 0; const clickable = value > 0; return (<button key={`${bucket}-${index}`} type="button" disabled={!clickable} onClick={() => clickable && setSelectedBucket(bucket)} className={`w-full text-left rounded-2xl border px-4 py-3 transition-colors ${clickable ? 'border-slate-200 hover:bg-slate-50' : 'border-slate-100 bg-slate-50/70 cursor-default'}`}><div className="flex justify-between text-sm mb-1 text-slate-600"><span>{bucket}</span><span className="font-semibold text-slate-800">{value}</span></div><div className="w-full bg-slate-100 rounded-full h-2"><div className={`${tokenToBgClass(colorByIndex(index))} h-2 rounded-full`} style={{ width: `${width}%` }}></div></div><div className="text-xs text-slate-400 mt-2">{clickable ? '点击查看该时间段的安装明细' : '当前时间段暂无安装 App'}</div></button>); })}</div></div>
        </div>
        <div className="col-span-1 md:col-span-4 space-y-6">
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm h-auto relative overflow-hidden"><div className="absolute top-0 right-0 w-20 h-20 bg-blue-50 rounded-bl-full z-0"></div><div className="relative z-10"><div className="flex justify-between items-center mb-6"><h3 className="text-base font-bold text-slate-800">App 画像轨迹</h3><span className="text-xs font-medium bg-slate-100 text-slate-600 px-2 py-1 rounded">Today</span></div><div className="mt-4">{timelineItems.map((item, index) => (<TimelineItem key={`${stringValue(item.time, 'item')}-${index}`} time={stringValue(item.time, 'N/A')} title={stringValue(item.title, 'Timeline')} sub={stringValue(item.sub, '')} icon={iconByName(stringValue(item.icon, 'Database'))} color={tokenToBgClass(stringValue(item.color_token, 'slate'))} isLast={index === timelineItems.length - 1} />))}</div></div></div>
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl shadow-lg relative overflow-hidden group min-h-[480px]"><div className="absolute -right-4 -top-4 w-24 h-24 bg-blue-500/20 rounded-full blur-xl group-hover:bg-blue-500/30 transition-all"></div><BrainCircuit className="absolute -bottom-2 -right-2 w-20 h-20 text-slate-700/50" /><h3 className="text-base font-bold text-white mb-3 relative z-10">Next App Predictions</h3><div className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium mb-4 relative z-10 ${llmStatusClass}`}>{llmStatusLabel}</div><div className="flex items-center justify-between bg-slate-800/80 p-4 rounded-xl border border-slate-700/50 mb-4 relative z-10 backdrop-blur-sm gap-4"><div><p className="text-xs text-slate-400 mb-1">Financial Maturity</p><p className="text-[28px] font-bold text-cyan-400 flex items-center gap-1">{toFinancialDisplayLabel(financialLevel)}<TrendingUp className="w-5 h-5 text-cyan-400" /></p></div><div className="text-right"><p className="text-xs text-slate-400 mb-1">Consumption Level</p><p className="text-base font-bold text-white">{toConsumptionDisplayLabel(consumptionLevel)}</p></div></div><div className="relative z-10 rounded-2xl border border-slate-700/70 bg-slate-800/60 px-4 py-4"><p className="text-sm text-slate-100 leading-6">{insightSummary}</p><p className="text-xs text-slate-400 mt-3">近30天新增 {recentInstallCount30d} 个 App，活跃度 {activityLevel}。</p></div><div className="mt-4 space-y-3 relative z-10">{predictionCards.map((item) => (<div key={item.title} className="rounded-2xl border border-slate-700/70 bg-slate-800/70 px-4 py-3"><div className="flex items-center justify-between gap-3"><span className="text-xs uppercase tracking-[0.18em] text-slate-400">{item.title}</span><span className={`text-sm font-semibold ${item.accentClass}`}>{item.value}</span></div><div className="text-xs text-slate-200 mt-2 leading-5">代表对象：{formatInlineList(item.apps, '暂无明显代表应用')}</div><div className="text-xs text-slate-400 mt-2 leading-5">{item.typeText}</div><div className="text-xs text-slate-300 mt-2 leading-5">{item.reason}</div></div>))}</div></div>
        </div>
      </div>
      <div className="mt-6 bg-white p-8 rounded-2xl border border-slate-200 shadow-sm"><div className="flex items-center justify-between gap-4 mb-6 flex-wrap"><h3 className="text-xl font-bold text-slate-800">大模型分析报告</h3><span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${llmStatusClass}`}>{llmStatusLabel}</span></div><MarkdownBlock text={stringValue(profile.report_markdown, summary)} /></div>
      <InstallBucketModal bucket={selectedBucket} groups={selectedBucketGroups} onClose={() => setSelectedBucket('')} />
      <CategoryAppsModal category={activeCategoryLabel} detail={activeCategoryDetail} onClose={() => setShowCategoryDetail(false)} open={showCategoryDetail} />
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.AppPanel = AppPanel;
