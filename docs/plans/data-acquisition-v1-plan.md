# data_acquisition_agent V1 Implementation Plan

> Design Doc: docs/specs/data_acquisition_agent.md

## Context

`data_acquisition_agent` Step 3 已落 Stub（caed309），demo0 已脱敏入 git（764a647）。本 Plan 把 9 个 Stub 方法转为可工作实现，按 Phase 0 → Phase 8 顺序 TDD 驱动，严格遵守 Design Doc §5 错误契约和 §7 安全双层防御。

## Scope

**In Scope（V1）**
- Phase 0–8 实现：`mexico.yaml` 真实路径 + 9 个运行时模块 + 单元测试 + mock e2e + `app/main.py include_router` + `POST /api/data-acquisition/generate`
- Design Doc §5 错误类型全覆盖：`bad_request` / `prompt_too_large` / `schema_validation_failed` / `credential_leak` / `dangerous_code` / `ddl_policy_violation` / `upstream_llm_error`

**Out of Scope（V1 不做）**
- real LLM smoke 测试（`test_smoke_real_llm_mexico.py` Stub 保留 pytest skip，本 Plan 不实现）
- `GET /manifests`、`GET /healthz` endpoint（Stub 保持 501，本 Plan 不实现也不写测试）
- 前端 UI、SQL/Python 实际执行、数据库连接、数据落地、RAG、多轮对话、非墨西哥国家验证、`preferred_table_name`

**Future Optional（不阻塞 V1）**
- real LLM smoke pytest marker 启用
- manifests / healthz 两个 debug endpoint
- 印尼 / 巴铁 / 泰国 / 菲律宾 manifest 真实路径填充
- 在 system_prompt 中显式声明 artifact 安全契约（"生成的 SQL/Python 仅为待审核 artifact，不会被自动执行；分析师需人工审核 → 限定在 `analyst_private_prefix` 私有 schema → 跑通后才入流程"），降低模型生成破坏性语句倾向（V1 已通过 output_scanner 守门，这条是纵深防御补强）
- V1 交付后启用 `test_smoke_real_llm_mexico.py`，建立 3-5 条 Golden Case（预期 SQL 含 `MEX017`、含 `HAVING`、不含明文凭据）作为 Prompt 调优基线评测集

## Worked Example（预期输入输出）

**正常请求 (200)**
```json
POST /api/data-acquisition/generate
{"natural_language_request": "建表墨西哥 mob1 取 100 uid", "target_country": "mexico"}

→ {"request_id": "uuid", "sql": "SELECT uid FROM ...", "sql_kind": "query_only",
   "audit_report": {"high_risk_ddl": false, "final_verdict": "ok"},
   "metadata": {"knowledge_files_loaded": ["5 files"], "redaction_events": 0}}
```

**错误请求 (400)**
```json
{"natural_language_request": "x", "target_country": "indonesia"}
→ {"error_type": "bad_request", "message": "placeholder field", "request_id": "uuid"}
```

## 关键决策（已与用户确认）

1. L1 redactor 第 5 类 `user='e_*'` 仅匹配带引号字面量，避免 SQL `e_id` 业务字段误伤
2. token 估算用中英文加权（中文 ×1.5），无第三方依赖
3. LLM 错误分流：`json_parse` / `json_repair_failed` / `schema_validation_failed` 前缀 → 422 `schema_validation_failed`；其余 model_error → 502 `upstream_llm_error`
4. DDL 检测：先剥 `--` 行注释和 `/* */` 块注释，再做大小写不敏感关键字 `\b(CREATE|DROP|ALTER|TRUNCATE|INSERT|UPDATE|DELETE)\b` 匹配
5. `mexico.yaml` 写相对 repo 根的字符串路径，`manifest.py` 负责转 `Path` 与存在性校验
6. e2e 测试用构造注入 `ModelClient` 参数（`DataAcquisitionOrchestrator(model_client=stub)`），不依赖全局 `settings`
7. token 阈值 800,000

---

## Phase 0 — mexico.yaml 真实路径

### Task 0.0 — 添加 pyyaml 依赖
**目标**：requirements.txt 当前不含 PyYAML，manifest 加载需要 yaml.safe_load。

- **Files Modify**: `requirements.txt`
- **Files Test**: 无（依赖文件改动，由 Task 2.1 测试间接验证 import 成功）

**TDD 步骤**
- Step 1：跳过（依赖声明，无独立测试；正确性由 Task 2.1 `from data_acquisition_agent.manifest import load_manifest` 间接验证）
- Step 2：跳过
- Step 3：在 `requirements.txt` 第 8 行 `google-genai>=1.0.0,<2.0` 之后追加：
  ```
  pyyaml>=6.0,<7.0
  ```
- Step 4：双重验证：
  1. `python -c "from pathlib import Path; assert 'pyyaml' in Path('requirements.txt').read_text(encoding='utf-8').lower()"` → 预期无输出（assert 不抛错即 PASS）
  2. `python -c "import yaml; print(yaml.__version__)"` → 预期打印 6.x 版本号（环境验证；若未安装则先运行 `python -m pip install -r requirements.txt`）
- Step 5：`git add requirements.txt && git commit -m "chore: add pyyaml dependency for da-agent manifest loader"`

**不允许**：升级其他依赖、删除现有条目
**完成标准**：`python -c "import yaml"` 不报错

### Task 0.1 — 填 mexico.yaml 真实知识库路径
**目标**：把 6 个 `<PLACEHOLDER_...>` 替换为 demo0 真实相对路径。

- **Files Modify**: `data_acquisition_agent/configs/mexico.yaml`
- **Files Test**: 无（路径有效性留 Phase 2 manifest 测试断言）

**TDD 步骤**
- Step 1：跳过（YAML 数据填充，无独立测试；正确性由 Phase 2 `test_manifest.py::test_mexico_manifest_loads` 间接验证）
- Step 2：跳过
- Step 3：用 Edit 把 mexico.yaml 6 行占位符替换为：
  ```yaml
  business_logic_md: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/多国业务逻辑.md
  all_examples_md: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/all_examples .md
  schema_md: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/scheme.md
  few_md: data_acquisition_agent/demo0/各国数据知识库汇总/墨西哥/few.md
  system_prompt_md: data_acquisition_agent/demo0/system_prompt.md
  analyst_private_prefix: dm_model.yyp_tmp_
  ```
- Step 4：`python -c "import yaml; print(yaml.safe_load(open('data_acquisition_agent/configs/mexico.yaml', encoding='utf-8')))"` → 预期 dict 含上述 5 个 md 路径 + `analyst_private_prefix='dm_model.yyp_tmp_'`
- Step 5：`git add data_acquisition_agent/configs/mexico.yaml && git commit -m "feat(da-agent): fill mexico.yaml real knowledge paths"`

**不允许**：修改 demo0 内文件、改 yaml schema 字段名、新增字段
**完成标准**：yaml.safe_load 成功，5 个 md 路径都能 `Path.exists()`

---

## Phase 1 — schemas.py validators

### Task 1.1 — sql/python 至少一非空 validator
- **Files Modify**: `data_acquisition_agent/schemas.py`
- **Files Create**: `data_acquisition_agent/tests/test_schemas.py`（覆盖 placeholder）

