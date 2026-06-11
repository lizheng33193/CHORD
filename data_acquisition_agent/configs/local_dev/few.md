# 本地开发 — Few-shot 示例（local MySQL `user_profile`）

> 本地开发模式下，SQL 明确分成两类：  
> 1. **cohort discovery**：只找 UID，不能直接用于 `/execute` 写 bucket  
> 2. **bucket extraction**：字段满足目标 bucket 契约，可直接送 `/execute`

## A. Cohort Discovery 示例

### 示例 A1：抽 5 个有 App 数据的用户

**自然语言**：帮我查 5 个墨西哥用户

```sql
SELECT DISTINCT uid
FROM app_install_list
LIMIT 5;
```

### 示例 A2：抽 3 个三方数据齐全的用户

**自然语言**：找 3 个数据齐全的墨西哥用户

```sql
SELECT DISTINCT a.uid
FROM app_install_list AS a
INNER JOIN behavior_events AS b ON a.uid = b.uid
INNER JOIN credit_report_raw AS c ON a.uid = c.uid
LIMIT 3;
```

### 示例 A3：找安装了金融类 App 的用户

**自然语言**：查装了金融 App 的墨西哥用户

```sql
SELECT DISTINCT uid
FROM app_install_list
WHERE gp_category = '金融'
   OR ai_category_level_2_CN IN ('移动银行', '借贷', '钱包')
LIMIT 10;
```

### 示例 A4：找最近 7 天活跃用户

**自然语言**：查最近 7 天活跃用户

```sql
SELECT DISTINCT uid
FROM behavior_events
WHERE FROM_UNIXTIME(servertimestamp / 1000) >= DATE_SUB(NOW(), INTERVAL 7 DAY)
LIMIT 10;
```

### 示例 A5：找高风险征信用户

**自然语言**：查高风险征信用户

```sql
SELECT DISTINCT uid
FROM credit_report_raw
WHERE CAST(valor AS DECIMAL(10, 2)) < 600
   OR NULLIF(TRIM(razones), '') IS NOT NULL
LIMIT 10;
```

---

## B. Bucket Extraction 示例

### 示例 B1：抽取 App bucket 明细

**自然语言**：把 5 个有 App 数据的用户 App 明细取出来

```sql
SELECT
  uid,
  app_name,
  app_package,
  first_install_time,
  last_update_time,
  gp_category,
  ai_category_level_2_CN
FROM app_install_list
WHERE uid IN (
  SELECT DISTINCT uid
  FROM app_install_list
  LIMIT 5
)
ORDER BY uid, app_package
LIMIT 1000;
```

### 示例 B2：抽取 Behavior bucket 明细

**自然语言**：把最近活跃用户的行为轨迹取出来

```sql
SELECT
  uid,
  servertimestamp,
  timestamp_,
  scenetype,
  processtype,
  eventname,
  extend,
  clientmodel,
  clientosversion,
  url,
  refer,
  ip
FROM behavior_events
WHERE uid IN (
  SELECT DISTINCT uid
  FROM behavior_events
  WHERE FROM_UNIXTIME(servertimestamp / 1000) >= DATE_SUB(NOW(), INTERVAL 7 DAY)
  LIMIT 5
)
ORDER BY uid, servertimestamp
LIMIT 5000;
```

### 示例 B3：抽取 Credit bucket 明细

**自然语言**：把高风险征信用户的原始征信字段取出来

```sql
SELECT
  uid,
  user_uuid,
  apply_risk_id,
  valor,
  nombrescore,
  razones,
  consultas_detail_json,
  creditos_detail_json
FROM credit_report_raw
WHERE CAST(valor AS DECIMAL(10, 2)) < 600
   OR NULLIF(TRIM(razones), '') IS NOT NULL
ORDER BY uid
LIMIT 1000;
```

---

## 强约束

- **所有 SQL 都必须 `SELECT uid`**
- **cohort discovery SQL** 只能用于找 UID，不能直接拿去写 `app/behavior/credit` bucket
- **bucket extraction SQL** 必须满足目标 bucket 字段契约后，才能送 `/execute`
- app bucket 字段名必须精确包含 `ai_category_level_2_CN`
- 不要用生产数仓表名（`hive.*`、`dwd_*`、`dwb_*`、`dm_model.*`）
- 默认带 `LIMIT`，避免全表扫描
