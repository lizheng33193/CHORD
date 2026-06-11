# Spec 05: th risk-feature country pack 设计（A1 双模式 v6）

> **STATUS**: ✅ **LOCKED·v6.1 — 双模式字段矩阵 + 路径 Q contracts 扩展就绪 / 可进 Plan 05 Phase 2**
>
> **关联 Plan**: `docs/plans/05-th-country-pack-plan.md`（v6.1 A1 双模式 + 路径 Q）
>
> **日期**: 2026-05-05（v1）/ 2026-05-05（v2）/ 2026-05-05（v3 BLOCKED）/ 2026-05-06（v4 路径 A 重写）/ 2026-05-07（v5 NCB placeholder — 业务建模错误）/ 2026-05-07（v6 A1 双模式 risk_features 修正） / 2026-05-07（v6.1 路径 Q contracts 扩展 + 5 CRITICAL 代码对齐修正）
>
> **v5→v6 业务建模重定向**：v5 把 TH credit 错认为 NCB 征信报告并设计了 FICO 风格 placeholder。实际 TH 数据是公司**风控特征聚合表**（13 列：人脸活体 / 通讯录 / 竞品 App / 7 天申请 / 历史结清-被拒 / 最大逾期 / 黑名单 / 银行卡关联 / 多头规则 / 逾期规则），不是 NCB / FICO 模型。v6 引入 `profile_mode` 双模式 dataclass：MX `="buro"` 走信用报告解读，TH `="risk_features"` 走风控特征解读，两条业务路径共存不互相污染。

---

## 0. 元信息

### 0.1 v5 → v6 关键差异

| 维度 | v5（NCB placeholder，已废） | v6（A1 双模式 risk_features） |
|---|---|---|
| TH 业务模型认知 | NCB 信用局 + FICO 评分 + account 列表 | **风控特征聚合表**（13 列内部聚合特征） |
| TH `source_display_name` | `"National Credit Bureau (NCB, Thailand)"` | **`"风控特征聚合表（泰国）"`** |
| TH `score_band_thresholds` | `(("A",720),("B",620),("C",540),("D",0))` DEV-PLACEHOLDER | **`()`**（空元组，永久不适用） |
| TH `account_type_labels` | 9 项 DEV-PLACEHOLDER | **`{}`**（空字典，永久不适用） |
| `CreditCountryPack` dataclass | 9 字段（不变） | **+3 字段**：`profile_mode` / `risk_feature_labels` / `sentinel_values` |
| `profile_mode` 字段 | 不存在 | **新增**：`Literal["buro", "risk_features"]`，MX 默认 `"buro"`，TH 显式 `"risk_features"` |
| `risk_feature_labels` 字段 | 不存在 | **新增**：`dict[str, str]`，TH 填 11 项中文标签，MX 空 |
| `sentinel_values` 字段 | 不存在 | **新增**：`dict[str, tuple[str, ...]]`，TH 填 3 类哨兵字符串，MX 空 |
| Phase 4 hard-gate | 替换 DEV-PLACEHOLDER 为 NCB 真值 | **禁止 NCB / DEV-PLACEHOLDER / 虚拟 score band / 虚拟 account type 残留** |
| explainer / feature_builder / decision_engine | 仅按 country pack 静态字段渲染 | **按 `pack.profile_mode` 分支**：`buro` 路径不变，`risk_features` 路径不读取 score_band / account_type，改用 risk_feature_labels + sentinel_values |
| Phase 1 任务 | 审核 NCB placeholder 假设 | 风控特征字段矩阵核对 + dataclass 扩展确认 || **CreditRawData contracts**（v6.1 路径 Q新增） | 仅 9 字段 dataclass 扩展，contracts 不动 | **+1 字段**：`risk_features_record: dict[str, Any] \| None`，mx 路径永远 `None`，th 路径 data_access 填充 11 维原始反欺诈特征 + 哨兵字符串（原状保留不转 None） |
| **Skill country_code 透传覆盖范围**（v6.1 修正） | 原计划 3 个 Skill | **6 个 Skill 全覆盖**：app / behavior / credit / **comprehensive** / **product_advice** / **ops_advice**，上游 3 + comprehensive + 2 建议 Skill 全走全链 country_code 透传 |
| **Orchestrator cache key**（v6.1 修正） | 3 元组升级 4 元组 | 4 元组不变，但调用点必改 5 处（不是 Plan v6 仅含 3 处方法定义描述） |
| **prompt 模板选择机制**（v6.1 修正） | 伪代码 `_read_template()`（不存在） | **`CreditExplainer.__init__` 变化**：接收 `prompt_paths: dict[str, Path]`（buro / risk_features 两份），`explain()` 内部按 `context.get("profile_mode")` 选模板（详见 §3.5） |
### 0.2 v6 字段值设计原则

| 字段类别 | 来源 | 上线限制 |
|---|---|---|
| 结构性字段（country_code / display_name / 语言 / contact_channel / contact_time / 发薪窗口） | 公开市场常识 | 直接上线 |
| TH 业务模型字段（profile_mode / risk_feature_labels / sentinel_values / source_display_name / currency_code） | csv 实测 schema + 公司业务命名 | 直接上线 |
| MX 业务模型字段（score_band_thresholds / account_type_labels / source_display_name） | mx 既有上线值 | 不改动 |
| TH 风控关键词（stage_keywords） | 泰语 + 英语 + 中文 + 业务术语 | 直接上线 |
| TH score_band_thresholds | **永久 `()`** — 不存在评分模型 | TH 不适用 |
| TH account_type_labels | **永久 `{}`** — 不存在账户类型 | TH 不适用 |

> **关键约束**：v6 **不存在** `# DEV-PLACEHOLDER` 占位字段。score_band_thresholds / account_type_labels 在 TH 路径下永久留空（不是占位），由 `profile_mode == "risk_features"` 显式声明数据语义。

### 0.3 用户决策（v6 / v6.1）

1. ✅ **路径 A**：复用既有 Legacy 注册表（最小侵入，沿用 v4）
2. ✅ **路径 A1**：CreditCountryPack 加 `profile_mode` / `risk_feature_labels` / `sentinel_values` 三个显式字段（v6 新增决策）
3. ✅ **路径 Q**：CreditRawData TypedDict 扩展 `risk_features_record: dict[str, Any] | None` 字段（v6.1 新增决策）。mx 路径永久 `None`，th 路径 data_access 填 11 维反欺诈特征原状数据（保留哨兵字符串不转 None）。跳出 `prepared_record` 唯一载体的限制，避免强套 mx Buró schema 。
4. ✅ **国别白名单**：V1 实际集合 `["mx", "th"]`（同步 PLANNING.md 第 341 行）
5. ✅ **TH 业务模型**：`profile_mode="risk_features"`，不生成虚拟 FICO 分，不生成虚拟 account type，score_band / account_type 永久空
6. ✅ **Skill 透传覆盖 6 个 Skill**：app / behavior / credit + **comprehensive / product_advice / ops_advice**。3 个上游 Skill + 1 个汇总 Skill + 2 个建议 Skill 全链透传 country_code（否则后 3 个 tab 在 th 路径下仍走 mx fallback，报告串味）
7. ✅ **本 Spec 标 LOCKED v6.1**：可进 Plan 05 Phase 2

