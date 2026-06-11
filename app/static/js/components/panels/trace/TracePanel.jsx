// Trace UI / TracePanel — orchestrator with two-layer status branching.
// Renders the trace tab content based on (requestStatus, response.status).
// Locked decisions: Activity icon (Design Doc §3.1), no_clear_signal not
// rendered in ChurnRootCauseBar (§11), KeyEventsTimeline default folded.

const { Activity, AlertTriangle, RefreshCw } = window.LucideReact;
const {
  ChurnStoryCard,
  PathGraphCard,
  TimePatternCard,
  FrictionHotspotGrid,
  InterventionList,
  KeyEventsTimeline,
} = window.AppComponents;

// Kept in sync with app/static/js/components/panels/OpsAdvicePanel.jsx churnRootCauseLabels
// (lines 67-74 there). OpsAdvicePanel itself is not modified — invariant 0.3.
const churnRootCauseLabels = {
  credit_limit_unmet: '额度不及预期',
  interest_perception_high: '利息感知过高',
  competitor_poaching: '竞品挖角',
  ux_friction: '操作体验差',
  repayment_burden: '还款压力大',
  no_clear_signal: '无明确信号',
};

const STATUS_BADGE_CLASS = {
  ok: 'bg-emerald-100 text-emerald-700',
  model_unavailable: 'bg-amber-100 text-amber-700',
  insufficient_events: 'bg-slate-100 text-slate-600',
  data_missing: 'bg-slate-100 text-slate-600',
  error: 'bg-red-100 text-red-700',
};

function Skeleton() {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
      <div className="flex items-center gap-2 mb-4">
        <Activity className="w-5 h-5 text-violet-500" />
        <h3 className="text-base font-semibold text-slate-800">深度行为解析</h3>
      </div>
      <div className="animate-pulse space-y-3">
        <div className="h-4 bg-slate-100 rounded w-1/2" />
        <div className="h-4 bg-slate-100 rounded w-3/4" />
        <div className="h-32 bg-slate-100 rounded" />
        <div className="h-4 bg-slate-100 rounded w-2/3" />
      </div>
      <div className="mt-3 text-xs text-slate-400">正在解析行为序列...</div>
    </div>
  );
}

function ErrorCard({ message, onRetry }) {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm border border-red-200">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-5 h-5 text-red-500" />
        <h3 className="text-base font-semibold text-red-700">无法加载深度行为解析</h3>
      </div>
      <div className="text-sm text-slate-600 mb-4">
        {message || '请求失败，请稍后再试。'}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-300"
        >
          <RefreshCw className="w-4 h-4" />
          重试
        </button>
      )}
    </div>
  );
}