**TDD 步骤**
- Step 1：在 test_schemas.py 写最小失败测试：
  ```python
  import pytest
  from pydantic import ValidationError
  from data_acquisition_agent.schemas import GenerateResponse, AuditReport, GenerateMetadata

  def _meta():
      return GenerateMetadata(model="m", token_estimate=0, knowledge_files_loaded=[], redaction_events=0, danger_scan_events=0, generated_at="t")

  def test_sql_and_python_both_empty_rejected():
      with pytest.raises(ValidationError):
          GenerateResponse(request_id="r", target_country="mexico", reasoning_summary="x", sql=None, python=None, audit_report=AuditReport(high_risk_ddl=False, final_verdict="ok"), metadata=_meta())

  def test_error_response_round_trip():
      """ErrorResponse 必须有 error_type / message / request_id 三字段，可被 model_dump(mode='json') 序列化"""
      from data_acquisition_agent.schemas import ErrorResponse, ErrorType
      e = ErrorResponse(error_type=ErrorType.CREDENTIAL_LEAK, message="x", request_id="rid-1")
      d = e.model_dump(mode="json")
      assert d["error_type"] == "credential_leak"
      assert d["message"] == "x"
      assert d["request_id"] == "rid-1"
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_schemas.py::test_sql_and_python_both_empty_rejected -v` → 预期 FAIL（当前无 validator）
- Step 3：在 GenerateResponse 类内添加 model_validator，并确认/补齐 ErrorResponse model（字段：`error_type: ErrorType`、`message: str`、`request_id: str = ""`）：
  ```python
  from pydantic import model_validator
  @model_validator(mode="after")
  def _at_least_one_artifact(self):
      if not (self.sql or self.python):
          raise ValueError("sql and python cannot both be empty")
      return self
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_schemas.py -v` → 预期 2 case PASS（_at_least_one_artifact + ErrorResponse round-trip）
- Step 5：`git add data_acquisition_agent/schemas.py data_acquisition_agent/tests/test_schemas.py && git commit -m "feat(da-agent): require sql or python non-empty"`

**不允许**：修改其他 model、删除 TODO 注释（留给 1.2）、加 sql_kind 联动逻辑
**完成标准**：2 case PASS

### Task 1.2 — sql_kind ↔ high_risk_ddl 联动 validator
- **Files Modify**: `data_acquisition_agent/schemas.py`
- **Files Modify**: `data_acquisition_agent/tests/test_schemas.py`

**TDD 步骤**
- Step 1：追加测试（≤ 3 case）：
  ```python
  def test_build_table_script_requires_high_risk_ddl_true():
      with pytest.raises(ValidationError):
          GenerateResponse(request_id="r", target_country="mexico", reasoning_summary="x",
              sql="CREATE TABLE dm_model.yyp_tmp_x AS SELECT 1", sql_kind="build_table_script",
              python=None, audit_report=AuditReport(high_risk_ddl=False, final_verdict="ok"), metadata=_meta())

  def test_query_only_with_high_risk_ddl_true_rejected():
      with pytest.raises(ValidationError):
          GenerateResponse(request_id="r", target_country="mexico", reasoning_summary="x",
              sql="SELECT 1", sql_kind="query_only", python=None,
              audit_report=AuditReport(high_risk_ddl=True, final_verdict="ok"), metadata=_meta())

  def test_sql_present_requires_sql_kind():
      with pytest.raises(ValidationError):
          GenerateResponse(request_id="r", target_country="mexico", reasoning_summary="x",
              sql="SELECT 1", sql_kind=None, python=None,
              audit_report=AuditReport(high_risk_ddl=False, final_verdict="ok"), metadata=_meta())
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_schemas.py -v` → 预期 3 个新 case FAIL
- Step 3：扩展 model_validator：
  ```python
  @model_validator(mode="after")
  def _sql_kind_audit_coupling(self):
      if self.sql and not self.sql_kind:
          raise ValueError("sql_kind required when sql is present")
      if self.sql_kind == "build_table_script" and not self.audit_report.high_risk_ddl:
          raise ValueError("build_table_script requires audit_report.high_risk_ddl=True")
      if self.sql_kind == "query_only" and self.audit_report.high_risk_ddl:
          raise ValueError("query_only must not set high_risk_ddl=True")
      return self
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_schemas.py -v` → 预期 5 个测试全 PASS（含 1.1 的 2 case + 1.2 的 3 case）
- Step 5：`git add data_acquisition_agent/schemas.py data_acquisition_agent/tests/test_schemas.py && git commit -m "feat(da-agent): sql_kind and high_risk_ddl coupling validators"`

**不允许**：在此处实现 SQL 内容扫描（属 Phase 4）
**完成标准**：5 个 test_schemas case PASS

---

## Phase 2 — manifest.py

### Task 2.1 — CountryManifest.from_yaml + load_manifest
- **Files Modify**: `data_acquisition_agent/manifest.py`
- **Files Modify**: `data_acquisition_agent/tests/test_manifest.py`

**TDD 步骤**
- Step 1：写测试：
  ```python
  from pathlib import Path
  import pytest
  from data_acquisition_agent.manifest import load_manifest, CountryManifest, ManifestNotImplemented

  def test_mexico_manifest_loads():
      m = load_manifest("mexico")
      assert m.country == "mexico"
      assert m.sql_dialect == "starrocks"
      assert m.analyst_private_prefix == "dm_model.yyp_tmp_"
      for p in (m.business_logic_md, m.all_examples_md, m.schema_md, m.few_md, m.system_prompt_md):
          assert isinstance(p, Path) and p.exists(), p

  def test_unknown_country_raises():
      with pytest.raises(FileNotFoundError):
          load_manifest("atlantis")

  def test_placeholder_country_raises_manifest_not_implemented():
      # indonesia.yaml 当前为 placeholder（路径未填或为 <PLACEHOLDER_*>）
      with pytest.raises(ManifestNotImplemented):
          load_manifest("indonesia")
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_manifest.py -v` → 预期 FAIL
- Step 3：实现（≤ 60 行）：
  ```python
  import yaml
  from dataclasses import dataclass
  CONFIG_DIR = Path(__file__).resolve().parent / "configs"
  REQUIRED_MD = ("business_logic_md","all_examples_md","schema_md","few_md","system_prompt_md")
  REQUIRED_FIELDS = REQUIRED_MD + ("country","display_name","sql_dialect","analyst_private_prefix")
  REPO_ROOT = Path(__file__).resolve().parent.parent

  class ManifestNotImplemented(Exception):
      """Raised when a country YAML is a placeholder/empty/missing required fields.
      Caller maps to ErrorType.BAD_REQUEST."""

  @dataclass
  class CountryManifest:
      country: str; display_name: str
      business_logic_md: Path; all_examples_md: Path; schema_md: Path
      few_md: Path; system_prompt_md: Path
      sql_dialect: str; analyst_private_prefix: str

      @classmethod
      def from_yaml(cls, path: Path) -> "CountryManifest":
          data = yaml.safe_load(path.read_text(encoding="utf-8"))
          if not isinstance(data, dict):
              raise ManifestNotImplemented(f"{path.name}: empty or non-dict yaml")
          for k in REQUIRED_FIELDS:
              if k not in data or data[k] is None:
                  raise ManifestNotImplemented(f"{path.name}: missing field {k}")
              if isinstance(data[k], str) and data[k].startswith("<PLACEHOLDER"):
                  raise ManifestNotImplemented(f"{path.name}: placeholder field {k}")
          kwargs = {k: REPO_ROOT / data[k] for k in REQUIRED_MD}
          for k, p in kwargs.items():
              if not p.exists():
                  raise ManifestNotImplemented(f"{path.name}: {k} path does not exist {p}")
          return cls(country=data["country"], display_name=data["display_name"],
              sql_dialect=data["sql_dialect"], analyst_private_prefix=data["analyst_private_prefix"], **kwargs)

  def load_manifest(country: str) -> CountryManifest:
      p = CONFIG_DIR / f"{country}.yaml"
      if not p.exists(): raise FileNotFoundError(p)
      return CountryManifest.from_yaml(p)

  def list_registered_countries() -> list[str]:
      return sorted(p.stem for p in CONFIG_DIR.glob("*.yaml"))
  ```
- Step 4：同命令 → 预期 PASS（3 case）
- Step 5：`git add data_acquisition_agent/manifest.py data_acquisition_agent/tests/test_manifest.py && git commit -m "feat(da-agent): implement CountryManifest YAML loader"`