---

## 1. 背景与目标

### 1.1 背景

- **mx 已上线**：3 个 country pack dataclass（`MX_APP_COUNTRY_PACK / MX_BEHAVIOR_COUNTRY_PACK / MX_CREDIT_COUNTRY_PACK`）+ Legacy 注册表 + `load_X_country_pack` 工厂均已就绪。
  - mx credit 数据（`New data/mex17/credit/mex17_withdraw_cdcdata_user_profile20260413.csv`）：35 列 Buró de Crédito 西语原始字段，含 FICO 评分（`valor`）+ 账户嵌套 JSON（`creditos_detail_json` 含 `tipocuenta=F/CC/...`）+ 查询嵌套 JSON（`consultas_detail_json`）。属于"信用局原始报告"业务模型。
- **th 现状**：
  - `app/country_packs/th/` 目录下仅有 `behavior_profile.py`（4 个常量：`TH_PAY_WINDOW={25-31, 1-3}` / `TH_PAY_CYCLE_NAME="เงินเดือน"` / `TH_PRIMARY_CHANNEL="LINE"` / `TH_PAY_CYCLE_DESCRIPTION="每月25-31号发薪"`）+ `__init__.py`（空文件），缺 `app_profile.py` / `credit_profile.py`，未注册到任何 `_X_COUNTRY_PACKS`。
  - th credit 数据（`New data/thai72/credit/thailand_72_withdraw_user_credit_profile_20260201_0430.csv`）：13 列**反欺诈风控聚合特征**（人脸活体分 / 通讯录 / 竞品 App / 7 天申请次数 / 历史结清/被拒 / 最大逾期天数 / 通讯录黑名单 / 银行卡关联 / 多头规则 / 逾期规则），**没有评分**，**没有账户类型**，**没有币种字段**。属于"风控特征聚合"业务模型 — 与 mx 完全不同。
- **Skill 层 country-agnostic**：`AppProfileSkill / BehaviorProfileSkill / CreditProfileSkill` 已通过 `build_X_run_context(country_code=...)` 透传 country pack，无需子类化。

### 1.2 目标

让用户在前端切换到 Thailand 后，后端 `/api/analyze` 透传 `country="th"` → `build_X_run_context` → `load_X_country_pack("th")` → 返回 `TH_X_COUNTRY_PACK` → Credit Skill 识别 `pack.profile_mode == "risk_features"` 走风控特征解读路径（不读取 score_band / account_type，改用 risk_feature_labels + sentinel_values + 专用 prompt 模板）。同时 mx 路径 `pack.profile_mode == "buro"` **行为零变更**。

### 1.3 非目标

- ❌ 抽象基类（`BaseCountryPack` / `BaseSkill[CountryT]` 等泛型）
- ❌ 工厂函数（`get_country_pack(TargetCountry)`）
- ❌ 字段 Adapter 类层级（`PassthroughAdapter` / `MexicoCreditAdapter` 等）
- ❌ Skill 子类化（`ThailandAppProfileSkill` 等）
- ❌ id / pk / ph / co / pe / cl / br 国家落地（V2+）
- ❌ 为 TH 生成虚拟 FICO / NCB score band（v5 失败教训）
- ❌ 为 TH 生成虚拟 account_type 映射（v5 失败教训）
- ❌ TH 风控授信结论 / KPI 数值化打分（V2+，本 V1 仅做 markdown 报告）

---

## 2. 字段对比矩阵（v6 全部锁定）

> **本节是 Plan 05 Phase 2 dataclass 代码块的唯一权威来源**。Phase 2 Task 2.0 / 2.1 / 2.2 / 2.3 必须严格按本节填值。

### 2.1 App 字段对比（`AppCountryPack`，v6 不变）

mx 实际定义（`app/country_packs/mx/app_profile.py`）含 5 个字段，th 完全同构：

| 字段名 | 类型 | mx 值 | th 值 | 一致？ | 适配落点 |
|---|---|---|---|---|---|
| `country_code` | str | `"mx"` | `"th"` | 不同（必然） | dataclass 实例 |
| `display_name` | str | `"Mexico"` | `"Thailand"` | 不同 | dataclass 实例 |
| `default_language` | str | `"zh-CN"` | `"zh-CN"` | ✅ 一致 | dataclass 实例 |
| `report_language` | str | `"zh-CN"` | `"zh-CN"` | ✅ 一致 | dataclass 实例 |
| `prompt_language` | str | `"zh-CN"` | `"zh-CN"` | ✅ 一致 | dataclass 实例 |

> `AppCountryPack` 当前未含业务字段，仅含元信息字段，因此 th 无需扩展 dataclass。

### 2.2 Behavior 字段对比（`BehaviorCountryPack`，v6 不变）

mx 实际定义（`app/country_packs/mx/behavior_profile.py`）含 11 个字段。th 完全同构（不扩展 dataclass 字段）：

| 字段名 | 类型 | mx 值 | th 值 | 一致？ | 适配落点 |
|---|---|---|---|---|---|
| `country_code` | str | `"mx"` | `"th"` | 不同（必然） | dataclass 实例 |
| `display_name` | str | `"墨西哥"` | `"泰国"` | 不同 | dataclass 实例 |
| `default_language` | str | `"zh-CN"` | `"zh-CN"` | ✅ 一致 | dataclass 实例 |
| `prompt_language` | str | `"zh-CN"` | `"zh-CN"` | ✅ 一致 | dataclass 实例 |
| `report_language` | str | `"zh-CN"` | `"zh-CN"` | ✅ 一致 | dataclass 实例 |
| `source_display_name` | str | `"Behavior Event Stream (MX)"` | `"Behavior Event Stream (TH)"` | 仅国家代码不同 | dataclass 实例 |
| `default_contact_channel` | str | `"WhatsApp"` | `"LINE"` | 不同（市场差异） | dataclass 实例 |
| `default_contact_time` | str | `"19:00-21:00"` | `"19:00-21:00"` | ✅ 一致 | dataclass 实例 |
| `stage_labels` | dict[str,str] | 6 项中文 | 同 mx 6 项中文 | ✅ 一致 | dataclass 实例 |
| `journey_section_labels` | dict[str,str] | 9 项中文 | 同 mx 9 项中文 | ✅ 一致 | dataclass 实例 |
| `stage_keywords` | dict[str,tuple[str,...]] | 5 组（西/英/中混合） | 5 组（**泰/英/中混合**） | 不同（本地化） | dataclass 实例 |
| `contact_channel_keywords` | dict[str,tuple[str,...]] | 4 渠道（WhatsApp/电话/短信/Push） | 4 渠道（**LINE 替换 WhatsApp**） | 不同 | dataclass 实例 |