function EmptyState({ title, hint, errors }) {
  const errs = Array.isArray(errors) ? errors : [];
  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="w-5 h-5 text-slate-400" />
        <h3 className="text-base font-semibold text-slate-700">{title}</h3>
      </div>
      {hint && <div className="text-sm text-slate-500">{hint}</div>}
      {errs.length > 0 && (
        <ul className="mt-3 list-disc pl-5 text-xs text-slate-400 space-y-1">
          {errs.map((e, idx) => (
            <li key={idx}>{String(e)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ChurnRootCauseBar({ causes }) {
  const filtered = (Array.isArray(causes) ? causes : []).filter(
    (c) => c && c !== 'no_clear_signal'
  );
  if (filtered.length === 0) return null;
  return (
    <div className="rounded-2xl border border-violet-100 bg-violet-50 p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-violet-700 mb-2">
        流失归因
      </div>
      <div className="flex flex-wrap gap-2">
        {filtered.map((c, idx) => (
          <span
            key={idx}
            className="inline-flex items-center rounded-full bg-white px-3 py-1 text-xs font-medium text-violet-700 border border-violet-200"
          >
            {churnRootCauseLabels[c] || c}
          </span>
        ))}
      </div>
    </div>
  );
}

function HeaderBlock({ status, response }) {
  const ew = (response && response.event_window) || {};
  const totalEvents = response && (response.total_events ?? ew.total_events);
  const analyzedEvents = response && (response.analyzed_events ?? ew.analyzed_events);
  const badgeClass = STATUS_BADGE_CLASS[status] || 'bg-slate-100 text-slate-600';
  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-200">
      <div className="flex flex-wrap items-center gap-3">
        <Activity className="w-5 h-5 text-violet-500" />
        <h3 className="text-base font-semibold text-slate-800">深度行为解析</h3>
        <span className={'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ' + badgeClass}>
          {status || 'unknown'}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-slate-600">
        <div>
          <div className="text-slate-400">起始</div>
          <div className="font-mono text-slate-700 truncate">{ew.start || '-'}</div>
        </div>
        <div>
          <div className="text-slate-400">结束</div>
          <div className="font-mono text-slate-700 truncate">{ew.end || '-'}</div>
        </div>
        <div>
          <div className="text-slate-400">总事件</div>
          <div className="text-slate-700">{totalEvents ?? '-'}</div>
        </div>
        <div>
          <div className="text-slate-400">已分析</div>
          <div className="text-slate-700">{analyzedEvents ?? '-'}</div>
        </div>
      </div>
    </div>
  );
}

function ModelTraceFooter({ modelTrace }) {
  if (!modelTrace) return null;
  const mode = modelTrace.mode || '-';
  const usedLlm = modelTrace.used_llm === true ? 'true' : 'false';
  const modelName = modelTrace.model_name || '-';
  const fallback = modelTrace.fallback_reason || '';
  return (
    <div className="text-xs text-slate-400">
      mode: {mode} · used_llm: {usedLlm} · model: {modelName}
      {fallback ? ' · fallback: ' + fallback : ''}
    </div>
  );
}

function FullPanel({ response }) {
  const status = response && response.status;
  const isFallbackBanner = status === 'model_unavailable';
  return (
    <div className="space-y-4">
      <HeaderBlock status={status} response={response} />
      {isFallbackBanner && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          规则产物完整，叙述为模板兜底
        </div>
      )}
      <ChurnRootCauseBar causes={response && response.churn_root_cause} />
      <ChurnStoryCard
        story={response && response.churn_story}
        modelTrace={response && response.model_trace}
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <PathGraphCard pathGraph={response && response.path_graph} />
        <TimePatternCard timePattern={response && response.time_pattern} />
      </div>
      <FrictionHotspotGrid hotspots={response && response.friction_hotspots} />
      <InterventionList suggestions={response && response.intervention_suggestions} />
      <KeyEventsTimeline events={response && response.key_events_tail} />
      <ModelTraceFooter modelTrace={response && response.model_trace} />
    </div>
  );
}

function TracePanel({ uid, cacheEntry, onRetry }) {
  if (!cacheEntry || cacheEntry.requestStatus === 'idle') return null;

  if (cacheEntry.requestStatus === 'loading') {
    return <Skeleton />;
  }

  if (cacheEntry.requestStatus === 'error') {
    return <ErrorCard message={cacheEntry.errorMessage} onRetry={onRetry} />;
  }

  const response = cacheEntry.response || {};
  const status = response.status;

  if (status === 'data_missing') {
    return (
      <EmptyState
        title="深度行为解析"
        hint={'未找到该 uid 的行为数据：' + (uid || '-')}
      />
    );
  }
  if (status === 'insufficient_events') {
    return (
      <EmptyState
        title="深度行为解析"
        hint="该用户事件数过少，无法生成深度解析"
        errors={response.errors}
      />
    );
  }
  if (status === 'error') {
    return (
      <EmptyState
        title="深度行为解析（业务错误）"
        hint="后端返回业务错误，已展示可获取部分。"
        errors={response.errors}
      />
    );
  }

  return <FullPanel response={response} />;
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.TracePanel = TracePanel;