**不允许**：实现 prompt 拼装、读取 md 内容
**完成标准**：3 个 test PASS

---

## Phase 3 — redactor.py

### Task 3.1 — redact() credential patterns
- **Files Modify**: `data_acquisition_agent/redactor.py`
- **Files Modify**: `data_acquisition_agent/tests/test_redactor.py`

**TDD 步骤**
- Step 1：写测试（合成假凭据，文档保留 IP）：
  ```python
  import pytest
  from data_acquisition_agent.redactor import redact

  CASES = [
      ("host='192.0.2.10'", "<DB_HOST>", "ip"),
      ("port=3306", "<DB_PORT>", "port"),
      ("user='e_fake_user'", "<DB_USER>", "user"),
      ("password='FAKE_PASSWORD_REDACTED'", "<DB_PASSWORD>", "password"),
      ("database='dm_fake_db'", "<DB_NAME>", "db"),
      ("token='abc123XYZ_fake'", "<TOKEN>", "token"),
      ("api_key='sk-FAKE'", "<API_KEY>", "api_key"),
      ("access_token='FAKE_AT'", "<ACCESS_TOKEN>", "access_token"),
      ("secret='FAKE_SECRET'", "<SECRET>", "secret"),
      ("Authorization: Bearer FAKE_BEARER_TOKEN", "<BEARER_TOKEN>", "bearer"),
      ("key='FAKE_KEY_VALUE'", "<KEY>", "key"),
  ]
  @pytest.mark.parametrize("raw,placeholder,label", CASES)
  def test_redact_each_pattern(raw, placeholder, label):
      out, hits = redact(raw)
      assert placeholder in out, f"{label}: {out}"
      assert hits >= 1

  def test_redact_does_not_touch_sql_select_field():
      out, hits = redact("SELECT e_id, e_phone FROM t")
      assert out == "SELECT e_id, e_phone FROM t"
      assert hits == 0

  def test_redact_word_boundary_no_false_positive_report_eq_3306():
      out, hits = redact("report=3306 AND export=3306")
      assert "<DB_PORT>" not in out
      assert hits == 0

  def test_redact_word_boundary_no_false_positive_user_uuid():
      out, hits = redact("SELECT user_uuid FROM t WHERE user_id=1")
      assert out == "SELECT user_uuid FROM t WHERE user_id=1"
      assert hits == 0

  def test_redact_does_not_touch_english_prose_password_word():
      # 英文文档中提到 password 字段名但未赋值，不应误报
      out, hits = redact("the password field is required and must be at least 8 chars")
      assert hits == 0
      assert "<DB_PASSWORD>" not in out
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_redactor.py -v` → 预期 FAIL
- Step 3：实现：
  ```python
  import re
  PATTERNS = [
      (re.compile(r"\bhost\s*=\s*'(?:\d{1,3}\.){3}\d{1,3}'"), "host='<DB_HOST>'"),
      (re.compile(r"\bport\s*=\s*\d{2,6}\b"), "port=<DB_PORT>"),
      (re.compile(r"\buser\s*=\s*'e_[A-Za-z0-9_]*'"), "user='<DB_USER>'"),
      (re.compile(r"\bpassword\s*=\s*'[^']*'"), "password='<DB_PASSWORD>'"),
      (re.compile(r"\bdatabase\s*=\s*'dm_[A-Za-z0-9_]*'"), "database='<DB_NAME>'"),
      (re.compile(r"\btoken\s*=\s*'[^']+'"), "token='<TOKEN>'"),
      (re.compile(r"\bapi_key\s*=\s*'[^']+'"), "api_key='<API_KEY>'"),
      (re.compile(r"\baccess_token\s*=\s*'[^']+'"), "access_token='<ACCESS_TOKEN>'"),
      (re.compile(r"\bsecret\s*=\s*'[^']+'"), "secret='<SECRET>'"),
      (re.compile(r"\bkey\s*=\s*'[^']+'"), "key='<KEY>'"),
      (re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+\S+"), "Authorization: Bearer <BEARER_TOKEN>"),
  ]
  def redact(text: str) -> tuple[str, int]:
      hits = 0
      for pat, repl in PATTERNS:
          text, n = pat.subn(repl, text); hits += n
      return text, hits
  def redact_file(path: str) -> tuple[str, int]:
      from pathlib import Path
      return redact(Path(path).read_text(encoding="utf-8"))
  ```
- Step 4：同命令 → 预期 15 个 case PASS（11 parametrize + 4 false-positive 边界）
- Step 5：`git add data_acquisition_agent/redactor.py data_acquisition_agent/tests/test_redactor.py && git commit -m "feat(da-agent): L1 credential redactor for db and secret patterns"`

**不允许**：扫描 LLM 输出（属 Phase 4）、写回磁盘
**完成标准**：15 个 case PASS

---

## Phase 4 — output_scanner.py

### Task 4.1 — scan_credentials（L2 凭据回扫）
- **Files Modify**: `data_acquisition_agent/output_scanner.py`
- **Files Modify**: `data_acquisition_agent/tests/test_output_scanner.py`

**TDD 步骤**
- Step 1：写测试：
  ```python
  from data_acquisition_agent.output_scanner import scan_credentials
  def test_scan_finds_ip_and_password():
      hits = scan_credentials("conn(host='198.51.100.10', password='FAKE_SECRET_REDACTED')")
      assert any("host" in h for h in hits)
      assert any("password" in h for h in hits)
  def test_scan_clean_text():
      assert scan_credentials("SELECT 1") == []
  def test_scan_finds_token_and_bearer():
      hits = scan_credentials("api_key='sk-FAKE'\nAuthorization: Bearer FAKE_AT")
      assert "api_key" in hits and "bearer" in hits
  def test_scan_clean_does_not_match_report_eq_3306():
      assert scan_credentials("report=3306") == []
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_output_scanner.py -v` → 预期 FAIL
- Step 3：实现：
  ```python
  import re

  # CRED_PATTERNS：基于 L1 PATTERNS 的相同 family，但允许 ' 或 " 包裹（输出层更宽松）
  CRED_PATTERNS = {
      "host": re.compile(r"\bhost\s*=\s*['\"](?:\d{1,3}\.){3}\d{1,3}['\"]"),
      "port": re.compile(r"\bport\s*=\s*\d{2,6}\b"),
      "user": re.compile(r"\buser\s*=\s*['\"]e_[A-Za-z0-9_]+['\"]"),
      "password": re.compile(r"\bpassword\s*=\s*['\"][^'\"]+['\"]"),
      "database": re.compile(r"\bdatabase\s*=\s*['\"]dm_[A-Za-z0-9_]+['\"]"),
      "token": re.compile(r"\btoken\s*=\s*['\"][^'\"]+['\"]"),
      "api_key": re.compile(r"\bapi_key\s*=\s*['\"][^'\"]+['\"]"),
      "access_token": re.compile(r"\baccess_token\s*=\s*['\"][^'\"]+['\"]"),
      "secret": re.compile(r"\bsecret\s*=\s*['\"][^'\"]+['\"]"),
      "key": re.compile(r"\bkey\s*=\s*['\"][^'\"]+['\"]"),
      "bearer": re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+\S+"),
  }
  def scan_credentials(text: str) -> list[str]:
      return [name for name, pat in CRED_PATTERNS.items() if pat.search(text)]
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_output_scanner.py -v` → 预期 4 case PASS
- Step 5：`git add data_acquisition_agent/output_scanner.py data_acquisition_agent/tests/test_output_scanner.py && git commit -m "feat(da-agent): L2 credential output scanner"`