**th `stage_labels`**（与 mx 一致，6 项）：
```python
{
    "acquisition": "拉新与注册阶段",
    "discovery": "产品浏览阶段",
    "application": "申请与认证阶段",
    "repayment": "还款与履约阶段",
    "support": "客服与触达阶段",
    "unknown": "其他行为阶段",
}
```

**th `journey_section_labels`**（与 mx 一致，9 项）：
```python
{
    "init": "初始化阶段",
    "basic_profile": "基础资料填写",
    "contact_entry": "联系人信息录入",
    "correction_retry": "反复尝试与格式纠错",
    "manual_fix": "密集手动修正",
    "dormancy_return": "深度流失/决策沉默",
    "bank_retry": "银行卡绑定重试",
    "offer_decision": "额度选择与权益决策",
    "unknown": "其他行为阶段",
}
```

**th `stage_keywords`**（5 组泰/英/中混合）：
```python
{
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
}
```

**th `contact_channel_keywords`**（LINE 替换 WhatsApp）：
```python
{
    "LINE": ("line", "line app", "line chat", "ไลน์"),
    "电话": ("call", "phone", "dial", "ivr", "voice", "โทร"),
    "短信": ("sms", "message", "text", "ข้อความ"),
    "App Push": ("push", "notification", "reminder", "แจ้งเตือน"),
}
```

### 2.3 Credit 字段对比（`CreditCountryPack`，v6 双模式 +3 字段）

mx 实际定义（`app/country_packs/mx/credit_profile.py`）含 9 个字段。**v6 扩展为 12 个字段**（保持向后兼容：所有新字段均提供默认值，mx 实例只填原 9 字段，新 3 字段自动取默认）。

| 字段名 | 类型 | mx 值 | th 值 | 一致？ | 适配落点 |
|---|---|---|---|---|---|
| `country_code` | str | `"mx"` | `"th"` | 不同（必然） | dataclass 实例 |
| `display_name` | str | `"墨西哥"` | `"泰国"` | 不同 | dataclass 实例 |
| `default_language` | str | `"zh-CN"` | `"zh-CN"` | ✅ 一致 | dataclass 实例 |
| `report_language` | str | `"zh-CN"` | `"zh-CN"` | ✅ 一致 | dataclass 实例 |
| `prompt_language` | str | `"zh-CN"` | `"zh-CN"` | ✅ 一致 | dataclass 实例 |
| `currency_code` | str | `"MXN"` | `"THB"` | 不同（货币） | dataclass 实例 |
| `source_display_name` | str | `"Buró de Crédito（墨西哥）"` | `"风控特征聚合表（泰国）"` | 不同（业务模型完全不同） | dataclass 实例 |
| `score_band_thresholds` | tuple[tuple[str,int],...] | `(("A",700),("B",580),("C",460),("D",0))` | **`()`**（永久空 — 不适用） | 不同 | dataclass 实例 |
| `account_type_labels` | dict[str,str] | 8 项 | **`{}`**（永久空 — 不适用） | 不同 | dataclass 实例 |
| **`profile_mode`**（v6 新） | Literal["buro", "risk_features"] | `"buro"`（默认） | **`"risk_features"`** | 不同（核心声明） | dataclass 实例 |
| **`risk_feature_labels`**（v6 新） | dict[str, str] | `{}`（默认） | **11 项中文标签**（详见 §2.5） | 不同 | dataclass 实例 |
| **`sentinel_values`**（v6 新） | dict[str, tuple[str, ...]] | `{}`（默认） | **3 项哨兵字符串**（详见 §2.6） | 不同 | dataclass 实例 |

**th `TH_CREDIT_COUNTRY_PACK` 完整定义**（v6 双模式锁定值，详见 §2.5/§2.6 见 risk_feature_labels / sentinel_values 内容）：

```python
TH_CREDIT_COUNTRY_PACK = CreditCountryPack(
    country_code="th",
    display_name="泰国",
    default_language="zh-CN",
    report_language="zh-CN",
    prompt_language="zh-CN",
    currency_code="THB",
    source_display_name="风控特征聚合表（泰国）",
    score_band_thresholds=(),                   # 永久空 — TH 数据不含评分模型
    account_type_labels={},                     # 永久空 — TH 数据不含账户类型
    profile_mode="risk_features",               # v6 新：显式声明业务模型
    risk_feature_labels={ ... },                # v6 新：见 §2.5
    sentinel_values={ ... },                    # v6 新：见 §2.6
)
```

**mx `MX_CREDIT_COUNTRY_PACK`**（v6 行为零变更 — 新 3 字段使用默认值）：

```python
# app/country_packs/mx/credit_profile.py 现状（v6 仅扩展 dataclass 类型，实例字面量不动）
MX_CREDIT_COUNTRY_PACK = CreditCountryPack(
    country_code="mx",
    display_name="墨西哥",
    default_language="zh-CN",
    report_language="zh-CN",
    prompt_language="zh-CN",
    currency_code="MXN",
    source_display_name="Buró de Crédito（墨西哥）",
    score_band_thresholds=(("A", 700), ("B", 580), ("C", 460), ("D", 0)),
    account_type_labels={
        "CC": "信用卡", "TC": "信用卡", "TDC": "信用卡",
        "F": "零售信贷",
        "M": "个人贷款", "PL": "个人贷款",
        "AUTO": "车贷", "HOME": "房贷",
    },
    # profile_mode / risk_feature_labels / sentinel_values 新字段使用默认值（"buro" / {} / {}）
    # 不必显式赋值，dataclass 自动填充。
)
```

### 2.4 不一致字段适配方案

| 字段 | 不一致原因 | 适配方案 | 负责文件 |
|---|---|---|---|
| `country_code` | 国家代码本质不同 | dataclass 实例字面量 `"th"` | `app/country_packs/th/{app,behavior,credit}_profile.py` |
| `display_name` | 中英文国名 | dataclass 实例字面量 | 同上 |
| `currency_code` | MXN→THB | dataclass 实例字面量 `"THB"` | `app/country_packs/th/credit_profile.py` |
| `source_display_name` (Behavior) | 数据源标识 | dataclass 实例字面量 `"Behavior Event Stream (TH)"` | `app/country_packs/th/behavior_profile.py` |
| `source_display_name` (Credit) | **业务模型完全不同** — TH 是风控聚合表不是 NCB | dataclass 实例字面量 `"风控特征聚合表（泰国）"` | `app/country_packs/th/credit_profile.py` |
| `default_contact_channel` | WhatsApp→LINE | dataclass 实例字面量 `"LINE"` | `app/country_packs/th/behavior_profile.py` |
| `stage_keywords` | 业务术语本地化 | dataclass 实例（详见 §2.2） | `app/country_packs/th/behavior_profile.py` |
| `contact_channel_keywords` | LINE 替换 WhatsApp | dataclass 实例（详见 §2.2） | `app/country_packs/th/behavior_profile.py` |
| `score_band_thresholds` (Credit) | TH 数据**不含评分模型** | **永久 `()`** + `profile_mode="risk_features"` 显式声明 | `app/country_packs/th/credit_profile.py` |
| `account_type_labels` (Credit) | TH 数据**不含账户类型** | **永久 `{}`** + `profile_mode="risk_features"` 显式声明 | `app/country_packs/th/credit_profile.py` |
| `profile_mode` (v6 新) | 业务模型声明 | mx 默认 `"buro"`，th 显式 `"risk_features"` | `app/country_packs/{mx,th}/credit_profile.py` |
| `risk_feature_labels` (v6 新) | TH 风控特征中文别名 | dataclass 实例（详见 §2.5），mx 默认 `{}` | `app/country_packs/th/credit_profile.py` |
| `sentinel_values` (v6 新) | TH 哨兵字符串语义化 | dataclass 实例（详见 §2.6），mx 默认 `{}` | `app/country_packs/th/credit_profile.py` |
| 发薪窗口 / 周期名称 / 周期描述 | 已存在 4 常量于现有 th/behavior_profile.py | 直接复用 `TH_PAY_WINDOW` / `TH_PAY_CYCLE_NAME="เงินเดือน"` / `TH_PAY_CYCLE_DESCRIPTION="每月25-31号发薪"` | `app/country_packs/th/behavior_profile.py`（已存在，不动） |

