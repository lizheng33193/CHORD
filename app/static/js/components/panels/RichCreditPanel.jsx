// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// Source: RichCreditPanel at L1254-L1600.
// Inline gauge SVG (L1374-L1393) replaced by <CreditGauge>.
// Inline radar SVG (L1571-L1595) replaced by <CreditRiskStructure>.
// Local radarPoint(value, index, count) retained for pre-computing radarPolygon
// (per Plan E.3 + user authorization). Un-nest fix: summary.split(/\\n+/) -> /\n+/
// (same G.3 UID_PATTERN precedent).

const { useState } = React;
const { CreditCard } = window.LucideReact || {};
const { objectValue, arrayValue, stringValue, numberValue, parsePercent } = window.AppUtils.normalize;
const {
  formatCreditRiskFlag,
  formatCreditTag,
  formatCreditLevel,
  formatCreditSourceName,
  formatCreditConfidence,
  formatCurrencyMxn,
  normalizeCreditAccountType,
  formatCreditUtilizationInsight,
  formatCreditStatus,
  softTagToneClass
} = window.AppUtils.displayMappers;
const { CreditProgressRow, CreditGauge, CreditRiskStructure } = window.AppComponents;

function RichCreditPanel({ profile }) {
  const [selectedRepayIndex, setSelectedRepayIndex] = useState(-1);
  const structured = objectValue(profile?.structured_result);
  const metrics = objectValue(structured.metrics);
  const evidence = objectValue(structured.evidence);
  const header = objectValue(evidence.profile_header);
  const llmProfile = objectValue(evidence.llm_credit_profile);
  const modelTrace = objectValue(structured.model_trace);
  const llmAccepted = Boolean(modelTrace.used_llm);
  const llmStatusLabel = llmAccepted ? 'LLM 推理完成' : '规则降级结果';
  const llmStatusClass = llmAccepted ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200';
  const rawRiskFlags = arrayValue(llmProfile.risk_flags).length ? arrayValue(llmProfile.risk_flags) : arrayValue(evidence.risk_flags);
  const riskFlags = arrayValue(llmProfile.risk_flags_display).length
    ? arrayValue(llmProfile.risk_flags_display)
    : rawRiskFlags.map((flag) => formatCreditRiskFlag(flag));
  const tags = arrayValue(structured.tags);
  const displayTags = Array.from(new Set(tags.map((tag) => formatCreditTag(tag))));
  const radarScores = objectValue(evidence.radar_scores).hasOwnProperty('financial_maturity')
    ? objectValue(evidence.radar_scores)
    : objectValue(metrics.radar_scores);
  const repaymentAmounts = arrayValue(evidence.repayment_amount_timeline).length
    ? arrayValue(evidence.repayment_amount_timeline).map((v) => numberValue(v, 0))
    : arrayValue(metrics.repayment_amount_timeline).map((v) => numberValue(v, 0));
  const repaymentNotes = arrayValue(evidence.repayment_amount_notes).length
    ? arrayValue(evidence.repayment_amount_notes).map((v) => stringValue(v, '当月暂无可识别的还款或应还金额说明。'))
    : arrayValue(metrics.repayment_amount_notes).map((v) => stringValue(v, '当月暂无可识别的还款或应还金额说明。'));
  const summary = stringValue(llmProfile.credit_summary, stringValue(profile?.summary, '当前暂无可展示的征信判断内容。'));
  const summaryParagraphs = summary.split(/\n+/).map((item) => item.trim()).filter(Boolean);
  const confidence = stringValue(llmProfile.confidence, stringValue(structured.status, 'unknown'));
  const scoreValue = numberValue(metrics.score_value, 0);
  const debtTotal = numberValue(metrics.total_outstanding_debt_mxn, 0);
  const monthPay = numberValue(metrics.monthly_payment_estimate_mxn, 0);
  const oldestMonths = numberValue(metrics.oldest_account_age_months, 0);
  const inquiries12m = numberValue(metrics.inquiries_last_12_months, 0);
  const accountDetails = arrayValue(evidence.account_details);
  const months = Array.from({ length: 12 }, (_, index) => `${index + 1}月`);
  const amountValues = (repaymentAmounts.length ? repaymentAmounts : Array.from({ length: 12 }, () => 0)).slice(0, 12);
  const amountNotes = (repaymentNotes.length ? repaymentNotes : Array.from({ length: 12 }, () => '当月暂无可识别的还款或应还金额说明。')).slice(0, 12);
  const amountMax = Math.max(1, ...amountValues);
  const maturity = objectValue(llmProfile.financial_maturity);
  const debtPressure = objectValue(llmProfile.debt_pressure);
  const creditStability = objectValue(llmProfile.credit_stability);
  const borrowingUrgency = objectValue(llmProfile.borrowing_urgency);
  const maturityLabel = formatCreditLevel(stringValue(maturity.display_level, stringValue(maturity.level, stringValue(metrics.financial_maturity_level, '未知'))));
  const pressureLabel = formatCreditLevel(stringValue(debtPressure.display_level, stringValue(debtPressure.level, stringValue(metrics.debt_pressure_level, '未知'))));
  const stabilityLabel = formatCreditLevel(stringValue(creditStability.display_level, stringValue(creditStability.level, stringValue(metrics.credit_stability_level, '未知'))));
  const urgencyLabel = formatCreditLevel(stringValue(borrowingUrgency.display_level, stringValue(borrowingUrgency.level, stringValue(metrics.borrowing_urgency_level, stringValue(metrics.borrowing_hunger_level, '未知')))));
  const sourceMeta = objectValue(evidence.source_meta);
  const sourceName = formatCreditSourceName(stringValue(sourceMeta.source_display_name, 'Buró de Crédito（墨西哥）'));
  const reportDate = stringValue(sourceMeta.credit_report_date, '');
  const confidenceLabel = formatCreditConfidence(confidence);
  const scoreBand = stringValue(metrics.credit_score_band, '未知');
  const riskLevel = formatCreditLevel(stringValue(metrics.risk_level, '未知'));
  const radarDimensions = [
    { key: 'financial_maturity', label: '金融成熟度' },
    { key: 'repayment_pressure_index', label: '还款压力' },
    { key: 'credit_stability', label: '信用稳定性' },
    { key: 'borrowing_urgency', label: '借贷饥渴度' },
    { key: 'credit_history_depth', label: '信用历史厚度' },
    { key: 'cash_tightness', label: '资金紧张程度' }
  ];
  const radarValues = radarDimensions.map((item) => Math.max(0, Math.min(100, numberValue(radarScores[item.key], 0))));
  const centerX = 150;
  const centerY = 135;
  const radius = 92;

  function radarPoint(value, index, count) {
    const angle = (-Math.PI / 2) + (index * 2 * Math.PI / count);
    const r = radius * (value / 100);
    return {
      x: centerX + r * Math.cos(angle),
      y: centerY + r * Math.sin(angle),
      labelX: centerX + (radius + 24) * Math.cos(angle),
      labelY: centerY + (radius + 24) * Math.sin(angle)
    };
  }

  const radarPolygon = radarValues
    .map((value, index) => {
      const point = radarPoint(value, index, radarDimensions.length);
      return `${point.x},${point.y}`;
    })
    .join(' ');

  if (stringValue(structured.status) === 'data_missing') {
    return (
      <div className="animate-in fade-in duration-500 space-y-7">
        <div className="flex items-center gap-3 mb-2 pb-4 border-b border-slate-100">
          <CreditCard className="w-8 h-8 text-slate-600" />
          <h2 className="text-2xl font-bold text-slate-800">Skill 3：征信画像 Agent 分析报告</h2>
        </div>
        <div className="relative overflow-hidden rounded-[28px] border border-slate-200 bg-white px-7 py-8 shadow-[0_16px_40px_rgba(15,23,42,0.07)]">
          <div className="absolute -right-16 -top-16 h-44 w-44 rounded-full bg-slate-100 blur-3xl"></div>
          <div className="relative">
            <div className="text-lg font-semibold text-slate-800 mb-3">当前暂无征信页面数据</div>
            <p className="text-sm leading-8 text-slate-600">{stringValue(profile?.summary, '当前 uid 暂未找到可用的征信样本数据。')}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-in fade-in duration-500 space-y-7">
      <div className="flex items-center gap-3 mb-2 pb-4 border-b border-slate-100">
        <CreditCard className="w-8 h-8 text-slate-600" />
        <h2 className="text-2xl font-bold text-slate-800">Skill 3：征信画像 Agent 分析报告</h2>
        <div className="ml-auto text-right">
          <div className="text-sm text-slate-500">数据源：{sourceName}</div>
          {reportDate ? <div className="mt-1 text-xs text-slate-400">报告时间：{reportDate}</div> : null}
        </div>
        <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${llmStatusClass}`}>{llmStatusLabel}</span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        <section className="xl:col-span-4 relative overflow-hidden rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_20px_45px_rgba(15,23,42,0.08)]">
          <div className="absolute -left-14 -top-14 h-44 w-44 rounded-full bg-blue-100/60 blur-3xl"></div>
          <div className="absolute -right-8 bottom-0 h-32 w-32 rounded-full bg-orange-100/60 blur-3xl"></div>
          <div className="relative text-sm text-slate-500 mb-3">BURÓ - MI SCORE 综合评分</div>
          <div className="relative h-44">
            <CreditGauge scoreValue={scoreValue} />
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <span className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">评分段：{scoreBand}</span>
            <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">整体风险：{riskLevel}</span>
          </div>
          <div className="mt-3 text-sm text-slate-600">UID：{stringValue(header.uid, stringValue(structured.uid, 'unknown'))}</div>
          <div className="mt-2 text-sm text-slate-500">基于标准化 Buró 征信记录生成</div>
          <div className="mt-2 inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-700">
            置信度：{confidenceLabel}
          </div>
        </section>

        <section className="xl:col-span-8 space-y-4">
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <div className="rounded-[24px] border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-5 shadow-sm">
              <div className="text-sm text-slate-500">总负债（MXN）</div>
              <div className="mt-2 text-[28px] font-bold text-slate-800">{formatCurrencyMxn(debtTotal)}</div>
            </div>
            <div className="rounded-[24px] border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-5 shadow-sm">
              <div className="text-sm text-slate-500">月还款估算（MXN）</div>
              <div className="mt-2 text-[28px] font-bold text-slate-800">{formatCurrencyMxn(monthPay)}</div>
            </div>
            <div className="rounded-[24px] border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-5 shadow-sm">
              <div className="text-sm text-slate-500">最老账户</div>
              <div className="mt-2 text-[28px] font-bold text-slate-800">{oldestMonths}<span className="ml-2 text-base font-medium text-slate-500">个月</span></div>
            </div>
            <div className="rounded-[24px] border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-5 shadow-sm">
              <div className="text-sm text-slate-500">近 12 个月查询次数</div>
              <div className="mt-2 text-[28px] font-bold text-amber-600">{inquiries12m} 次</div>
            </div>
          </div>

          <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
            <h3 className="text-xl font-bold text-slate-800 mb-5">四维征信评估模型（4D Evaluation）</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <CreditProgressRow label="金融成熟度" levelLabel={maturityLabel} value={`${numberValue(radarScores.financial_maturity, 0)}%`} widthPercent={numberValue(radarScores.financial_maturity, 0)} barClass="bg-emerald-500" note={stringValue(maturity.reasoning, '主要结合账户账龄、银行系足迹和信用基础判断。')} levelClass="text-emerald-600" />
              <CreditProgressRow label="信用稳定性" levelLabel={stabilityLabel} value={`${numberValue(radarScores.credit_stability, 0)}%`} widthPercent={numberValue(radarScores.credit_stability, 0)} barClass="bg-blue-500" note={stringValue(creditStability.reasoning, '主要结合逾期深度、逾期账户数量和账户状态判断。')} levelClass="text-blue-600" />
              <CreditProgressRow label="负债压力评估" levelLabel={pressureLabel} value={`${numberValue(radarScores.repayment_pressure_index, 0)}%`} widthPercent={numberValue(radarScores.repayment_pressure_index, 0)} barClass="bg-amber-500" note={stringValue(debtPressure.reasoning, '综合参考总负债、估算月还款与额度使用率。')} levelClass="text-amber-600" />
              <CreditProgressRow label="借贷饥渴度" levelLabel={urgencyLabel} value={`${numberValue(radarScores.borrowing_urgency, 0)}%`} widthPercent={numberValue(radarScores.borrowing_urgency, 0)} barClass="bg-rose-500" note={stringValue(borrowingUrgency.reasoning, '结合近 3 至 6 个月查询密度判断短期融资活跃度。')} levelClass="text-rose-600" />
            </div>
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <section className="xl:col-span-4 rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
          <h3 className="text-xl font-bold text-slate-800 mb-3">近 12 个月还款轨迹</h3>
          <div className="mb-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600 leading-6">
            每个柱状卡片展示系统识别到的当月还款或应还金额（MXN）。点击月份卡片后，可在下方查看对应的摘要说明。
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {amountValues.map((value, index) => {
              const height = Math.max(8, Math.round((numberValue(value, 0) / amountMax) * 90));
              const noteText = stringValue(amountNotes[index], '当月暂无可识别的还款或应还金额说明。');
              const isSelected = selectedRepayIndex === index;
              return (
                <button
                  type="button"
                  key={`m-${index}`}
                  title={noteText}
                  onClick={() => setSelectedRepayIndex(isSelected ? -1 : index)}
                  className={`rounded-2xl border p-3 text-left transition-all duration-200 ${
                    isSelected ? 'border-blue-300 bg-blue-50/60 shadow-sm' : 'border-slate-100 bg-slate-50 hover:border-blue-200 hover:bg-white'
                  }`}
                >
                  <div className="text-[11px] font-medium text-slate-500 mb-2">{months[index]}</div>
                  <div className="h-20 rounded-xl bg-slate-200/80 flex items-end overflow-hidden">
                    <div className="w-full bg-emerald-500 rounded-t-xl" style={{ height: `${height}%` }}></div>
                  </div>
                  <div className="mt-2 text-sm font-semibold text-slate-700">{formatCurrencyMxn(value)}</div>
                </button>
              );
            })}
          </div>
          {selectedRepayIndex >= 0 && selectedRepayIndex < amountNotes.length && (
            <div className="mt-4 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm leading-7 text-blue-900">
              <div className="font-semibold mb-1">{months[selectedRepayIndex]}解析</div>
              <div>{stringValue(amountNotes[selectedRepayIndex], '当月暂无可识别的还款或应还金额说明。')}</div>
            </div>
          )}
        </section>

        <section className="xl:col-span-8 rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h3 className="text-xl font-bold text-slate-800">活跃账户解析摘要（Active Accounts）</h3>
            <span className="text-sm text-slate-500">账户数：{accountDetails.length}</span>
          </div>
          <div className="space-y-3">
            {accountDetails.length ? accountDetails.slice(0, 6).map((item, index) => {
              const institution = stringValue(item.institution, `账户 ${index + 1}`);
              const accountType = stringValue(item.type, 'UNKNOWN');
              const accountTypeLabel = stringValue(item.account_type_label, normalizeCreditAccountType(accountType));
              const ageMonths = numberValue(item.account_age_months, 0);
              const status = stringValue(item.payment_status, 'unknown');
              const balance = numberValue(item.current_balance_mxn, 0);
              const limit = numberValue(item.credit_limit_mxn, numberValue(item.original_amount_mxn, 0));
              const utilText = stringValue(item.utilization_rate, limit > 0 ? `${Math.min(100, Math.round((balance / limit) * 100))}%` : 'N/A');
              const utilValue = parsePercent(utilText);
              const loanOrCreditText = /CC|TC|CARD|TDC/i.test(accountType) ? '信用卡' : '贷款账户';
              const amountLabel = limit > 0 ? '授信额度' : '原始金额';
              const amountValue = limit > 0 ? limit : balance;
              const resolvedUtilText = utilText === 'N/A' && amountValue > 0 && balance > 0 ? '100%（估算）' : utilText;
              const effectiveUtilValue = utilText === 'N/A' && amountValue > 0 && balance > 0 ? 100 : utilValue;
              const utilRiskText = formatCreditUtilizationInsight(effectiveUtilValue);
              const statusLabel = formatCreditStatus(status);
              return (
                <div key={`${institution}-${index}`} className="rounded-[24px] border border-slate-100 bg-gradient-to-r from-slate-50 to-white px-5 py-5 flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-[28px] leading-tight text-slate-800 break-words">
                      {institution}
                    </div>
                    <div className="mt-2 text-[15px] text-slate-500">
                      账户类型：{accountTypeLabel} | 账户形态：{loanOrCreditText} | 账龄：{ageMonths} 个月
                    </div>
                    <div className="mt-3 text-[22px] font-semibold text-slate-800 break-words">
                      {amountLabel}：{formatCurrencyMxn(amountValue)} | 当前余额：{formatCurrencyMxn(balance)}
                    </div>
                    <div className="mt-2 text-sm text-slate-500">使用率解读：{utilRiskText}</div>
                  </div>
                  <div className="shrink-0 md:min-w-[170px] rounded-2xl border border-slate-200 bg-white/90 px-4 py-4 text-right shadow-sm">
                    <span className={`inline-flex text-xs font-bold px-3 py-1 rounded-full border ${
                      /^(current|normal|good|ok|v|vigente)$/i.test(status) ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : 'bg-amber-50 text-amber-600 border-amber-200'
                    }`}>
                      {statusLabel}
                    </span>
                    <div className={`mt-4 text-[18px] font-bold ${effectiveUtilValue >= 80 ? 'text-amber-600' : 'text-slate-700'}`}>
                      额度使用率：{resolvedUtilText}
                    </div>
                  </div>
                </div>
              );
            }) : (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-400">当前暂无可用的账户级明细。</div>
            )}
          </div>
        </section>
      </div>

      <section className="rounded-[30px] border border-slate-200 bg-white p-6 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-5">
          <div>
            <h3 className="text-2xl font-bold text-slate-800">征信画像判断（LLM 输出）</h3>
            <div className="mt-2 text-sm text-slate-500">以下结论基于结构化征信事实与运行时解释层综合生成，用于辅助授信和业务判断。</div>
          </div>
          <span className="inline-flex w-fit text-sm font-semibold px-4 py-2 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
            置信度：{confidenceLabel}
          </span>
        </div>
        <div className="rounded-[26px] border border-slate-100 bg-gradient-to-br from-slate-50 via-white to-blue-50/40 px-5 py-5">
          <div className="space-y-4 text-[15px] leading-8 text-slate-700">
            {(summaryParagraphs.length ? summaryParagraphs : ['当前暂无可展示的征信判断内容。']).map((paragraph, index) => (
              <p key={`credit-summary-${index}`}>{paragraph}</p>
            ))}
          </div>
        </div>
        <div className="mt-6">
          <div className="text-sm font-semibold text-slate-700 mb-3">用户标签</div>
          <div className="flex flex-wrap gap-2">
            {displayTags.length ? displayTags.slice(0, 12).map((tag, index) => (
              <span key={`${tag}-${index}`} className={`px-3 py-1 rounded-full text-sm font-semibold border ${softTagToneClass(index)}`}>{tag}</span>
            )) : <span className="text-sm text-slate-400">当前暂无标签</span>}
          </div>
        </div>
        {riskFlags.length ? (
          <div className="mt-6">
            <div className="text-sm font-semibold text-slate-700 mb-3">重点风险提示</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {riskFlags.slice(0, 6).map((flag, index) => (
              <div key={`${flag}-${index}`} className="rounded-2xl bg-amber-50 border border-amber-100 px-4 py-3 text-sm leading-6 text-amber-800">
                {formatCreditRiskFlag(flag)}
              </div>
            ))}
          </div>
          </div>
        ) : null}
        <div className="mt-6 rounded-[26px] border border-slate-100 bg-slate-50 p-4 overflow-x-auto">
          <div className="mb-3 text-sm font-semibold text-slate-700">征信结构雷达图</div>
          <CreditRiskStructure
            radarDimensions={radarDimensions}
            radarValues={radarValues}
            radarPolygon={radarPolygon}
            centerX={centerX}
            centerY={centerY}
          />
        </div>
      </section>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.RichCreditPanel = RichCreditPanel;