**L1/L2 同源约定**：L1（redactor）与 L2（output_scanner）使用同一 credential family 清单（host / port / user / password / database / token / api_key / access_token / secret / key / bearer），各自独立 compile 正则，输出层 L2 在引号上更宽松。V1 不抽 shared registry，避免重构；新增 family 时须同步更新两侧 pattern + 两侧测试集。

**不允许**：在此处加 Python 黑名单或 SQL 策略
**完成标准**：4 case PASS

### Task 4.2 — scan_python_dangerous（黑名单）
- **Files Modify**: `output_scanner.py`, `tests/test_output_scanner.py`

**TDD 步骤**
- Step 1：测试：
  ```python
  from data_acquisition_agent.output_scanner import scan_python_dangerous
  import pytest
  DANGER = ["os.system('ls')", "subprocess.run(['x'], shell=True)", "eval('1+1')",
            "exec('x')", "__import__('os')", "shutil.rmtree('/')", "os.remove('/x')"]
  @pytest.mark.parametrize("code", DANGER)
  def test_blacklist_hits(code):
      assert scan_python_dangerous(code)
  def test_clean_python():
      assert scan_python_dangerous("import pandas as pd\ndf = pd.read_csv('x.csv')") == []
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_output_scanner.py -v` → 预期 FAIL
- Step 3：实现：
  ```python
  DANGEROUS = [
      re.compile(r"\bos\.system\("),
      re.compile(r"subprocess\.[A-Za-z_]+\([^)]*shell\s*=\s*True"),
      re.compile(r"\beval\("),
      re.compile(r"\bexec\("),
      re.compile(r"__import__\(\s*['\"]os['\"]"),
      re.compile(r"\bshutil\.rmtree\("),
      re.compile(r"\bos\.remove\("),
      re.compile(r"urllib\.request\.urlretrieve\("),
  ]
  def scan_python_dangerous(code: str) -> list[str]:
      return [pat.pattern for pat in DANGEROUS if pat.search(code)]
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_output_scanner.py -v` → 预期 8 case PASS
- Step 5：`git add data_acquisition_agent/output_scanner.py data_acquisition_agent/tests/test_output_scanner.py && git commit -m "feat(da-agent): python dangerous code blacklist"`

**完成标准**：8 case PASS

### Task 4.3 — check_sql_policy（DDL 二分策略）
- **Files Modify**: `output_scanner.py`, `tests/test_output_scanner.py`