### 2.5 TH 风控特征字段表（`risk_feature_labels`）

> 数据来源：`New data/thai72/credit/thailand_72_withdraw_user_credit_profile_20260201_0430.csv` 实测 13 列（含 user_uuid / apply_uuid 2 个键列 → 11 个业务特征）。
>
> 字段名采用 csv 列名前缀（下划线前段），TH explainer 用本字典将原始列名映射成中文别名喂给 LLM prompt。

```python
risk_feature_labels = {
    # 身份核验类
    "liveness_score": "人脸活体识别分数（防伪反欺诈）",
    # 申请行为类
    "apply_7d_num": "近 7 天贷款申请次数",
    "apply_refuse_num": "历史申请被拒次数",
    "cashloan_app_num": "设备已安装的现金贷竞品 App 数量",
    # 还款履约类
    "finished_assets_num": "历史已结清贷款笔数",
    "max_yuqi_days": "历史最大逾期天数",
    # 社交关系类
    "contact_num": "通讯录联系人总数",
    "is_contact_black": "通讯录是否包含黑名单联系人（0/1）",
    "bankcard_user_num": "银行卡关联账户数量",
    # 规则命中类
    "rule_hit_多头规则拦截": "多头借贷规则是否命中",
    "rule_hit_逾期未结清拦截": "逾期未结清规则是否命中",
}
```

> **业务分组提示**（仅注释，不进 dataclass）：身份核验（1）/ 申请行为（3）/ 还款履约（2）/ 社交关系（3）/ 规则命中（2）= 11 项，对应 Phase 3 Task 3.6.5 中 explainer prompt 5 段结构。

### 2.6 TH 哨兵值定义（`sentinel_values`）

> 数据来源：csv 实测唯一值统计。TH 数据存在以下字符串哨兵值（不是 null / 空字符串），LLM prompt 必须显式说明语义，否则会被误解读为有效数值。

```python
sentinel_values = {
    "liveness_score": ("无活体分",),         # 用户未通过/未进行人脸活体识别
    "max_yuqi_days": ("无逾期",),             # 历史无任何逾期记录
    "rule_hit_多头规则拦截": ("无记录",),    # 规则未触发或无判定数据
    "rule_hit_逾期未结清拦截": ("无记录",),  # 规则未触发或无判定数据
}
```

> **关键约定**：
> 1. data_access 层**不做** sentinel 字符串到 None 的转换（保留原字符串送给下游）
> 2. feature_builder 在生成 evidence 时按 `sentinel_values` 字典识别哨兵 → 标记为 "未观察到此特征"
> 3. explainer prompt 模板（Phase 3 Task 3.6.5 新建）必须解释每个哨兵字符串的业务含义，避免 LLM 把 `"无活体分"` 误判为低分

### 2.7 v6 上线 hard-gate（替换 v5 DEV-PLACEHOLDER 规则）

> v5 hard-gate 的方向是"上线前替换 NCB placeholder 为真值"——这个方向因业务建模错误而废弃。v6 hard-gate 的方向是**禁止 NCB 伪征信语义残留**。

```powershell
# Phase 4 Task 4.4 必跑 — 命中任意一条立即中断 [complete]
$bad = Select-String -Path app/country_packs/th/ -Pattern "National Credit Bureau|NCB|DEV-PLACEHOLDER" -Recurse
$count = ($bad | Measure-Object).Count
if ($count -gt 0) {
    $bad | Format-Table Path,LineNumber,Line
    Write-Host "❌ Hard-gate 失败：TH risk_features 路径不允许残留 NCB / DEV-PLACEHOLDER 语义"
    exit 1
}

# 同时跑 Python 运行时断言：profile_mode 与空字段保护
python -c "
from app.country_packs.credit_profile import load_credit_country_pack
p = load_credit_country_pack('th')
assert p.profile_mode == 'risk_features', f'TH must be risk_features, got {p.profile_mode}'
assert p.score_band_thresholds == (), f'TH score_band must be empty, got {p.score_band_thresholds}'
assert p.account_type_labels == {}, f'TH account_type must be empty, got {p.account_type_labels}'
assert p.source_display_name == '风控特征聚合表（泰国）', f'TH source must be 风控特征聚合表, got {p.source_display_name}'
assert p.risk_feature_labels, f'TH risk_feature_labels must be non-empty'
assert p.sentinel_values, f'TH sentinel_values must be non-empty'
print('✅ TH risk_features hard-gate passed')
"
```

> **执行守则**：以上两个 gate 必须全绿（exit 0 + Python assert 0 fail）才允许 [complete] commit。

---

## 3. 设计原则

### 3.1 核心：复用既有 Legacy 注册表

> v6 不引入任何新抽象层，完全复用 `app/country_packs/{app,behavior,credit}_profile.py` 中已存在的注册表 + 工厂模式。

#### 3.1.1 既有注册表结构（mx 已验证）

```python
# app/country_packs/credit_profile.py（既有）
from app.country_packs.mx.credit_profile import MX_CREDIT_COUNTRY_PACK, CreditCountryPack

_CREDIT_COUNTRY_PACKS: dict[str, CreditCountryPack] = {
    MX_CREDIT_COUNTRY_PACK.country_code: MX_CREDIT_COUNTRY_PACK,
}

def load_credit_country_pack(country_code: str) -> CreditCountryPack:
    pack = _CREDIT_COUNTRY_PACKS.get(country_code)
    if pack is None:
        logger.warning("Unknown country_code=%s, fallback to mx", country_code)
        return MX_CREDIT_COUNTRY_PACK
    return pack
```

#### 3.1.2 v6 新增（每个 X_profile.py 仅 +1 行）

