"""
Thailand behavior profile constants.

Pay cycle data sources:
- BOT (Bank of Thailand) labor statistics: monthly pay dominant
- Large corporations and civil service: 25th-30th of month
- Confidence: medium (formal sector well-documented; SMEs may differ)

Primary channel rationale:
- LINE 在泰国渗透率 >90%，是 messaging + payment 主入口（区别于其他东南亚国家）

业务值来源: docs/specs/05-country-pack-design.md v6.1 §2.2

TODO(country-pack): validate against actual user transaction data once available.
"""

from __future__ import annotations

from app.country_packs.mx.behavior_profile import BehaviorCountryPack

TH_PAY_WINDOW = frozenset({25, 26, 27, 28, 29, 30, 31, 1, 2, 3})
TH_PAY_CYCLE_NAME = "เงินเดือน"
TH_PRIMARY_CHANNEL = "LINE"
TH_PAY_CYCLE_DESCRIPTION = "每月25-31号发薪"

TH_BEHAVIOR_COUNTRY_PACK = BehaviorCountryPack(
    country_code="th",
    display_name="泰国",
    default_language="zh-CN",
    prompt_language="zh-CN",
    report_language="zh-CN",
    source_display_name="Behavior Event Stream (TH)",
    default_contact_channel=TH_PRIMARY_CHANNEL,
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
            "register", "signup", "login", "signin", "otp",
            "verify_phone", "face", "liveness",
            "ลงทะเบียน", "เข้าสู่ระบบ", "ยืนยันตัวตน", "บัตรประชาชน",
            "开户", "注册", "登录", "活体", "验证码",
        ),
        "discovery": (
            "home", "product", "offer", "coupon", "rate",
            "fee", "promo", "banner", "browse",
            "สินค้า", "ดอกเบี้ย", "โปรโมชั่น", "หน้าแรก",
            "产品", "利率", "优惠", "活动", "首页",
        ),
        "application": (
            "apply", "application", "kyc", "upload", "bank",
            "employment", "risk", "approval", "reject", "form",
            "สมัคร", "อนุมัติ", "ปฏิเสธ", "ธนาคาร", "เอกสาร",
            "申请", "认证", "审核", "拒绝", "表单", "绑卡",
        ),
        "repayment": (
            "repay", "payment", "due", "overdue", "collection",
            "renew", "settle",
            "ชำระ", "ค้างชำระ", "ติดตามหนี้", "ต่ออายุ", "ปิดบัญชี",
            "还款", "逾期", "催收", "续借", "结清",
        ),
        "support": (
            "support", "service", "help", "faq", "cs",
            "agent", "call", "line", "message",
            "บริการลูกค้า", "ช่วยเหลือ", "ติดต่อ", "ข้อความ",
            "客服", "帮助", "电话", "消息", "提醒",
        ),
    },
    contact_channel_keywords={
        "LINE": ("line", "line app", "line chat", "ไลน์"),
        "电话": ("call", "phone", "dial", "ivr", "voice", "โทร"),
        "短信": ("sms", "message", "text", "ข้อความ"),
        "App Push": ("push", "notification", "reminder", "แจ้งเตือน"),
    },
)
