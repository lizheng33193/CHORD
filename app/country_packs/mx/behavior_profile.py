"""Mexico Behavior Profile country pack."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BehaviorCountryPack:
    """Static country configuration used by the Behavior profile pipeline."""

    country_code: str
    display_name: str
    default_language: str
    prompt_language: str
    report_language: str
    source_display_name: str
    default_contact_channel: str
    default_contact_time: str
    stage_labels: dict[str, str] = field(default_factory=dict)
    journey_section_labels: dict[str, str] = field(default_factory=dict)
    stage_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)
    contact_channel_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)


MX_BEHAVIOR_COUNTRY_PACK = BehaviorCountryPack(
    country_code="mx",
    display_name="墨西哥",
    default_language="zh-CN",
    prompt_language="zh-CN",
    report_language="zh-CN",
    source_display_name="Behavior Event Stream (MX)",
    default_contact_channel="WhatsApp",
    default_contact_time="19:00-21:00",
    stage_labels={
        "acquisition": "拉新与注册阶段",
        "discovery": "产品浏览阶段",
        "application": "申请与认证阶段",
        "repayment": "还款与履约阶段",
        "support": "客服与触达阶段",
        "unknown": "其他行为阶段",
    },
    journey_section_labels={
        "init": "初始化阶段",
        "basic_profile": "基础资料填写",
        "contact_entry": "联系人信息录入",
        "correction_retry": "反复尝试与格式纠错",
        "manual_fix": "密集手动修正",
        "dormancy_return": "深度流失/决策沉默",
        "bank_retry": "银行卡绑定重试",
        "offer_decision": "额度选择与权益决策",
        "unknown": "其他行为阶段",
    },
    stage_keywords={
        "acquisition": (
            "register",
            "signup",
            "login",
            "signin",
            "otp",
            "verify_phone",
            "face",
            "liveness",
            "开户",
            "注册",
            "登录",
            "活体",
            "验证码",
        ),
        "discovery": (
            "home",
            "product",
            "offer",
            "coupon",
            "rate",
            "fee",
            "promo",
            "banner",
            "browse",
            "产品",
            "利率",
            "优惠",
            "活动",
            "首页",
        ),
        "application": (
            "apply",
            "application",
            "kyc",
            "upload",
            "bank",
            "employment",
            "risk",
            "approval",
            "reject",
            "form",
            "申请",
            "认证",
            "审核",
            "拒绝",
            "表单",
            "绑卡",
        ),
        "repayment": (
            "repay",
            "payment",
            "due",
            "overdue",
            "collection",
            "renew",
            "settle",
            "还款",
            "逾期",
            "催收",
            "续借",
            "结清",
        ),
        "support": (
            "support",
            "service",
            "help",
            "faq",
            "cs",
            "agent",
            "call",
            "whatsapp",
            "message",
            "客服",
            "帮助",
            "电话",
            "消息",
            "提醒",
        ),
    },
    contact_channel_keywords={
        "WhatsApp": ("whatsapp", "wa", "whats app"),
        "电话": ("call", "phone", "dial", "ivr", "voice"),
        "短信": ("sms", "message", "text"),
        "App Push": ("push", "notification", "reminder"),
    },
)

# --- Quincena pay-cycle configuration (Mexico-specific) ---
MX_QUINCENA_WINDOW = frozenset({1, 2, 3, 15, 16, 17, 18, 28, 29, 30, 31})
MX_PAY_CYCLE_NAME = "Quincena"
MX_PRIMARY_CHANNEL = "WhatsApp"
MX_PAY_CYCLE_DESCRIPTION = "每月15号和月末发薪"