```python
# app/country_packs/credit_profile.py（v6 +1 行 import + 1 行 dict）
from app.country_packs.mx.credit_profile import MX_CREDIT_COUNTRY_PACK, CreditCountryPack
from app.country_packs.th.credit_profile import TH_CREDIT_COUNTRY_PACK  # NEW

_CREDIT_COUNTRY_PACKS: dict[str, CreditCountryPack] = {
    MX_CREDIT_COUNTRY_PACK.country_code: MX_CREDIT_COUNTRY_PACK,
    TH_CREDIT_COUNTRY_PACK.country_code: TH_CREDIT_COUNTRY_PACK,  # NEW
}
```

### 3.2 dataclass 单例规范（v6 CreditCountryPack 扩展）

- **类型**：`@dataclass(frozen=True)`，country-shared
- **位置**：dataclass 类型定义在 `mx/{X}_profile.py`（保持与 mx 既有约定）；th 单例 `import` 该 dataclass 类型，不重复定义
- **命名**：`{COUNTRY}_{X}_COUNTRY_PACK`
- **导出**：`app/country_packs/{country}/__init__.py` 统一 `__all__` 导出

#### 3.2.1 v6 CreditCountryPack 扩展定义（`app/country_packs/mx/credit_profile.py`）

```python
"""Mexico Credit Profile country pack (shared dataclass type)."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class CreditCountryPack:
    """Static country configuration used by the Credit profile pipeline.

    v6: 引入 profile_mode 双模式：
      - "buro": MX 信用局原始报告解读（FICO 评分 + 账户列表）
      - "risk_features": TH 风控特征聚合解读（11 维特征 + 哨兵值）
    """

    country_code: str
    display_name: str
    default_language: str
    report_language: str
    prompt_language: str
    currency_code: str
    source_display_name: str
    score_band_thresholds: tuple[tuple[str, int], ...]
    account_type_labels: dict[str, str] = field(default_factory=dict)
    # v6 新增字段（必须有默认值，向后兼容 mx 现有实例）
    profile_mode: Literal["buro", "risk_features"] = "buro"
    risk_feature_labels: dict[str, str] = field(default_factory=dict)
    sentinel_values: dict[str, tuple[str, ...]] = field(default_factory=dict)
```

> **向后兼容保证**：mx 实例字面量不需要传 `profile_mode` / `risk_feature_labels` / `sentinel_values`，dataclass 自动填默认值（`"buro"` / `{}` / `{}`）。mx 行为零变更。

### 3.3 Skill 类保持 country-agnostic，但需最小透传 country_code

> `AppProfileSkill / BehaviorProfileSkill / CreditProfileSkill` 保持 country-agnostic（不新增 Thailand 子类），但现有 3 个 Skill 的 `analyze(uid, **kwargs)` **并未**把 `country_code` 传给 `build_X_run_context`。这会导致即使路由和 orchestrator 传了 country_code，Skill 也会 fallback 到 `settings.default_country_code`（mx）。因此必须补上最小透传。

#### 3.3.1 当前代码问题（需修复）

```python
# app/runtime_skills/app_profile_agent.py（现状）
context = build_app_run_context(
    uid,
    application_time=application_time,
    source_preference=settings.data_source,
    enable_llm_explanation=True,
    # ⚠️ 没有 country_code= 参数 → fallback 到 default_country_code (mx)
)
```

#### 3.3.2 v6 修复后（3 Skill 同构）

```python
async def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
    repository = kwargs.get("repository")
    application_time = kwargs.get("application_time")
    country_code = kwargs.get("country_code")  # NEW
    context = build_app_run_context(
        uid,
        application_time=application_time,
        country_code=country_code,  # NEW
        source_preference=settings.data_source,
        enable_llm_explanation=True,
    )
    ...
```

#### 3.3.3 Orchestrator 需在 kwargs 注入 country_code

```python
# app/services/orchestrator.py::_run_single_module
kwargs: dict = {"uid": uid, "repository": self.repository, "country_code": country_code}  # NEW
```

> Skill 类本身的 `name / stage / depends_on / __init__` 均不变（CLAUDE.md Zero Tolerance 不动 BaseSkill 接口签名）。

### 3.4 后端入口 + 前端切换

- **后端 — 三个路由都要加 country**：主路径是 `/api/analyze-module`（GET，渐进加载），仅改 `/api/analyze`（POST）不够：
  - `app/schemas/request.py::AnalyzeRequest.country: Literal["mx", "th"] = "mx"`
  - `app/api/analyze_module.py::analyze_user_module(country: Literal["mx", "th"] = Query("mx"))`
  - `app/api/analyze_stream.py` / `app/services/batch_service.py` 透传 `request.country`
  - `app/services/orchestrator.py::analyze / analyze_module / _run_single_module / _analyze_comprehensive_module / _analyze_advisory_module` 全链路透传 country_code + cache key 加 country 维度
  - 3 个 Skill `analyze()` 从 `kwargs.get("country_code")` 读出后传给 `build_X_run_context(country_code=...)`
- **前端 — React useState 而非 useResultStore**：`app/static/js/app.jsx` 顶层 `country` state（含 URL `?country=` 持久化） + Header dropdown + 切换二次确认 + `resetAnalysisStateForCountry()` 局部函数清空 6 个 state。**不依赖**不存在的 `useResultStore.clearAll()`。

### 3.5 `profile_mode` 分支策略（v6 新增 + v6.1 路径 Q 实现细化 — 最关键设计点）

> Credit Profile 内部三个层（feature_builder / decision_engine / explainer）必须按 `pack.profile_mode` 分支处理。否则即使 country_code 传到 TH，仍会因为代码默认假设 buro 模型而读取空的 score_band / account_type → 报错或生成错误业务结论。
>
> **v6.1 实现细化**：CreditExplainer / CreditFeatureBuilder 不手写 `_read_template()` 函数（v6 占位）。按现有 explainer 代码结构，`CreditExplainer.__init__` 由接收单个 `prompt_path: Path` 改为接收 `prompt_paths: dict[str, Path]`（键 ∈ {"buro", "risk_features"}），`explain()` 内部按 `context.get("profile_mode")` 从字典选模板路径。`CreditProfileSkill.__init__` 在实例化 explainer 时传两条 prompt 路径。同时 `build_credit_run_context` 返回的 dict 必须添 `"profile_mode"` 键（值取自 pack.profile_mode）。

#### 3.5.1 `profile_mode == "buro"`（mx 路径）

- **行为零变更**：保持当前所有逻辑
- **可读字段**：`score_band_thresholds` / `account_type_labels` / `currency_code` / `source_display_name`
- **不读字段**：`risk_feature_labels` / `sentinel_values`（默认空，读了也无效）
- **prompt 模板**：`app/prompts/credit_profile_prompt.md`（既有）

#### 3.5.2 `profile_mode == "risk_features"`（th 路径）

