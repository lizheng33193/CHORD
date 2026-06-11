"""Thailand Credit Profile country pack — risk_features 模式。

v6 业务模型重定向：
- TH credit 数据是公司风控特征聚合表（11 维特征 + 哨兵字符串），
  不是信用局报告，不存在评分模型，不存在账户类型。
- profile_mode = "risk_features" 显式声明业务模型，
  下游 explainer / feature_builder / decision_engine 据此分支。

业务值来源: docs/specs/05-country-pack-design.md v6.1 §2.3 / §2.5 / §2.6
csv 数据来源: New data/thai72/credit/thailand_72_withdraw_user_credit_profile_20260201_0430.csv
"""

from __future__ import annotations

from app.country_packs.mx.credit_profile import CreditCountryPack

TH_CREDIT_COUNTRY_PACK = CreditCountryPack(
    country_code="th",
    display_name="泰国",
    default_language="zh-CN",
    report_language="zh-CN",
    prompt_language="zh-CN",
    currency_code="THB",
    source_display_name="风控特征聚合表（泰国）",
    score_band_thresholds=(),                    # 永久空 — TH 数据不含评分模型
    account_type_labels={},                      # 永久空 — TH 数据不含账户类型
    profile_mode="risk_features",                # v6 显式声明业务模型（不是 buro）
    risk_feature_labels={
        # 身份核验类（1 项）
        "liveness_score": "人脸活体识别分数（防伪反欺诈）",
        # 申请行为类（3 项）
        "apply_7d_num": "近 7 天贷款申请次数",
        "apply_refuse_num": "历史申请被拒次数",
        "cashloan_app_num": "设备已安装的现金贷竞品 App 数量",
        # 还款履约类（2 项）
        "finished_assets_num": "历史已结清贷款笔数",
        "max_yuqi_days": "历史最大逾期天数",
        # 社交关系类（3 项）
        "contact_num": "通讯录联系人总数",
        "is_contact_black": "通讯录是否包含黑名单联系人（0/1）",
        "bankcard_user_num": "银行卡关联账户数量",
        # 规则命中类（2 项）
        "rule_hit_多头规则拦截": "多头借贷规则是否命中",
        "rule_hit_逾期未结清拦截": "逾期未结清规则是否命中",
    },
    sentinel_values={
        "liveness_score": ("无活体分",),
        "max_yuqi_days": ("无逾期",),
        "rule_hit_多头规则拦截": ("无记录",),
        "rule_hit_逾期未结清拦截": ("无记录",),
    },
)
