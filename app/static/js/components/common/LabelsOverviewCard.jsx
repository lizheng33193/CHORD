const { Tag } = window.LucideReact || {};
const { objectValue, stringValue } = window.AppUtils.normalize;

const GROUP_TITLES = {
  basic_attributes: '基础属性',
  risk_labels: '风险标签',
  behavior_labels: '行为标签',
  value_labels: '价值标签',
  metadata: '元数据'
};

const GROUP_ORDER = ['basic_attributes', 'risk_labels', 'behavior_labels', 'value_labels', 'metadata'];

const KEY_LABELS = {
  age_band: '年龄段',
  occupation_type: '职业类型',
  banking_level: '银行层级',
  geo_region: '地域',
  multi_loan_risk: '多头借贷',
  credit_stability: '信用稳定性',
  debt_pressure: '负债压力',
  borrow_hunger: '借款渴求',
  repayment_willingness: '还款意愿',
  credit_line_willingness: '提额意愿',
  churn_risk: '流失风险',
  outreach_preference: '触达偏好',
  consumption_power: '消费能力',
  lifestyle: '生活方式',
  segment: '客群分层',
  profile_confidence: '画像置信度',
  data_completeness: '数据完整度'
};

const VALUE_DISPLAY_MAP = {
  "banked": "银行化", "semi-banked": "半银行化", "unbanked": "非银行化",
  "unknown": "未知", "high": "高", "medium": "中", "low": "低",
  "good": "良好", "poor": "较差", "excellent": "优秀", "fair": "一般",
  "strong": "强", "moderate": "中等", "weak": "弱", "none": "无"
};

function valueBadgeClass(value) {
  const v = (value || '').toLowerCase();
  if (v.includes('高') || v.includes('high') || v.includes('差') || v.includes('poor')) {
    return 'bg-red-100 text-red-700';
  }
  if (v.includes('中') || v.includes('medium') || v.includes('一般')) {
    return 'bg-amber-100 text-amber-700';
  }
  if (v.includes('低') || v.includes('low') || v.includes('良') || v.includes('good') || v.includes('优')) {
    return 'bg-green-100 text-green-700';
  }
  return 'bg-slate-100 text-slate-600';
}

function LabelsOverviewCard({ labels }) {
  if (!labels) {
    return null;
  }

  return (
    <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
      <h3 className="text-base font-bold text-slate-800 mb-4 flex items-center gap-2">
        {Tag ? <Tag className="w-4 h-4 text-blue-500" /> : null}
        标签概览 · Standardized Labels
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {GROUP_ORDER.map((groupKey) => {
          const group = objectValue(labels[groupKey]);
          if (!group || Object.keys(group).length === 0) {
            return null;
          }
          return (
            <div key={groupKey} className="bg-slate-50/70 border border-slate-200 rounded-xl p-4">
              <h4 className="text-sm font-bold text-slate-700 mb-3">{GROUP_TITLES[groupKey] || groupKey}</h4>
              <ul className="space-y-2">
                {Object.entries(group).map(([k, v]) => {
                  const valueText = stringValue(v, '—');
                  const displayValue = VALUE_DISPLAY_MAP[(valueText || '').toLowerCase()] || valueText;
                  return (
                    <li key={k} className="flex flex-col gap-1">
                      <span className="text-xs text-slate-400">{KEY_LABELS[k] || k}</span>
                      <span className={`inline-block self-start rounded-full px-2 py-0.5 text-xs ${valueBadgeClass(valueText)}`}>
                        {displayValue}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.LabelsOverviewCard = LabelsOverviewCard;