- **新增逻辑**（Phase 3 Task 3.6.5）：
  - **不读取** `score_band_thresholds`（永久空 `()`）
  - **不读取** `account_type_labels`（永久空 `{}`）
  - **使用** `risk_feature_labels` 把原始列名映射为中文别名供 prompt 引用
  - **使用** `sentinel_values` 解释 `"无活体分"` / `"无逾期"` / `"无记录"` 等哨兵字符串语义
  - **不生成虚拟 FICO 分**、**不生成虚拟 account_type**
- **prompt 模板**：`app/prompts/credit_profile_th_prompt.md`（Phase 3 Task 3.6.5 新建），按 5 段结构组织：身份核验 / 申请行为 / 还款履约 / 社交关系 / 规则命中
- **explainer 选模板逻辑**：

```python
# app/runtime_skills/credit_profile/explainer.py（v6 改造示意）
def select_prompt_template(pack: CreditCountryPack) -> str:
    if pack.profile_mode == "risk_features":
        return _read_template("credit_profile_th_prompt.md")
    return _read_template("credit_profile_prompt.md")  # buro 默认
```

#### 3.5.3 feature_builder / decision_engine 同步分支

- `feature_builder` 在生成 `CreditFeatureBundle` 时若 `pack.profile_mode == "risk_features"`：
  - 跳过 score_band 分箱
  - 跳过 account_type 聚合
  - 改为生成 11 维 risk_feature evidence + sentinel 标记
- `decision_engine` 同理：buro 路径生成"信用等级 A/B/C/D"，risk_features 路径生成"风险信号清单"

> 具体函数签名 / 数据契约由 Phase 3 Task 3.6.5 实施时落 ADR；本 Spec 锁定**分支必须存在**，分支细节实施时定。

---

## 4. 数据流

```
[Frontend]
   │
   │ GET /api/analyze-module?uid=...&module=credit&country=th（主路径）
   │ POST /api/analyze body: {uid, country: "th", ...}
   ▼
[Backend Routes]
   │
   │ Pydantic Literal["mx", "th"] 强制校验
   ▼
[Orchestrator]
   │
   │ analyze_module(uid, module, application_time, country_code)
   │ cache key = (uid, module, application_time, country_code) 4 元组
   ▼
[Skill.analyze(uid, **kwargs)]
   │
   │ country_code = kwargs.get("country_code")
   │ context = build_credit_run_context(uid, country_code=country_code, ...)
   ▼
[build_credit_run_context(uid, country_code="th")]
   │
   │ pack = load_credit_country_pack("th")  → 返回 TH_CREDIT_COUNTRY_PACK (profile_mode="risk_features")
   ▼
[Credit Skill 内部分支（v6 新增）]
   │
   │ if pack.profile_mode == "risk_features":
   │     feature_builder._build_risk_features(raw_data, pack.risk_feature_labels, pack.sentinel_values)
   │     decision_engine._derive_risk_signals(feature_bundle)
   │     explainer._render(prompt_template="credit_profile_th_prompt.md", pack)
   │ else:  # "buro"
   │     feature_builder._build_buro(raw_data, pack.score_band_thresholds, pack.account_type_labels)
   │     decision_engine._derive_credit_grade(feature_bundle)
   │     explainer._render(prompt_template="credit_profile_prompt.md", pack)
   ▼
[Final API Response]
```

---

## 5. 前端国家切换器

### 5.1 顶层 country state

- **位置**：`app/static/js/app.jsx`（顶层入口；DashboardView/HomeView 通过 props 接收）
- **来源**：`URLSearchParams.get("country")`，仅接受 `"mx"` / `"th"`
- **持久化**：`useEffect` 监听 `country` 变化 → `window.history.replaceState` 写回 URL

### 5.2 Header dropdown

- **选项**：`[{value: "mx", label: "Mexico (mx)"}, {value: "th", label: "Thailand (th)"}]`
- **切换**：onChange 触发 confirm modal「切换国家会清空当前分析结果，是否继续？」→ 确认后调本地 `resetAnalysisStateForCountry()` + `setCountry(next)`

### 5.3 fetch 透传

- `analyzeModule(targetUid, moduleName, normalizedApplicationTime, country)`：第 4 形参，拼到 `/api/analyze-module?...&country=` query
- `analyzeByUid` / `analyzeByUidStream`：POST body 加 `country: country || "mx"`
- `analyzeByFile`（FormData 模式）：要么 `formData.append("country", country)` + 后端 `/api/analyze-file` 同步加 country，要么明示「文件批量模式 V1 暂不支持国家切换」并在 UI 提示。Phase 3 二选一并落地。

### 5.4 stale state 防护（React state 而非 store）

```jsx
function resetAnalysisStateForCountry() {
    setAnalysisResults([]);
    setSelectedResultIndex(0);
    setModuleStates(createInitialModuleStates());
    setModuleStatesByUid({});
    setErrorMessage("");
    setTraceSeedByUid({});
}
```

避免 mx 结果残留在 th 视图（货币符号 / 国名 / 联系渠道 / **profile_mode 分支结果** 显示错位）。

---

## 6. 字段适配落点（v6 4 层）

> v6 在 v4/v5 的 3 层落点基础上新增第 4 层（profile_mode 分支），用以隔离两种业务模型。

### 6.1 落点 1：`data_access.py`（数据层）

适用场景：th 数据库列名 / 类型与 mx 不同。

```python
def load_credit_data(uid: str, country_code: str) -> CreditRawData:
    if country_code == "mx":
        rows = repo.query_mx_buro(uid)
        return _normalize_buro_rows(rows)
    if country_code == "th":
        rows = repo.query_th_risk_features(uid)
        return _normalize_th_risk_rows(rows)  # 保留 sentinel 字符串不转 None
    raise ValueError(f"Unsupported country: {country_code}")
```

### 6.2 落点 2：`XCountryPack` 业务字段（配置层）

适用场景：相同字段语义，但业务阈值 / 标签 / 文案因国家不同；以及 v6 双模式声明。

```python
# v6 CreditCountryPack 12 字段（含 profile_mode / risk_feature_labels / sentinel_values）
```

### 6.3 落点 3：业务下游（feature_builder / explainer / assembler）

- `explainer.py` 调用 LLM 时，按 `pack.profile_mode` 选 prompt 模板
- `assembler.py` 输出报告时，按 `pack.profile_mode` 决定 markdown 章节模板（buro 5 段 vs risk_features 5 段，章节标题不同）

### 6.4 落点 4：`profile_mode` 分支（v6 新增）+ 路径 Q contracts 扩展（v6.1 新增）

适用场景：业务模型本质不同（不仅仅是字段值差异），需要在 feature_builder / decision_engine / explainer 三层显式分支。

```python
# 通用模式
if pack.profile_mode == "risk_features":
    handle_th_risk_features_path(...)
else:
    handle_buro_path(...)  # buro 默认
```

#### 6.4.1 路径 Q 下 CreditRawData 扩展（v6.1 决策）

