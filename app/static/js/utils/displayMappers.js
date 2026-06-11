// Extracted from app/ui/live_frontend.py during UI separation Step-1.

const { stringValue, numberValue, arrayValue } = window.AppUtils.normalize;

function formatCurrencyMxn(value) {
  return `$${numberValue(value, 0).toLocaleString('en-US')}`;
}

function formatCreditConfidence(value) {
  const normalized = stringValue(value, '').toLowerCase();
  const mapping = {
    high: '高',
    medium: '中',
    low: '低',
    partial: '中',
    ok: '高',
    unknown: '未知'
  };
  return mapping[normalized] || stringValue(value, '未知');
}

function formatCreditLevel(value) {
  const raw = stringValue(value, '未知');
  const normalized = raw.toLowerCase().replace(/\s+/g, '_');
  const mapping = {
    low: '低',
    medium: '中',
    medium_high: '中高',
    high: '高',
    thin_file: '薄征信',
    growing: '成长型',
    mature: '成熟型',
    thin: '薄征信'
  };
  return mapping[normalized] || raw;
}

function formatCreditSourceName(value) {
  const raw = stringValue(value, '');
  if (/buro de cr[eé]dito|buro de credito/i.test(raw)) {
    return 'Buró de Crédito（墨西哥）';
  }
  return raw || 'Buró de Crédito（墨西哥）';
}

function formatCreditRiskFlag(flag) {
  const text = stringValue(flag, '');
  const normalized = text.toLowerCase();
  const match = normalized.match(/^score value\s+(\d+)/);
  if (match) {
    return `评分值偏低（${match[1]} 分）`;
  }
  const mapping = {
    'very short credit history': '信用历史极短',
    'high utilization account present': '存在高使用率账户',
    'high inquiry heat in last 3 months': '近 3 个月查询热度偏高',
    'overall credit risk resolved as high': '整体征信风险偏高',
    'no major credit risk flags were detected from the prepared record.': '当前未识别出显著征信风险信号'
  };
  return mapping[normalized] || text || '当前暂无额外风险提示';
}

function formatCreditTag(tag) {
  const raw = stringValue(tag, '');
  const normalized = raw.toLowerCase();
  const exact = {
    'collection-watch': '需关注催收风险',
    'credit-footprint-thin': '征信足迹较薄'
  };
  if (exact[normalized]) {
    return exact[normalized];
  }
  if (normalized.startsWith('risk-')) {
    return `整体风险-${formatCreditLevel(normalized.slice(5))}`;
  }
  if (normalized.startsWith('credit-')) {
    return `评分段-${normalized.slice(7).toUpperCase()}`;
  }
  if (normalized.startsWith('debt-pressure-')) {
    return `负债压力-${formatCreditLevel(normalized.slice(14))}`;
  }
  if (normalized.startsWith('stability-')) {
    return `信用稳定性-${formatCreditLevel(normalized.slice(10))}`;
  }
  if (normalized.startsWith('borrowing-urgency-')) {
    return `借贷饥渴度-${formatCreditLevel(normalized.slice(18))}`;
  }
  if (normalized.startsWith('financial-maturity-')) {
    return `金融成熟度-${formatCreditLevel(normalized.slice(19))}`;
  }
  return raw || '未分类标签';
}

function formatCreditStatus(status) {
  const raw = stringValue(status, '未知');
  const normalized = raw.toLowerCase();
  if (/^(current|normal|good|ok|vigente|v)$/.test(normalized)) {
    return '状态正常';
  }
  if (/past_due|late|delinquent|overdue|mora/.test(normalized)) {
    return '存在逾期';
  }
  return raw;
}

function formatCreditUtilizationInsight(value) {
  const utilization = numberValue(value, 0);
  if (utilization >= 85) {
    return '额度使用率偏高';
  }
  if (utilization >= 60) {
    return '额度使用率偏高位';
  }
  if (utilization > 0) {
    return '额度使用率可控';
  }
  return '暂无额度使用信号';
}

function normalizeCreditAccountType(typeCode) {
  const code = stringValue(typeCode, '').toUpperCase();
  const map = {
    'CC': '信用卡',
    'TC': '信用卡',
    'TDC': '信用卡',
    'F': '零售信贷',
    'M': '个人贷款',
    'PL': '个人贷款',
    'AUTO': '车贷',
    'HOME': '房贷'
  };
  return map[code] || stringValue(typeCode, '未知类型');
}

function normalizeMetricKey(label) {
  const safeLabel = typeof label === 'string' ? label : '';
  const mapping = {
    '多头借贷风险': 'multi_loan_risk',
    '金融成熟度': 'financial_maturity',
    '消费能力': 'consumption_ability',
    '数据完整度': 'data_completeness'
  };
  return mapping[safeLabel] || safeLabel.toLowerCase().replace(/[^a-z0-9]+/g, '_');
}

function colorByIndex(index) {
  const colors = ['blue', 'cyan', 'indigo', 'purple', 'slate'];
  return colors[index % colors.length];
}

function softTagToneClass(index) {
  const tones = ['bg-blue-50 text-blue-700 border-blue-100','bg-cyan-50 text-cyan-700 border-cyan-100','bg-violet-50 text-violet-700 border-violet-100','bg-emerald-50 text-emerald-700 border-emerald-100','bg-amber-50 text-amber-700 border-amber-100'];
  return tones[index % tones.length];
}