**TDD 步骤**
- Step 1：测试：
  ```python
  from data_acquisition_agent.output_scanner import check_sql_policy
  import pytest

  def test_query_only_rejects_ddl():
      with pytest.raises(ValueError):
          check_sql_policy("DROP TABLE x", "query_only", "dm_model.yyp_tmp_")

  def test_query_only_allows_select():
      check_sql_policy("SELECT * FROM t", "query_only", "dm_model.yyp_tmp_")

  def test_query_only_ignores_ddl_in_comments():
      check_sql_policy("-- DROP TABLE x\nSELECT 1", "query_only", "dm_model.yyp_tmp_")

  def test_build_table_requires_prefix():
      with pytest.raises(ValueError):
          check_sql_policy("CREATE TABLE prod.x AS SELECT 1", "build_table_script", "dm_model.yyp_tmp_")

  def test_build_table_with_prefix_ok():
      check_sql_policy("CREATE TABLE dm_model.yyp_tmp_x AS SELECT 1", "build_table_script", "dm_model.yyp_tmp_")

  def test_build_table_drop_if_exists_with_prefix_ok():
      check_sql_policy("DROP TABLE IF EXISTS dm_model.yyp_tmp_x", "build_table_script", "dm_model.yyp_tmp_")

  # 新增：build_table_script 模式禁止其他 DML/DDL（即使表名带 prefix）
  @pytest.mark.parametrize("sql", [
      "DELETE FROM dm_model.yyp_tmp_x WHERE id=1",
      "INSERT INTO dm_model.yyp_tmp_x VALUES (1)",
      "UPDATE dm_model.yyp_tmp_x SET a=1",
      "TRUNCATE TABLE dm_model.yyp_tmp_x",
      "ALTER TABLE dm_model.yyp_tmp_x ADD COLUMN c INT",
  ])
  def test_build_table_rejects_non_create_drop_dml(sql):
      with pytest.raises(ValueError):
          check_sql_policy(sql, "build_table_script", "dm_model.yyp_tmp_")

  # 新增：DDL target 含反引号 / 双引号包裹时保守 reject
  @pytest.mark.parametrize("sql", [
      "CREATE TABLE `dm_model`.`yyp_tmp_x` AS SELECT 1",
      'CREATE TABLE "dm_model"."yyp_tmp_x" AS SELECT 1',
  ])
  def test_build_table_rejects_quoted_identifier(sql):
      with pytest.raises(ValueError):
          check_sql_policy(sql, "build_table_script", "dm_model.yyp_tmp_")
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_output_scanner.py -v` → 预期 FAIL
- Step 3：实现：
  ```python
  DDL_KW = re.compile(r"\b(CREATE|DROP|ALTER|TRUNCATE|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)
  # build_table_script 仅允许 CREATE TABLE [IF NOT EXISTS] <ident> AS SELECT ... 与 DROP TABLE [IF EXISTS] <ident>
  _ALLOWED_BUILD_STMT = re.compile(
      r"(?is)^\s*(?:CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+([A-Za-z_][\w.]*)\s+AS\s+(?:WITH\s+|SELECT\s+).+"
      r"|DROP\s+TABLE(?:\s+IF\s+EXISTS)?\s+([A-Za-z_][\w.]*)\s*;?\s*)$"
  )
  _QUOTED_IDENT = re.compile(r"`|\"")

  def _strip_sql_comments(sql: str) -> str:
      sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
      sql = re.sub(r"--[^\n]*", " ", sql)
      return sql

  def _split_statements(sql: str) -> list[str]:
      return [s for s in (s.strip() for s in sql.split(";")) if s]

  def check_sql_policy(sql: str, sql_kind: str, analyst_private_prefix: str) -> None:
      stripped = _strip_sql_comments(sql)
      if sql_kind == "query_only":
          if DDL_KW.search(stripped):
              raise ValueError("query_only contains DDL/DML keyword")
          return
      if sql_kind == "build_table_script":
          if not DDL_KW.search(stripped):
              raise ValueError("build_table_script must contain DDL")
          for stmt in _split_statements(stripped):
              m = _ALLOWED_BUILD_STMT.match(stmt)
              if not m:
                  raise ValueError(f"build_table_script disallows statement: {stmt[:60]}")
              target = m.group(1) or m.group(2)
              if _QUOTED_IDENT.search(target):
                  raise ValueError(f"build_table_script disallows quoted identifier: {target}")
              if not target.startswith(analyst_private_prefix):
                  raise ValueError(f"DDL target {target} not in analyst_private_prefix {analyst_private_prefix}")
          return
      raise ValueError(f"unknown sql_kind: {sql_kind}")
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_output_scanner.py -v` → 预期 13 case PASS（query_only 3 + build_table base 3 + 5 DML reject + 2 quoted reject）
- Step 5：`git add data_acquisition_agent/output_scanner.py data_acquisition_agent/tests/test_output_scanner.py && git commit -m "feat(da-agent): SQL DDL policy enforcement"`

**完成标准**：所有 test_output_scanner.py case PASS

---

## Phase 5 — prompt_assembler.py

### Task 5.1 — estimate_tokens（中英文加权）
- **Files Modify**: `data_acquisition_agent/prompt_assembler.py`
- **Files Modify**: `data_acquisition_agent/tests/test_prompt_assembler.py`

**TDD 步骤**
- Step 1：测试：
  ```python
  from data_acquisition_agent.prompt_assembler import estimate_tokens
  def test_english_close_to_quarter_chars():
      assert 3 <= estimate_tokens("hello world hello world") <= 8
  def test_chinese_weight_higher_than_english():
      en = estimate_tokens("a" * 100)
      zh = estimate_tokens("中" * 100)
      assert zh > en
  def test_empty_zero():
      assert estimate_tokens("") == 0
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_prompt_assembler.py -v` → 预期 FAIL
- Step 3：实现（≤ 10 行）：
  ```python
  def estimate_tokens(text: str) -> int:
      if not text: return 0
      cjk = sum(1 for c in text if '一' <= c <= '鿿')
      other = len(text) - cjk
      return int(cjk * 1.5 + other / 4)
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_prompt_assembler.py -v` → 预期 3 case PASS
- Step 5：`git add data_acquisition_agent/prompt_assembler.py data_acquisition_agent/tests/test_prompt_assembler.py && git commit -m "feat(da-agent): cjk-weighted token estimator"`

### Task 5.2 — assemble_prompt（拼装 + 脱敏 + 阈值护栏）
- **Files Modify**: `prompt_assembler.py`, `tests/test_prompt_assembler.py`

**TDD 步骤**
- Step 1：测试：
  ```python
  from data_acquisition_agent.prompt_assembler import assemble_prompt, TOKEN_LIMIT
  from data_acquisition_agent.manifest import load_manifest
  from data_acquisition_agent.schemas import GenerateRequest
  import pytest

  def test_assemble_mexico_includes_all_5_files():
      m = load_manifest("mexico")
      req = GenerateRequest(natural_language_request="建表 mob1 取 100 uid", target_country="mexico")
      prompt, tokens, files, redaction_hits = assemble_prompt(req, m)
      assert len(files) == 5
      assert tokens > 0
      assert "建表 mob1 取 100 uid" in prompt
      assert isinstance(redaction_hits, int)

  def test_assemble_redacts_synthetic_credentials(tmp_path):
      """构造含合成凭据的临时知识库 → 断 prompt 不含原文 + redaction_hits >= 2"""
      from data_acquisition_agent.manifest import CountryManifest
      def _w(name, body):
          p = tmp_path / name; p.write_text(body, encoding="utf-8"); return p
      sp = _w("sp.md", "ROLE")
      bl = _w("bl.md", "host='198.51.100.10'\npassword='FAKE_PASSWORD_XYZ'")
      ex = _w("ex.md", "examples")
      sc = _w("sc.md", "schema")
      fw = _w("fw.md", "few")
      m = CountryManifest(country="mexico", display_name="MX",
                          business_logic_md=bl, all_examples_md=ex, schema_md=sc,
                          few_md=fw, system_prompt_md=sp, sql_dialect="starrocks",
                          analyst_private_prefix="dm_model.yyp_tmp_")
      req = GenerateRequest(natural_language_request="x", target_country="mexico")
      prompt, _, _, hits = assemble_prompt(req, m)
      assert "198.51.100.10" not in prompt
      assert "FAKE_PASSWORD_XYZ" not in prompt
      assert hits >= 2

  def test_assemble_raises_when_over_limit(monkeypatch):
      m = load_manifest("mexico")
      req = GenerateRequest(natural_language_request="x", target_country="mexico")
      monkeypatch.setattr("data_acquisition_agent.prompt_assembler.TOKEN_LIMIT", 10)
      with pytest.raises(ValueError, match="prompt_too_large"):
          assemble_prompt(req, m)
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_prompt_assembler.py -v` → 预期 FAIL
- Step 3：实现：
  ```python
  from .redactor import redact
  TOKEN_LIMIT = 800_000
  def assemble_prompt(request, manifest):
      sections = []
      files = []
      total_hits = 0
      for label, p in [
          ("system_prompt", manifest.system_prompt_md),
          ("business_logic", manifest.business_logic_md),
          ("all_examples", manifest.all_examples_md),
          ("schema", manifest.schema_md),
          ("few", manifest.few_md),
      ]:
          raw = p.read_text(encoding="utf-8")
          red, hits = redact(raw)
          total_hits += hits
          sections.append(f"# === {label} ===\n{red}")
          files.append(str(p))
      user_block = (f"# === user_request ===\ncountry={request.target_country.value}\n"
                    f"action={request.target_action.value if request.target_action else 'auto'}\n"
                    f"request:\n{request.natural_language_request}\n\n"
                    "Return ONLY a JSON object with keys: reasoning_summary, sql, sql_kind, python, audit_report.\n"
                    "audit_report.high_risk_ddl must be true iff sql_kind=='build_table_script'.")
      sections.append(user_block)
      prompt = "\n\n".join(sections)
      tokens = estimate_tokens(prompt)
      if tokens > TOKEN_LIMIT:
          raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")
      return prompt, tokens, files, total_hits
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_prompt_assembler.py -v` → 预期 6 case PASS（含 5.1 的 3 case + 5.2 的 3 case）
- Step 5：`git add data_acquisition_agent/prompt_assembler.py data_acquisition_agent/tests/test_prompt_assembler.py && git commit -m "feat(da-agent): assemble redacted prompt with token guardrail"`

**不允许**：在 prompt 里写真实凭据、跳过 redact、修改 manifest
**完成标准**：6 case PASS（含 5.1 的 3 case + 5.2 的 3 case）

---

## Phase 6 — orchestrator.py

### Task 6.1 — OrchestratorError（含 request_id）+ 骨架与 happy path
- **Files Modify**: `data_acquisition_agent/orchestrator.py`
- **Files Create**: `data_acquisition_agent/tests/test_orchestrator.py`

**TDD 步骤**
- Step 1：测试（happy path + request_id 透传 + redaction_events/danger_scan_events 落 metadata）：
  ```python
  import pytest, re
  from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator, OrchestratorError
  from data_acquisition_agent.schemas import GenerateRequest, ErrorType

  class StubModelClient:
      mode = "mock"; model_name = "stub"
      def __init__(self, payload, status="ok"): self._p = payload; self._s = status
      def generate_structured(self, **kw):
          return {"status": self._s, "structured_result": self._p, "model_name": "stub", "prompt_preview": ""}

  PAYLOAD_OK = {"reasoning_summary": "x", "sql": "SELECT 1", "sql_kind": "query_only",
                "python": None, "audit_report": {"high_risk_ddl": False, "final_verdict": "ok"}}

  def test_happy_path():
      orch = DataAcquisitionOrchestrator(model_client=StubModelClient(PAYLOAD_OK))
      resp = orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
      assert resp.sql == "SELECT 1"
      assert resp.metadata.knowledge_files_loaded
      # request_id 是 uuid4 形态
      assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", resp.request_id)
      # demo0 已预脱敏，运行时 hits 可能为 0；只断非负，避免环境耦合（与 Task 5.2 同策略）
      assert isinstance(resp.metadata.redaction_events, int)
      assert resp.metadata.redaction_events >= 0
      assert resp.metadata.danger_scan_events == 0  # python is None, sql 干净
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_orchestrator.py -v` → 预期 FAIL
- Step 3：实现（OrchestratorError 类 + generate 主流程骨架，错误分流由 6.2/6.3 进一步完善）：
  ```python
  import uuid
  from datetime import datetime, timezone
  from app.core.logger import get_logger
  from app.core.model_client import ModelClient
  from .manifest import load_manifest, ManifestNotImplemented
  from .prompt_assembler import assemble_prompt, estimate_tokens
  from .output_scanner import scan_credentials, scan_python_dangerous, check_sql_policy
  from .schemas import (GenerateRequest, GenerateResponse, AuditReport, GenerateMetadata,
                        TokensUsed, ErrorType)
  logger = get_logger(__name__)

  class OrchestratorError(Exception):
      def __init__(self, error_type: ErrorType, message: str, request_id: str = ""):
          super().__init__(message)
          self.error_type = error_type
          self.message = message
          self.request_id = request_id

  _LLM_SCHEMA_HINTS = ("json_parse", "json_repair_failed", "schema_validation_failed")
  _RESPONSE_SCHEMA = {"type":"object","properties":{
      "reasoning_summary":{"type":"string"},"sql":{"type":["string","null"]},
      "sql_kind":{"type":["string","null"]},"python":{"type":["string","null"]},
      "audit_report":{"type":"object"}}}

  class DataAcquisitionOrchestrator:
      def __init__(self, model_client=None):
          self.model_client = model_client or ModelClient()
      def generate(self, request: GenerateRequest) -> GenerateResponse:
          rid = str(uuid.uuid4())
          try:
              manifest = load_manifest(request.target_country.value)
          except ManifestNotImplemented as e:
              raise OrchestratorError(ErrorType.BAD_REQUEST, str(e), request_id=rid)
          try:
              prompt, token_estimate, files, redaction_hits = assemble_prompt(request, manifest)
          except ValueError as e:
              raise OrchestratorError(ErrorType.PROMPT_TOO_LARGE, str(e), request_id=rid)
          fallback = {"reasoning_summary":"","sql":None,"sql_kind":None,"python":None,
                      "audit_report":{"high_risk_ddl":False,"final_verdict":""}}
          mr = self.model_client.generate_structured(skill_name="data_acquisition",
              prompt=prompt, fallback_result=fallback, response_schema=_RESPONSE_SCHEMA)
          if mr.get("status") != "ok":
              err = str(mr.get("structured_result", {}).get("model_error", ""))
              if any(h in err for h in _LLM_SCHEMA_HINTS):
                  raise OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED, err, request_id=rid)
              raise OrchestratorError(ErrorType.UPSTREAM_LLM_ERROR,
                                      err or "model_unavailable", request_id=rid)
          payload = mr["structured_result"]
          # 输出层凭据扫描 + Python 黑名单 + DDL 策略 → 见 Task 6.2
          danger_events = self._enforce_output_policies(payload, manifest, rid)
          # 组装 GenerateResponse → 见 Task 6.3
          return self._build_response(rid, request, payload, mr, token_estimate, files,
                                       redaction_hits, danger_events)

      # 6.1 最小 stub —— 6.2 / 6.3 会扩展
      def _enforce_output_policies(self, payload, manifest, rid: str) -> int:
          return 0
      def _build_response(self, rid, request, payload, mr, token_estimate, files,
                          redaction_hits, danger_events):
          return GenerateResponse(
              request_id=rid, target_country=request.target_country,
              reasoning_summary=payload.get("reasoning_summary",""),
              sql=payload.get("sql"), sql_kind=payload.get("sql_kind"),
              python=payload.get("python"),
              audit_report=AuditReport(**payload.get("audit_report", {})),
              metadata=GenerateMetadata(
                  model=mr.get("model_name",""), tokens_used=None,
                  token_estimate=token_estimate, knowledge_files_loaded=files,
                  redaction_events=redaction_hits,
                  danger_scan_events=danger_events,
                  generated_at=datetime.now(timezone.utc).isoformat()))
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_orchestrator.py -v` → 预期 1 case PASS（happy path + request_id + metadata）
- Step 5：`git add data_acquisition_agent/orchestrator.py data_acquisition_agent/tests/test_orchestrator.py && git commit -m "feat(da-agent): orchestrator skeleton with request_id"`

**不允许**：直接 import google.genai；连数据库；执行 SQL/Python；落盘
**完成标准**：1 case PASS，且 Phase 1-5 测试不回归

### Task 6.2 — _enforce_output_policies 扩展（凭据 / Python 黑名单 / DDL 策略）
- **Files Modify**: `data_acquisition_agent/orchestrator.py`, `data_acquisition_agent/tests/test_orchestrator.py`

**TDD 步骤**
- Step 1：测试（leak / dangerous_code / ddl_policy_violation 三类分流，全部带 request_id）：
  ```python
  def test_leak_in_python_rejected():
      bad = dict(PAYLOAD_OK, sql=None, python="conn(host='198.51.100.10', password='FAKE')")
      orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
      with pytest.raises(OrchestratorError) as ei:
          orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
      assert ei.value.error_type == ErrorType.CREDENTIAL_LEAK
      assert ei.value.request_id

  def test_dangerous_python_rejected():
      bad = dict(PAYLOAD_OK, sql=None, python="import os\nos.system('rm -rf /')")
      orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
      with pytest.raises(OrchestratorError) as ei:
          orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
      assert ei.value.error_type == ErrorType.DANGEROUS_CODE

  def test_ddl_policy_violation_in_query_only():
      bad = dict(PAYLOAD_OK, sql="DROP TABLE x", sql_kind="query_only")
      orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
      with pytest.raises(OrchestratorError) as ei:
          orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
      assert ei.value.error_type == ErrorType.DDL_POLICY_VIOLATION
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_orchestrator.py -v` → 预期 FAIL
- Step 3：实现：
  ```python
      def _enforce_output_policies(self, payload, manifest, rid: str) -> int:
          py = payload.get("python") or ""
          combined = (payload.get("sql") or "") + "\n" + py
          danger_events = 0
          cred_hits = scan_credentials(combined)
          if cred_hits:
              raise OrchestratorError(ErrorType.CREDENTIAL_LEAK,
                                      "credential pattern in artifact", request_id=rid)
          if py:
              py_hits = scan_python_dangerous(py)
              if py_hits:
                  raise OrchestratorError(ErrorType.DANGEROUS_CODE,
                                          "blacklist hit in python", request_id=rid)
          sql = payload.get("sql"); kind = payload.get("sql_kind")
          if sql and kind:
              try:
                  check_sql_policy(sql, kind, manifest.analyst_private_prefix)
              except ValueError as e:
                  raise OrchestratorError(ErrorType.DDL_POLICY_VIOLATION, str(e), request_id=rid)
          return danger_events  # V1 当前为 0；保留位以便后续累计 warning 类命中

      # 注：danger_scan_events 仅出现在成功响应的 metadata，表示成功 artifact 内 L2 命中数；V1 在
      # 命中（凭据 / 黑名单 / DDL 违规）时直接 raise OrchestratorError，不在 ErrorResponse 暴露 hit 计数。
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_orchestrator.py -v` → 预期 3 case PASS（4 case 累计含 6.1 的 1）
- Step 5：`git add data_acquisition_agent/orchestrator.py data_acquisition_agent/tests/test_orchestrator.py && git commit -m "feat(da-agent): output policy enforcement"`

**不允许**：跳过任一扫描；把扫描放回 prompt_assembler
**完成标准**：3 case PASS

### Task 6.3 — _build_response 扩展（异常兜底 → schema_validation_failed）
- **Files Modify**: `data_acquisition_agent/orchestrator.py`, `data_acquisition_agent/tests/test_orchestrator.py`

**TDD 步骤**
- Step 1：测试（json_parse → schema_validation_failed + audit_report 缺失字段 → schema_validation_failed）：
  ```python
  def test_model_unavailable_json_parse_to_schema_failed():
      orch = DataAcquisitionOrchestrator(model_client=StubModelClient(
          {"model_error": "json_parse: bad"}, status="model_unavailable"))
      with pytest.raises(OrchestratorError) as ei:
          orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
      assert ei.value.error_type == ErrorType.SCHEMA_VALIDATION_FAILED
      assert re.fullmatch(
          r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
          ei.value.request_id,
      )

  def test_invalid_audit_report_to_schema_failed():
      bad = dict(PAYLOAD_OK, audit_report="not_a_dict")
      orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
      with pytest.raises(OrchestratorError) as ei:
          orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
      assert ei.value.error_type == ErrorType.SCHEMA_VALIDATION_FAILED
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_orchestrator.py -v` → 预期 FAIL
- Step 3：实现：
  ```python
      def _build_response(self, rid, request, payload, mr, token_estimate, files,
                          redaction_hits, danger_events):
          try:
              return GenerateResponse(
                  request_id=rid, target_country=request.target_country,
                  reasoning_summary=payload.get("reasoning_summary",""),
                  sql=payload.get("sql"), sql_kind=payload.get("sql_kind"),
                  python=payload.get("python"),
                  audit_report=AuditReport(**payload.get("audit_report", {})),
                  metadata=GenerateMetadata(
                      model=mr.get("model_name",""), tokens_used=None,
                      token_estimate=token_estimate, knowledge_files_loaded=files,
                      redaction_events=redaction_hits,
                      danger_scan_events=danger_events,
                      generated_at=datetime.now(timezone.utc).isoformat()))
          except Exception as e:
              raise OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED, str(e), request_id=rid)
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_orchestrator.py -v` → 预期 2 case PASS（6 case 累计含 6.1 的 1 + 6.2 的 3 + 6.3 的 2）
- Step 5：`git add data_acquisition_agent/orchestrator.py data_acquisition_agent/tests/test_orchestrator.py && git commit -m "feat(da-agent): response assembly with schema fallback"`

**不允许**：直接 import google.genai；连数据库；执行 SQL/Python；落盘
**完成标准**：2 case PASS，且 Phase 1-5 + 6.1/6.2 测试不回归

---

## Phase 7 — api.py + app/main.py include_router

### Task 7.1 — api.py 接 orchestrator + 错误映射
- **Files Modify**: `data_acquisition_agent/api.py`
- **Files Create**: `data_acquisition_agent/tests/test_api.py`

**TDD 步骤**
- Step 1：测试：
  ```python
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from data_acquisition_agent.api import router
  from data_acquisition_agent import api as api_mod
  from data_acquisition_agent.orchestrator import OrchestratorError
  from data_acquisition_agent.schemas import ErrorType

  def _client(): app = FastAPI(); app.include_router(router); return TestClient(app)

  def test_generate_422_on_invalid_country_enum():
      # target_country="atlantis" 不在 TargetCountry 枚举内，FastAPI/Pydantic 自动 422
      r = _client().post("/api/data-acquisition/generate",
          json={"natural_language_request":"x","target_country":"atlantis"})
      assert r.status_code == 422

  class _StubMC:
      mode = "mock"; model_name = "stub"
      def generate_structured(self, **kw):
          return {"status": "ok", "structured_result": kw.get("fallback_result", {}),
                  "model_name": "stub", "prompt_preview": ""}

  def test_generate_400_on_placeholder_country(monkeypatch):
      # indonesia.yaml 当前为占位符 manifest（business_logic_md 等仍是 <PLACEHOLDER...）
      # 必须 monkeypatch orchestrator 避免 ModelClient.__init__ 依赖环境变量
      from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator
      monkeypatch.setattr(api_mod, "_get_orchestrator",
          lambda: DataAcquisitionOrchestrator(model_client=_StubMC()))
      r = _client().post("/api/data-acquisition/generate",
          json={"natural_language_request":"x","target_country":"indonesia"})
      assert r.status_code == 400
      assert r.json()["error_type"] == "bad_request"
      assert r.json()["request_id"]

  def test_generate_422_on_credential_leak(monkeypatch):
      class Boom:
          def generate(self, req):
              raise OrchestratorError(ErrorType.CREDENTIAL_LEAK, "x", request_id="rid-test-1")
      monkeypatch.setattr(api_mod, "_get_orchestrator", lambda: Boom())
      r = _client().post("/api/data-acquisition/generate", json={"natural_language_request":"x","target_country":"mexico"})
      assert r.status_code == 422
      body = r.json()
      assert body["error_type"] == "credential_leak"
      assert body["request_id"] == "rid-test-1"

  import pytest
  @pytest.mark.parametrize("etype,expected_status", [
      (ErrorType.BAD_REQUEST,                400),
      (ErrorType.PROMPT_TOO_LARGE,           400),
      (ErrorType.SCHEMA_VALIDATION_FAILED,   422),
      (ErrorType.CREDENTIAL_LEAK,            422),
      (ErrorType.DANGEROUS_CODE,             422),
      (ErrorType.DDL_POLICY_VIOLATION,       422),
      (ErrorType.UPSTREAM_LLM_ERROR,         502),
  ])
  def test_error_type_to_http_status_mapping(monkeypatch, etype, expected_status):
      class Boom:
          def generate(self, req):
              raise OrchestratorError(etype, "x", request_id="rid-map")
      monkeypatch.setattr(api_mod, "_get_orchestrator", lambda: Boom())
      r = _client().post("/api/data-acquisition/generate",
          json={"natural_language_request":"x","target_country":"mexico"})
      assert r.status_code == expected_status
      assert r.json()["error_type"] == etype.value
      assert r.json()["request_id"] == "rid-map"
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_api.py -v` → 预期 FAIL
- Step 3：实现替换：
  ```python
  from fastapi import APIRouter
  from fastapi.responses import JSONResponse
  from .schemas import GenerateRequest, GenerateResponse, ErrorType, ErrorResponse
  from .orchestrator import DataAcquisitionOrchestrator, OrchestratorError

  router = APIRouter(prefix="/api/data-acquisition", tags=["data-acquisition"])
  _STATUS_MAP = {
      ErrorType.BAD_REQUEST: 400, ErrorType.PROMPT_TOO_LARGE: 400,
      ErrorType.SCHEMA_VALIDATION_FAILED: 422, ErrorType.CREDENTIAL_LEAK: 422,
      ErrorType.DANGEROUS_CODE: 422, ErrorType.DDL_POLICY_VIOLATION: 422,
      ErrorType.UPSTREAM_LLM_ERROR: 502,
  }
  _ORCH = None
  def _get_orchestrator():
      global _ORCH
      if _ORCH is None: _ORCH = DataAcquisitionOrchestrator()
      return _ORCH

  @router.post("/generate", response_model=GenerateResponse)
  def generate(request: GenerateRequest):
      try:
          return _get_orchestrator().generate(request)
      except OrchestratorError as e:
          err = ErrorResponse(error_type=e.error_type, message=e.message,
                              request_id=e.request_id)
          return JSONResponse(status_code=_STATUS_MAP[e.error_type],
                              content=err.model_dump(mode="json"))
  ```
  manifests / healthz endpoint 保留 Stub 501 不变。
- Step 4：`python -m pytest data_acquisition_agent/tests/test_api.py -v` → 预期 10 case PASS（invalid_country_enum / placeholder_country / credential_leak + 7 parametrize 映射）
- Step 5：`git add data_acquisition_agent/api.py data_acquisition_agent/tests/test_api.py && git commit -m "feat(da-agent): wire api.py to orchestrator with error mapping"`

**不允许**：实现 manifests/healthz；改 stub 文件标签外的代码
**完成标准**：10 case PASS

### Task 7.2 — app/main.py include data_acquisition router
- **Files Modify**: `app/main.py`
- **Files Modify**: `data_acquisition_agent/tests/test_api.py`

**TDD 步骤**
- Step 1：追加测试：
  ```python
  def test_main_app_mounts_da_router():
      from app.main import app
      paths = {r.path for r in app.routes}
      assert "/api/data-acquisition/generate" in paths
      assert "/api/analyze" in paths or any(p.startswith("/api/analyze") for p in paths)
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_api.py -v` → 预期 FAIL（router 未挂入）
- Step 3：在 `app/main.py` 末尾追加 2 行：
  ```python
  from data_acquisition_agent.api import router as data_acquisition_router
  app.include_router(data_acquisition_router)
  ```
- Step 4：`python -m pytest data_acquisition_agent/tests/test_api.py -v` → 预期 PASS
- Step 5：`git add app/main.py data_acquisition_agent/tests/test_api.py && git commit -m "feat(da-agent): mount data_acquisition router into main app"`

**不允许**：改现有 `/api/analyze` 路由、修改 SkillRegistry、修改 BaseSkill
**完成标准**：测试 PASS

---

## Phase 8 — test_e2e_mock_llm.py 集成

### Task 8.1 — e2e 通过 TestClient 走 happy path
- **Files Modify**: `data_acquisition_agent/tests/test_e2e_mock_llm.py`

**TDD 步骤**
- Step 1：测试：
  ```python
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from data_acquisition_agent.api import router
  from data_acquisition_agent import api as api_mod
  from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator

  class StubModelClient:
      mode = "mock"; model_name = "stub-mock"
      def generate_structured(self, **kw):
          return {"status":"ok","model_name":"stub-mock","prompt_preview":"",
              "structured_result":{
                  "reasoning_summary":"mob1 mexico extract",
                  "sql":"SELECT uid FROM dwb.dwb_b1_data_burying_point WHERE channel='MEX017' LIMIT 100",
                  "sql_kind":"query_only","python":None,
                  "audit_report":{"high_risk_ddl":False,"final_verdict":"ok"}}}
  def test_e2e_mock_llm_mexico_happy(monkeypatch):
      monkeypatch.setattr(api_mod, "_get_orchestrator",
          lambda: DataAcquisitionOrchestrator(model_client=StubModelClient()))
      app = FastAPI(); app.include_router(router); c = TestClient(app)
      r = c.post("/api/data-acquisition/generate",
          json={"natural_language_request":"建表墨西哥 mob1 取 100 uid","target_country":"mexico"})
      assert r.status_code == 200, r.text
      body = r.json()
      assert "MEX017" in body["sql"]
      assert body["sql_kind"] == "query_only"
      assert body["audit_report"]["high_risk_ddl"] is False
      assert len(body["metadata"]["knowledge_files_loaded"]) == 5
  ```
- Step 2：`python -m pytest data_acquisition_agent/tests/test_e2e_mock_llm.py -v` → 预期 FAIL（placeholder 还在 / orchestrator 未注入）
- Step 3：删除 placeholder 函数，保留上面 e2e 用例
- Step 4：`python -m pytest data_acquisition_agent/tests/test_e2e_mock_llm.py -v` → 预期 PASS
- Step 5：`git add data_acquisition_agent/tests/test_e2e_mock_llm.py && git commit -m "feat(da-agent): e2e mock LLM happy-path integration test [complete]"`

**不允许**：调用 real LLM；新增除 placeholder 替换外的其他文件
**完成标准**：e2e PASS，全套 `python -m pytest data_acquisition_agent/tests/ -v` 全绿

---

## Commit 策略

1. **执行前打基线**（Phase 0 之前）：
   ```bash
   git commit --allow-empty -m "[baseline] data_acquisition_agent_v1"
   ```
2. 每个 Task 完成立即 commit，commit message 见各 Task Step 5
3. **禁止** `git add -A`；每次只 add 该 Task 显式列出的文件
4. **最后一个 commit 必须含 `[complete]` 标签**：Task 8.1 commit message 已含

## 停止条件（遇到以下情况立即停下汇报，不要猜测或绕过）

- demo0 知识库文件读取失败（路径/编码问题）→ 停，不要猜路径
- ModelClient import 失败（依赖未装 / 版本不兼容）→ 停，不要改 ModelClient 代码
- pytest 收集报错（非测试失败，而是 import error / SyntaxError）→ 停，先查依赖
- 任何 Task 的实际测试数与 Plan 预估不符 → 停，确认 Plan 是否有更新

## 预估总测试用例数

| 测试文件 | 用例数 |
|---|---|
| `test_schemas.py` | 5（_at_least_one_artifact + 3 个 sql_kind 联动 + ErrorResponse round-trip）|
| `test_manifest.py` | 3（含 placeholder country `<PLACEHOLDER` 检测）|
| `test_redactor.py` | 15（11 parametrize + 4 false-positive 边界）|
| `test_output_scanner.py` | 25（凭据 4 + Python 8 + DDL 13 含 5 DML reject + 2 quoted reject）|
| `test_prompt_assembler.py` | 6（5.1 的 3 case + 5.2 的 3 case）|
| `test_orchestrator.py` | 6（6.1 的 1 + 6.2 的 3 + 6.3 的 2）|
| `test_api.py` | 11（invalid_country 422 / placeholder_country 400 / credential_leak 422 + 7 ErrorType 映射 + mount）|
| `test_e2e_mock_llm.py` | 1 |
| `test_smoke_real_llm_mexico.py` | 0 实现（保持 skip placeholder）|
| **合计** | **72** |

## 已知风险及应对

| # | 风险 | 应对 |
|---|---|---|
| 1 | demo0 脱敏回归（后续修改 demo0 引入新明文）| `test_redactor.py` 测脱敏函数本身；后续可加 pre-commit 扫描（V2 可选）|
| 2 | LLM JSON parse 不稳定 | ModelClient 自带 1 次 retry；未通过则 422 `schema_validation_failed`，不静默降级 |
| 3 | DDL prefix 绕过（注释挟带、单/双引号包裹的标识符）| `_strip_sql_comments` 先剥注释；V1 不支持 quoted identifier — 包含反引号或双引号的 DDL statement 无法匹配 allowlist，因此保守 reject；V2 可考虑支持安全解析 quoted identifier |
| 4 | 日志泄漏知识库正文 | logger 仅记 path/size/hits/token_estimate，不打 prompt 正文（Design Doc §9）|
| 5 | token estimate 误差 | 中文 ×1.5 启发式偏低 ~30%，阈值 800K 留充足边际；超限时 400 而非静默截断 |
| 6 | ModelClient 不返回 token usage | `metadata.tokens_used=None`，Pydantic Optional 允许；`token_estimate` 始终填 |
| 7 | include_router 影响现有 /api/analyze | Task 7.2 测试同时断言 `/api/analyze` 仍存在 |
| 8 | Pydantic extra 字段兼容 | `AuditReport.Config.extra='allow'` 已在 Stub；orchestrator 用 `AuditReport(**dict)` 透传 |
| 9 | L1（redactor）与 L2（output_scanner.scan_credentials）模式漂移：知识库已脱敏但 LLM 输出含等价凭据，因两侧规则不同步而漏过 | L1/L2 使用同一 credential family 清单，V1 不抽 shared registry，通过两侧测试防漂移 |
| 10 | 占位符 country manifest（indonesia/pakistan/thailand/philippines）被误调用，触发 LLM 用未脱敏 `<PLACEHOLDER...>` md 路径 | Task 2.1 `load_manifest` 在任一字段以 `<PLACEHOLDER` 开头或路径不存在时抛 `ManifestNotImplemented`；Task 6.1 映射为 `bad_request` 400；test_api 含 indonesia 400 case |
| 11 | ModelClient 单点故障（模型不可用时直接 502，无 fallback） | V1 接受直接 502；V2 可加 FALLBACK_MODELS 列表降级到更小模型 |

## 五点检查法自检

1. **每个 Task 有精确文件路径？** ✅ 所有 Task 都列出了 Files Create/Modify/Test 完整绝对路径前缀（含子项目目录）
2. **有 TBD/TODO/占位符？** ✅ Plan 主体无未决占位；schemas.py 内现存 Step 4 placeholder 注释会在 Phase 1 清理
3. **代码步骤有最小可执行代码块？** ✅ 每个 Task Step 1 含可粘贴测试，Step 3 含 patch 级实现片段
4. **有验证命令 + 预期输出？** ✅ 每个 Task Step 2/4 有 pytest 命令 + FAIL/PASS 预期
5. **一个人不问问题能执行完？** ✅ 所有 Scope 决策已在 Plan 中落定（无遗留 Open Question）
