// Extracted from app/ui/live_frontend.py during UI separation Step-1.

const { stringValue } = window.AppUtils.normalize;

function buildComprehensiveMarketingSuggestion(segment, valueSignal, llmAccepted) {
  const normalizedSegment = stringValue(segment, '').toUpperCase();
  const normalizedValue = stringValue(valueSignal, '').toLowerCase();
  if (normalizedSegment === 'S1' || normalizedValue === 'high') {
    return '建议优先推送提额、续贷或高价值权益方案，突出稳定经营与长期合作收益。';
  }
  if (normalizedSegment === 'S5') {
    return '营销触达应更克制，避免过强刺激，优先传递透明规则与稳健服务信息。';
  }
  return llmAccepted
    ? '建议以常规权益、分层额度和场景化触达为主，逐步验证转化与留存表现。'
    : '当前结果为回退展示，建议先观察后续补充数据，再决定是否推送更强营销动作。';
}

function buildComprehensiveRiskSuggestion(riskLevel, conflictCount, confidenceLevel) {
  const normalizedRisk = stringValue(riskLevel, '').toLowerCase();
  const normalizedConfidence = stringValue(confidenceLevel, '').toLowerCase();
  if (normalizedRisk === 'high') {
    return '维持强规则校验与名单监控，必要时收紧额度或转人工复核。';
  }
  if (conflictCount > 0) {
    return '建议保留监控名单，并持续跟踪跨模块冲突信号是否扩大。';
  }
  if (normalizedConfidence === 'low') {
    return '当前置信度偏低，建议先补数或等待更多行为样本后再放大自动化决策权重。';
  }
  return '可维持当前风险策略，并按周期复评综合画像变化趋势。';
}

window.AppUtils = window.AppUtils || {};
window.AppUtils.advice = {
  buildComprehensiveMarketingSuggestion,
  buildComprehensiveRiskSuggestion,
};