function formatInlineList(values, fallback = '暂无') {
  const safeValues = arrayValue(values).map((item) => stringValue(item)).filter(Boolean);
  return safeValues.length ? safeValues.join('，') : fallback;
}

function tokenToBgClass(token) {
  const mapping = {
    blue: 'bg-blue-500',
    cyan: 'bg-cyan-500',
    green: 'bg-green-500',
    amber: 'bg-amber-500',
    slate: 'bg-slate-500',
    indigo: 'bg-indigo-500',
    purple: 'bg-purple-500',
    emerald: 'bg-emerald-500',
    rose: 'bg-rose-500',
    gray: 'bg-slate-400'
  };
  return mapping[token] || mapping.blue;
}

function levelWidthClass(level) {
  const mapping = {
    low: 'w-1/3',
    medium_low: 'w-2/5',
    medium: 'w-2/3',
    medium_high: 'w-4/5',
    high: 'w-full',
    unknown: 'w-1/4'
  };
  return mapping[stringValue(level, 'unknown')] || mapping.unknown;
}

function scoreBandWidthClass(scoreBand) {
  const mapping = {
    a: 'w-full',
    b: 'w-4/5',
    c: 'w-3/5',
    d: 'w-2/5'
  };
  return mapping[stringValue(scoreBand, '').toLowerCase()] || 'w-1/4';
}

function repaymentWidthClass(status) {
  const mapping = {
    stable: 'w-full',
    normal: 'w-2/3',
    watchlist: 'w-1/3'
  };
  return mapping[stringValue(status, '').toLowerCase()] || 'w-1/4';
}

function formatCurrency(value) {
  const safeValue = numberValue(value, 0);
  return `¥${safeValue.toLocaleString('en-US')}`;
}

function riskBadgeClass(riskLevel) {
  const mapping = {
    high: 'text-[11px] font-medium px-2 py-0.5 rounded-full border bg-red-50 text-red-600 border-red-200',
    mid: 'text-[11px] font-medium px-2 py-0.5 rounded-full border bg-amber-50 text-amber-600 border-amber-200',
    low: 'text-[11px] font-medium px-2 py-0.5 rounded-full border bg-blue-50 text-blue-600 border-blue-200',
    safe: 'text-[11px] font-medium px-2 py-0.5 rounded-full border bg-slate-50 text-slate-500 border-slate-200'
  };
  return mapping[riskLevel] || mapping.safe;
}

function toRiskLabel(riskLevel) {
  const mapping = {
    low: '低风险稳健用户',
    medium: '中风险观察用户',
    high: '高风险重点关注用户'
  };
  return mapping[riskLevel] || '待补充评估';
}

function toFinancialDisplayLabel(level) {
  const mapping = {
    banked: '银行化',
    semi_banked: '半银行化',
    non_banked: '非银行化'
  };
  return mapping[stringValue(level, '')] || stringValue(level, '待确认');
}

function toConsumptionDisplayLabel(level) {
  const mapping = {
    high: '高',
    medium_high: '中偏上',
    medium: '中等',
    low: '偏弱'
  };
  return mapping[stringValue(level, '')] || stringValue(level, '待确认');
}

function toSegmentDisplay(segment) {
  const mapping = {
    S1: 'S1 高价值稳健客群',
    S2: 'S2 稳健经营客群',
    S3: 'S3 机会转化客群',
    S4: 'S4 流失预警客群',
    S5: 'S5 风险关注客群',
    S6: 'S6 待观察客群'
  };
  return mapping[stringValue(segment, '').toUpperCase()] || `${stringValue(segment, 'S6')} 待观察客群`;
}

function toSegmentFeature(segment) {
  const mapping = {
    S1: '高价值 + 低风险',
    S2: '稳健经营 + 中低风险',
    S3: '活跃需求 + 待转化',
    S4: '高流失风险',
    S5: '高风险重点关注',
    S6: '信息有限待补充'
  };
  return mapping[stringValue(segment, '').toUpperCase()] || '信息有限待补充';
}

function toValueSignalDisplay(level) {
  const mapping = {
    high: '高价值',
    medium: '中高价值',
    low: '基础价值'
  };
  return mapping[stringValue(level, '').toLowerCase()] || stringValue(level, '待确认');
}

function toConfidenceDisplay(level) {
  const mapping = {
    high: '高',
    medium: '中',
    low: '低'
  };
  return mapping[stringValue(level, '').toLowerCase()] || stringValue(level, '低');
}

function toRiskDisplay(level) {
  const mapping = {
    low: '中低风险',
    medium: '中等风险',
    high: '高风险'
  };
  return mapping[stringValue(level, '').toLowerCase()] || '待确认风险';
}

window.AppUtils = window.AppUtils || {};
window.AppUtils.displayMappers = {
  formatCurrencyMxn,
  formatCreditConfidence,
  formatCreditLevel,
  formatCreditSourceName,
  formatCreditRiskFlag,
  formatCreditTag,
  formatCreditStatus,
  formatCreditUtilizationInsight,
  normalizeCreditAccountType,
  normalizeMetricKey,
  colorByIndex,
  softTagToneClass,
  formatInlineList,
  tokenToBgClass,
  levelWidthClass,
  scoreBandWidthClass,
  repaymentWidthClass,
  formatCurrency,
  riskBadgeClass,
  toRiskLabel,
  toFinancialDisplayLabel,
  toConsumptionDisplayLabel,
  toSegmentDisplay,
  toSegmentFeature,
  toValueSignalDisplay,
  toConfidenceDisplay,
  toRiskDisplay,
};
