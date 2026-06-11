function ChatExecutionTraceCard({ trace, runStatus }) {
  if (!trace) return null;
  const requestUnderstanding = trace.request_understanding || null;
  const availability = trace.availability || null;
  const steps = Array.isArray(trace.steps) ? trace.steps : [];
  const visibleSteps = steps.filter((step) => (
    step && ['running', 'done', 'failed', 'blocked', 'awaiting_resolution'].includes(step.status || 'pending')
  ));
  const pendingSteps = steps.filter((step) => step && !visibleSteps.includes(step));
  const review = trace.review || null;
  const perUid = Array.isArray(availability && availability.per_uid) ? availability.per_uid : [];
  const routeLabel = (requestUnderstanding && requestUnderstanding.route_label) || _intentLabel(trace.intent);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">执行轨迹</div>
          <div className="mt-1 text-sm font-semibold text-slate-800">{trace.request_summary || '当前请求'}</div>
        </div>
        {routeLabel ? (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">
            {routeLabel}
          </span>
        ) : null}
      </div>

      {requestUnderstanding ? (
        <div className="mt-4 space-y-3">
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
            <div className="text-xs font-semibold text-slate-500">需求理解</div>
            <div className="mt-1 text-sm font-medium leading-6 text-slate-700">
              {requestUnderstanding.rewritten_goal || trace.request_summary || '当前请求'}
            </div>
            {Array.isArray(requestUnderstanding.focus) && requestUnderstanding.focus.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {requestUnderstanding.focus.map((focusItem) => (
                  <span key={focusItem} className="rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-slate-500">
                    {focusItem}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
            <div className="text-xs font-semibold text-slate-500">路径说明</div>
            <div className="mt-1 text-sm leading-6 text-slate-700">
              {requestUnderstanding.route_reason || '当前请求将按既定执行路径继续。'}
            </div>
          </div>
        </div>
      ) : null}

      {perUid.length > 0 ? (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-slate-500">数据完整性检查</div>
          {perUid.map((row) => (
            <div key={row.uid} className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
              <div className="font-mono text-[11px] text-slate-500">{row.uid}</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {['app', 'behavior', 'credit'].map((bucket) => {
                  const item = row[bucket] || {};
                  const ok = item.available;
                  return (
                    <span
                      key={`${row.uid}-${bucket}`}
                      className={`rounded-full px-2 py-1 font-semibold ${ok ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}
                    >
                      {bucket}: {item.status || 'unknown'}
                    </span>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {steps.length > 0 ? (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold text-slate-500">执行计划</div>
          {visibleSteps.map((step) => {
            const status = step.status || 'pending';
            const color = status === 'done'
              ? 'bg-emerald-50 text-emerald-700'
              : status === 'failed' || status === 'blocked'
                ? 'bg-rose-50 text-rose-700'
                : status === 'running'
                  ? 'bg-blue-50 text-blue-700'
                  : 'bg-slate-100 text-slate-600';
            return (
              <div key={step.step_id} className="rounded-xl border border-slate-100 px-3 py-2 transition-all duration-300 ease-out animate-[fadeIn_0.24s_ease-out]">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-slate-700">{step.title || step.step_id}</div>
                  <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${color}`}>{status}</span>
                </div>
                {step.user_visible_reason ? (
                  <div className="mt-2">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">为什么这样做</div>
                    <div className="mt-1 text-xs leading-5 text-slate-500">{step.user_visible_reason}</div>
                  </div>
                ) : null}
                {step.result_summary ? (
                  <div className="mt-2">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">观察结果</div>
                    <div className="mt-1 text-xs leading-5 text-slate-500">{step.result_summary}</div>
                  </div>
                ) : null}
                {step.status === 'awaiting_resolution' && step.resolution_type === 'clarification' ? (
                  <div className="mt-2 rounded-lg bg-blue-50 px-3 py-2">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-blue-500">澄清请求</div>
                    <div className="mt-1 text-xs leading-5 text-blue-700">{step.resolution_prompt || '等待补充国家和时间范围。'}</div>
                  </div>
                ) : null}
                {step.status === 'awaiting_resolution' && step.resolution_type === 'repair_strategy' ? (
                  <div className="mt-2 rounded-lg bg-blue-50 px-3 py-2">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-blue-500">Repair 策略选择</div>
                    <div className="mt-1 text-xs leading-5 text-blue-700">{step.resolution_prompt || '等待选择本次 cohort 的补数策略。'}</div>
                  </div>
                ) : null}
              </div>
            );
          })}
          {pendingSteps.length > 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-3 py-3">
              <div className="text-xs font-semibold text-slate-500">
                {runStatus === 'completed'
                  ? `${pendingSteps.length} 个计划步骤未执行`
                  : runStatus === 'cancelled'
                    ? `${pendingSteps.length} 个步骤因停止而跳过`
                    : runStatus === 'failed'
                      ? `${pendingSteps.length} 个步骤因失败而未执行`
                      : `后续 ${pendingSteps.length} 个步骤已规划，等待执行...`}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {review ? (
        <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
          <div className="text-xs font-semibold text-slate-500">规则审核</div>
          <div className="mt-1 text-sm font-semibold text-slate-700">{review.status || 'unknown'}</div>
          {Array.isArray(review.issues) && review.issues.length > 0 ? (
            <div className="mt-2 space-y-1">
              {review.issues.map((issue, idx) => (
                <div key={`issue-${idx}`} className="text-xs leading-5 text-slate-600">
                  {issue.uid && issue.bucket
                    ? `UID ${issue.uid} 缺少 ${issue.bucket} 数据`
                    : issue.message || issue.type || '存在待关注项'}
                </div>
              ))}
            </div>
          ) : null}
          {review.confidence_impact ? (
            <div className="mt-2 text-xs leading-5 text-slate-500">置信度影响：{review.confidence_impact}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function _intentLabel(intent) {
  const labels = {
    answer_from_workspace: '已有画像追问',
    profile_uid: '单 UID 画像分析',
    profile_batch: '批量画像分析',
    need_clarification: '需要补充条件',
    query_data_then_profile: '先取数后画像',
    run_trace: '轨迹分析',
    general_chat: '通用 Agent 对话',
  };
  return labels[intent] || intent || '';
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatExecutionTraceCard = ChatExecutionTraceCard;