> mx prepared_record schema（`profile_header / summary / delinquency / inquiries / account_details / score / repayment_timeline / source_meta`）是典型 Buró 信用局原始报告载体。**TH 风控特征聘合表没有任何一个字段能被填入 prepared_record 的任何子节点**。强套（如 `summary["liveness_score"]=...）会给 mx feature_builder 带来噪音。

**路径 Q 决策**：`CreditRawData` TypedDict 增加一个独立字段 `risk_features_record: dict[str, Any] | None`。

```python
# v6.1 后的 CreditRawData
class CreditRawData(TypedDict):
    uid: str
    country_code: str
    source_meta: dict[str, Any]
    prepared_record: CreditPreparedRecord  # mx 填真值；th 填 build_empty_prepared_record 占位
    risk_features_record: dict[str, Any] | None  # NEW：mx 永 None；th 填 11 维原始风控特征 + 哨兵字符串
    data_status: str
    errors: list[str]
```

**两路径数据流对照**：

```
mx (profile_mode="buro"):
  CreditDataProvider.fetch → raw_payload → prepare_credit_record_from_payload →
    CreditRawData{prepared_record: 真值, risk_features_record: None}
  → feature_builder._build_buro_features (现有逻辑) → 现有 CreditFeatureBundle

th (profile_mode="risk_features"):
  CreditDataProvider.fetch → raw_payload → _normalize_th_risk_features
    (保留哨兵字符串原状不转 None) →
    CreditRawData{prepared_record: empty_placeholder, risk_features_record: 11维 dict}
  → feature_builder._build_risk_features (v6.1 新逻辑) → CreditFeatureBundle
```

**feature_builder 分支入口**：

```python
class CreditFeatureBuilder:
    def build(self, raw_data: CreditRawData, context: CreditRunContext) -> CreditFeatureBundle:
        if context.get("profile_mode") == "risk_features":
            return self._build_risk_features(raw_data, context)
        return self._build_buro_features(raw_data, context)  # 现有逻辑 — 函数名重命名，内部逻辑 0 动
```

> 落点 4 + 路径 Q 是 v5 → v6.1 的关键架构升级 — 把“国家差异”从“字段值差异”升级为“业务模型 + 原始载体 schema 双重差异”，避免代码默认假设 buro 模型读取空字段报错，同时不给 mx 路径带来任何噪音。

---

## 7. Harness 12 层影响

| 层 | v5 影响 | v6 影响 | 说明 |
|---|---|---|---|
| 1. Identity | 无 | 无 | 用户身份不变 |
| 2. Authentication | 无 | 无 | 鉴权不变 |
| 3. Authorization | 无 | 无 | 鉴权不变 |
| 4. Routing | 轻微（country query） | 同 | `/api/analyze-module` 等路由加 country 参数 |
| 5. Throttling | 无 | 无 | 流控策略不分国家 |
| 6. Tracing | 轻微（country tag） | 同 | trace_id 不变；可在日志加 country 字段 |
| 7. Tool | 注册表 +1 行 | 同 | 删除 Adapter 抽象 |
| 8. Memory | cache key 加 country | 必做 | `_module_cache` key 4 元组（uid, module, application_time, country_code） |
| 9. Reasoning | LLM prompt 用 country pack 字段 | **profile_mode 分支选 prompt 模板** | v6 新：buro → 既有模板，risk_features → th 专用模板（Phase 3 Task 3.6.5 新建） |
| 10. Action | 无 | 无 | 输出动作不变 |
| 11. Output | 报告语言 / 货币按 country pack | **profile_mode 分支选章节结构** | buro 5 段 vs risk_features 5 段（身份核验/申请行为/还款履约/社交关系/规则命中） |
| 12. Audit | 审计日志含 country | 同（可加 profile_mode） | 日志加字段 |

**v6 净影响**：Reasoning + Output 层从"配置驱动"升级为"profile_mode 分支驱动"；Tool / Memory 层与 v5 相同。

---

## 8. 性能 / 安全

### 8.1 性能

- **country pack load 开销**：dict O(1) 查表 + dataclass(frozen=True) 单例 → 可忽略
- **profile_mode 分支判断开销**：单次属性读取 + if/else，纳秒级
- **数据库查询**：data_access 按 country 走不同 query 已是既有架构，v6 不改

### 8.2 安全

- **Pydantic 强制白名单**：`country: Literal["mx", "th"]` schema 阻止任意字符串注入
- **Fallback warning**：未知 country 自动 fallback mx + WARN log（既有，v6 不改）
- **凭据隔离**：data_access 内部按 country 走不同凭据已是既有架构，v6 不改
- **profile_mode 类型保护**：`Literal["buro", "risk_features"]` 在 dataclass 层强制，无效值直接构造时报错
- **PLANNING.md zero tolerance 遵守**：未脱敏凭据不进 prompt / 日志 / API 响应

---

## 9. 验收 / 测试

### 9.1 单元测试

#### 9.1.1 th risk-features country pack（v6 新断言）

文件：`tests/country_packs/test_th_country_packs.py`（新建）

| 用例 | 断言 |
|---|---|
| `load_app_country_pack("th")` | `pack.country_code == "th"` + `pack.display_name == "Thailand"` |
| `load_behavior_country_pack("th")` | `pack.default_contact_channel == "LINE"` + `pack.display_name == "泰国"` + `"ลงทะเบียน" in pack.stage_keywords["acquisition"]` |
| `load_credit_country_pack("th")` 双模式断言 | `pack.profile_mode == "risk_features"` + `pack.source_display_name == "风控特征聚合表（泰国）"` + `pack.currency_code == "THB"` + `pack.score_band_thresholds == ()` + `pack.account_type_labels == {}` + `pack.risk_feature_labels` 非空（11 项） + `pack.sentinel_values` 非空 + `"liveness_score" in pack.risk_feature_labels` + `pack.sentinel_values["liveness_score"] == ("无活体分",)` |
| `load_credit_country_pack("mx")` 行为零变更 | `pack.profile_mode == "buro"` + `pack.score_band_thresholds[0] == ("A", 700)`（既有值） + `pack.account_type_labels["CC"] == "信用卡"` + `pack.risk_feature_labels == {}` + `pack.sentinel_values == {}` |
| `load_credit_country_pack("xx")` fallback mx | `pack.country_code == "mx"` + `pack.profile_mode == "buro"` |

#### 9.1.2 cache mx/th 隔离

文件：`tests/test_orchestrator_country_cache.py`（新建）

| 用例 | 断言 |
|---|---|
| `_set_cached(uid, module, app_time, "mx", payload)` | 同 uid+module+app_time 下 `_get_cached(..., "th")` 返回 None |
| mx 和 th payload 同时存在 | 不互相覆盖 |

#### 9.1.3 profile_mode 分支单测（v6 新）

文件：`tests/runtime_skills/test_credit_profile_mode_branching.py`（新建，Phase 3 Task 3.6.5 落地后）

| 用例 | 断言 |
|---|---|
| `select_prompt_template(MX_CREDIT_COUNTRY_PACK)` | 返回 `credit_profile_prompt.md` |
| `select_prompt_template(TH_CREDIT_COUNTRY_PACK)` | 返回 `credit_profile_th_prompt.md` |
| feature_builder 在 risk_features 模式 | 不调用 `_score_band_bin()` 函数 |
| feature_builder 在 buro 模式 | 不调用 `_risk_feature_label_lookup()` 函数 |

### 9.2 集成测试

- mx 全量 pytest（Phase 0 baseline + Phase 2/3/4 三道回归）
- 通过数 N₀（baseline）→ Phase 2 后 ≥ N₀ + 5（test_th_country_packs.py 新增 5 用例）→ Phase 3 后 ≥ N₀ + 6（test_orchestrator_country_cache.py 新增 1 用例）→ Phase 3 末 ≥ N₀ + 10（test_credit_profile_mode_branching.py 新增 4 用例）

### 9.3 人工 E2E

- 浏览器切到 Thailand → 输入 th UID（或 mock）→ 4 tab 全部正常
- App tab 显示 "Thailand"
- Behavior tab 联系渠道 LINE
- **Credit tab**：货币 THB；source_display_name 显示「风控特征聚合表（泰国）」；**不显示 score_band 等级**；**不显示 account_type 列表**；显示 5 段 markdown：身份核验 / 申请行为 / 还款履约 / 社交关系 / 规则命中
- Comprehensive tab summary 引用上述无矛盾，**不**生成虚拟信用等级

### 9.4 Phase 4 上线 hard-gate

```powershell
# Gate 1：禁止 NCB / DEV-PLACEHOLDER 残留
$bad = Select-String -Path app/country_packs/th/ -Pattern "National Credit Bureau|NCB|DEV-PLACEHOLDER" -Recurse
($bad | Measure-Object).Count  # 必须 = 0

# Gate 2：profile_mode + 空字段保护运行时断言
python -c "from app.country_packs.credit_profile import load_credit_country_pack; p = load_credit_country_pack('th'); assert p.profile_mode == 'risk_features' and p.score_band_thresholds == () and p.account_type_labels == {} and p.source_display_name == '风控特征聚合表（泰国）' and p.risk_feature_labels and p.sentinel_values"
```

> Gate 1 + Gate 2 必须全绿才允许 [complete] commit。

---

## 10. v3 → v4 → v5 → v6 决策记录

> 详见 Plan 05 v6 附录 Z。本节摘录关键决策。

### 10.1 v3 BLOCKED 原因

1. v3 `BaseCountryPack` 抽象层与既有 `_X_COUNTRY_PACKS` 注册表正交但冗余
2. Plan 03/05 国别白名单冲突未处理（拉美 6 vs 亚洲 5，交集仅 {mx, th}）
3. v3 Schema Adapter 类层级把字段适配分散到 4 个地方
4. Phase 数 6 违反"每 Plan ≤4 commit"教训
5. 时机错误：4 BUG 未修复 + mx StarRocks 数据未导入

### 10.2 v4 决策（路径 A）

- 走路径 A：复用既有注册表 + dataclass 单例
- 删除 BaseCountryPack / TargetCountry / get_country_pack / Schema Adapter / Skill 子类
- Phase 数 6 → 5（4 个实施 commit）
- PLANNING.md 第 341 行修正为 V1 实际集合 `["mx", "th"]`

### 10.3 v4 BLOCKED for Claude Code 原因

- v4 §2 字段矩阵 4 张表全空 → Phase 1 阻塞用户提供 schema → Claude Code 无法 self-contained 执行

### 10.4 v5 BLOCKED 原因（业务建模错误）

- v5 把 TH credit 错认为 NCB 信用局报告
- 设计了 FICO 风格 placeholder（A/B/C/D 评分阈值 + 9 项 account_type_labels）
- DEV-PLACEHOLDER hard-gate 方向是"上线前替换为 NCB 真值"
- **实际 TH 数据是公司内部反欺诈风控聚合表**，不存在 NCB / FICO 模型 → v5 整套 placeholder 是业务建模错误
- 用户审核 csv 实测后改方向

### 10.5 v6 决策（A1 双模式）

- 走路径 A1：CreditCountryPack 加 3 个显式字段（`profile_mode` / `risk_feature_labels` / `sentinel_values`）
- TH `profile_mode = "risk_features"`，MX `profile_mode = "buro"`（默认）
- TH `score_band_thresholds = ()` / `account_type_labels = {}` 永久空（不是 placeholder）
- TH `source_display_name = "风控特征聚合表（泰国）"`
- explainer / feature_builder / decision_engine 按 `pack.profile_mode` 分支
- Phase 4 hard-gate 重写：禁止 NCB / DEV-PLACEHOLDER / 虚拟 score / 虚拟 account 残留
- Plan / commit 节奏保 v5（5 Phase / 4 commit）
### 10.6 v6.1 决策（路径 Q + 5 CRITICAL 代码对齐）

- 走路径 Q：`CreditRawData` 添 `risk_features_record: dict | None` 独立字段（v6 中伪代码 `_read_template()` 不可用）
- `CreditExplainer.__init__` 由 `prompt_path: Path` 改为 `prompt_paths: dict[str, Path]`，`explain()` 按 `context["profile_mode"]` 选模板
- `build_credit_run_context` 返回 dict 增 `profile_mode` 键（值来自 pack）
- Skill 透传覆盖范围从 3 个扩到 6 个（+ comprehensive / product_advice / ops_advice）
- orchestrator cache key 调用点 5 处全列出（`_run_single_module` ×1 + `_analyze_comprehensive_module` ×4 + `_analyze_advisory_module` ×2）
- `app/schemas/request.py` import 补 `Literal`，`/api/analyze-file` 同步 `country: Literal["mx","th"] = Form("mx")`
- v6.1 hard-gate Python 片段抽出为 `scripts/v6_hard_gate.py` 独立脚本，避免跨平台引号转义
### 10.6 既有架构对齐

| 维度 | 既有架构（mx 已落地） | v6 决策 |
|---|---|---|
| 注册位置 | `_X_COUNTRY_PACKS: dict[str, XCountryPack]` | 沿用 |
| 单例形式 | `MX_X_COUNTRY_PACK = XCountryPack(country_code="mx", ...)` | th 同构 |
| Skill 路由 | `AppProfileSkill` country-agnostic + `build_X_run_context(country_code)` | 保持 |
| 字段适配 | `data_access.py` + `XCountryPack` 业务字段 | **+ profile_mode 分支落点 4** |
| 工厂函数 | `load_X_country_pack(country_code) -> XCountryPack` | 沿用（不引入 enum） |
| dataclass | mx 9 字段 | **mx 12 字段（向后兼容）+ th 12 字段（双模式）** |
| 业务值来源 | mx：业务团队既有定义 | th：csv 实测 + Q1-Q5 用户决策（risk_features 模式） |

> v6 完全对齐既有架构 + 显式声明业务模型（profile_mode）；解决 v5 业务建模错误问题，Claude Code 插件可自动 / 半自动执行 5 个 Phase。
