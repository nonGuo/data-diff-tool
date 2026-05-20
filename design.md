# 数据仓库迁移验证工具 (Data-Diff-Tool) 设计文档 (MVP)

## 1. 概述

在数仓中台场景下，当上游系统切换但表粒度保持不变时，本工具用于自动化验证新旧表之间的一致性。通过配置映射关系，工具将自动执行表结构对标、不变字段的数据等值校验，并生成可视化报告。

## 2. 核心架构

工具采用 **“Python 逻辑控制 + In-Database SQL 计算”** 的架构。

* **Python 层**：负责配置解析、动态 SQL 渲染、任务流控制及报告生成。
* **DWS 层**：利用 MPP 分布式架构进行高并发的数据对比，仅向 Python 返回统计结果。

---

## 3. 详细设计

### 3.1 配置模块 (Configuration)

使用 YAML 或 JSON 定义任务，支持主键更名及字段分类。

```yaml
task_id: "order_system_migration_001"
source_config:
  old_table: "ods.old_order_info"
  new_table: "ods.new_order_info"
  filter: "dt = '2026-03-01'" # 支持特定限制条件
mapping:
  primary_keys:
    - { old: "order_id", new: "id" } # 支持主键名变更
  identical_columns: # 预期完全一致的字段
    - "user_id"
    - "order_amount"
    - "create_time"
  logical_change_columns: # 逻辑变化的字段（MVP仅做记录或基础类型检查）
    - "order_status"

```

### 3.2 验证引擎 (Verification Engine)

#### 模块 A：表结构校验 (Metadata Checker)

通过查询 DWS 系统表（`pg_attribute` 系列）实现。

* **SQL 逻辑**：
```sql
SELECT
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_attribute a
    JOIN pg_class c ON a.attrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname = '{schema}'
    AND c.relname = '{table_name}'
    AND a.attnum > 0
    AND NOT a.attisdropped;
```

```


* **对比逻辑**：
1. 检查 `mapping.identical_columns` 中的字段是否存在于新表。
2. 检查字段类型是否兼容（例如：`varchar(32)` 变为 `varchar(64)` 可接受，但变为 `int` 则报错）。



#### 模块 B：数据一致性校验 (Data Checker)

动态生成单条聚合 SQL，利用 DWS 的并行计算能力。

* **核心逻辑**：使用 `FULL JOIN` 关联新旧表。
* **关键处理**：
* **NULL 处理**：使用 `DECODE` 或 `COALESCE` 确保 `NULL = NULL` 在对比中判定为一致。
* **差异统计**：针对每个字段生成 `SUM(CASE WHEN...)`。



**动态生成的校验 SQL 示例**：

```sql
SELECT 
    COUNT(1) AS total_count,
    SUM(CASE WHEN a.{old_pk} IS NULL THEN 1 ELSE 0 END) AS left_only_count,
    SUM(CASE WHEN b.{new_pk} IS NULL THEN 1 ELSE 0 END) AS right_only_count,
    -- 动态渲染不变字段的对比
    SUM(CASE WHEN NOT (a.user_id IS NOT DISTINCT FROM b.user_id) THEN 1 ELSE 0 END) AS user_id_diff_cnt,
    SUM(CASE WHEN NOT (a.order_amount IS NOT DISTINCT FROM b.order_amount) THEN 1 ELSE 0 END) AS order_amount_diff_cnt
FROM {old_table} a
FULL JOIN {new_table} b ON a.{old_pk} = b.{new_pk}
WHERE {filter_conditions};

```

> *注：`IS NOT DISTINCT FROM` 为 PostgreSQL 标准的 NULL-safe 等值对等操作符，`NULL IS NOT DISTINCT FROM NULL` 判定为 true。*

---

### 3.3 报告模块 (Reporting)

生成 Markdown 或 HTML 格式的报告，包含：

1. **任务摘要**：运行时间、耗时、数据总量、差异总行数。
2. **结构对标表**：
| 字段名 | 预期类型 | 实际类型 | 结论 |
| --- | --- | --- | --- |
| id | int8 | int8 | ✅ |


3. **数据一致性表**：
| 检查字段 | 对比行数 | 差异行数 | 差异率 | 状态 |
| --- | --- | --- | --- | --- |
| user_id | 1,000,000 | 0 | 0.00% | ✅ |
| amount | 1,000,000 | 12 | 0.0012% | ❌ |



---

## 4. 技术栈

* **语言**：Python 3.12+
* **数据库驱动**：`psycopg2-binary` (DWS 完美兼容)
* **模板引擎**：`Jinja2` (用于动态生成复杂的 SQL)
* **配置解析**：`PyYAML`
* **数据展示**：`PrettyTable` (控制台预览) 或 `Pandas` (报告格式化)

---

## 5. MVP 实施计划

1. **Day 1**: 搭建 Python 基础框架，完成数据库连接池封装。
2. **Day 2**: 实现 `Metadata Checker` 逻辑，能够读取 DWS 系统表。
3. **Day 3**: 编写 `SQL Generator`，利用 Jinja2 渲染 `FULL JOIN` 对比语句。
4. **Day 4**: 开发报告输出模块，集成控制台日志。
5. **Day 5**: 针对一张百万级以上的真实 DWS 表进行端到端测试。

---

## 6. 风险与规避

* **性能风险**：如果对比字段过多（如 100+ 字段），生成的 SQL 可能会非常庞大。
* *规避*：MVP 限制单次对比字段上限，或分批次生成 SQL 执行。

---

## 7. 输入

关联影响清单：excel文件，涉及两个页签，分别为`实体级mapping`和`属性级mapping`，分别存储表级的变化和字段级的变化

### 实体级mapping
|序号|切换前库名|切换前Schema|切换前表名|切换后库名|切换后Schema|切换后表名|实体级变化类型|数据迁移策略|迁移后粒度是否发生变化|详细说明|
|--|--|--|--|--|--|--|--|--|--|--|
|1|edw|sdi|sdi_contract_2000|edw|sdi|sdi_contract_3000|1:1|全量迁移|否||
|2|edw|sdi|sdi_order_2000|edw|sdi|sdi_order_cn_3000|1:N|全量迁移|否|拆分为中国区和海外两张表存储，该表存储中国区数据|
|3|edw|sdi|sdi_order_2000|edw|sdi|sdi_order_ovs_3000|1:N|全量迁移|否|拆分为中国区和海外两张表存储，该表存储海外数据|
|4|edw|sdi|sdi_invoice_2000|edw|sdi|sdi_invoice_3000|N:1|全量迁移|否||
|5|edw|sdi|sdi_invoice_th_2000|edw|sdi|sdi_invoice_3000|N:1|全量迁移|否||
|6|edw|sdi|sdi_user_2000||||1:0||||
|7||||edw|sdi|sdi_partner_3000|0:1||||


实体级变化类型说明：
|实体级变化类型|说明|
|--|--|
|1:1|切换前数据存储在1张表，切换后仅存在新系统1张表|
|1:N|旧表拆分成多表|
|N:1|多表整合成1张新表|
|1:0|旧表下线|
|0:1|切换前不存在，切换后新增|

### 属性级mapping
|序号|切换前库名|切换前Schema|切换前表名|切换前字段名|切换前字段中文名|切换前字段类型|切换后库名|切换后Schema|切换后表名|切换后字段名|切换后字段中文名|切换后字段类型|字段级变化类型|数据内容变化|是否可还原|还原方案详细说明|
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
|1|edw|sdi|sdi_contract_2000|contract_id|合同ID|nvarchar2(100)|edw|sdi|sdi_contract_3000|contract_id|nvarchar2(100)|合同ID|1:1 完全一致|1.数据内容不变|||
|2|edw|sdi|sdi_contract_2000|contract_no|合同号|nvarchar2(100)|edw|sdi|sdi_contract_3000|contract_num|nvarchar2(100)|合同号|1:1 字段类型变化|1.数据内容不变|||
|3|edw|sdi|sdi_contract_2000|contract_type|合同类型|nvarchar2(30)|edw|sdi|sdi_contract_3000|contract_type|nvarchar2(30)|合同类型|1:1 数据内容变化|2.数据值域变化|Y|asis->tobe:<br>1->3<br>2->4<br>3->5|

字段级变化类型说明：
|字段级变化类型|说明|
|--|--|
|1:1 完全一致|字段类型，数据内容切换前后完全一致|
|1:1 字段类型变化|切换前后字段类型/长度改变，数据内容一致|
|1:1 数据内容变化|切换前后数据内容改变，字段类型一致|
|1:1 字段类型变化 数据内容变化|切换前后字段类型/内容改变|
|0:1|切换后字段新增|
|1:0|切换后字段废弃|

### 实体级变化类型与 MVP 处理策略

|实体级变化类型|说明|MVP 处理策略|
|--|--|--|
|1:1|切换前数据存储在1张表，切换后仅存在新系统1张表|执行完整校验（结构+数据）|
|1:N|旧表拆分成多表|MVP 阶段标记为"需人工确认"，不自动校验|
|N:1|多表整合成1张新表|MVP 阶段标记为"需人工确认"，不自动校验|
|1:0|旧表下线|仅输出清单记录，不做数据校验|
|0:1|切换前不存在，切换后新增|仅输出清单记录，不做数据校验|

> **MVP 范围**：仅自动处理 1:1 实体映射。1:N / N:1 因涉及跨表 UNION 或过滤条件推断，复杂度较高，MVP 阶段输出待办清单即可。

### 属性级变化类型与校验策略

|字段级变化类型|说明|校验策略|
|--|--|--|
|1:1 完全一致|字段类型，数据内容切换前后完全一致|执行严格等值对比|
|1:1 字段类型变化|切换前后字段类型/长度改变，数据内容一致|执行类型兼容对比（CAST 后对比）|
|1:1 数据内容变化|切换前后数据内容改变，字段类型一致|MVP 跳过数据对比，仅记录变化|
|1:1 字段类型变化 数据内容变化|切换前后字段类型/内容改变|MVP 跳过数据对比，仅记录变化|
|0:1|切换后字段新增|仅记录|
|1:0|切换后字段废弃|仅记录|

### 实体级 Mapping 主键

Excel 第一列"序号"虽能保证唯一性但无业务含义，不适合作为主键。实体级行的主键由旧表和新表的全限定名（FQN = 库名.Schema.表名）组合而成：

| 场景 | 主键构成 | 说明 |
|------|----------|------|
| 1:1 | `old_fqn` 或 `(old_fqn, new_fqn)` | 双向唯一，任选其一 |
| 1:N | `(old_fqn, new_fqn)` | 一张旧表对应多张新表，需组合才能唯一 |
| N:1 | `(old_fqn, new_fqn)` | 多张旧表对应一张新表，需组合才能唯一 |
| 1:0 | `old_fqn` | 无 new_fqn |
| 0:1 | `new_fqn` | 无 old_fqn |

**统一规则**：所有场景统一以 `(old_fqn, new_fqn)` 组合作为组合主键（1:0 的 new_fqn 为空字符串，0:1 的 old_fqn 为空字符串）。

**用途**：属性级 mapping 也包含新旧表的全限定名，解析时以此为外键，将字段级映射精确关联到对应的实体级行。

### 数据校验主键来源

数据校验阶段需要知道表级关联的列级主键（如 `contract_id`），通过以下方式确定：

1. **Excel「抽样校验配置」页签**：按旧表 FQN 指定主键字段和过滤条件
2. **CLI `--primary-keys` 参数**：作为全局 fallback 应用于所有 1:1 任务

若以上方式均未配置，工具报错并提示用户指定主键。

### 属性级 Mapping 主键

属性级行在实体级组合主键的基础上增加字段名，构成四级组合主键：

| 场景 | 主键构成 | 说明 |
|------|----------|------|
| 1:1 | `(old_fqn, new_fqn, old_col, new_col)` | 唯一对应一条字段映射关系 |
| 1:N / N:1 | `(old_fqn, new_fqn, old_col, new_col)` | 同样适用，由 `(old_fqn, new_fqn)` 限定所属实体行 |
| 1:0 | `(old_fqn, "", old_col, "")` | 仅旧表字段 |
| 0:1 | `("", new_fqn, "", new_col)` | 仅新表字段 |

解析时以此四元组作为唯一标识，避免同一表内多字段映射产生混淆。

---

## 8. Excel 解析与任务生成流程

```
Excel 输入
  │
  ├── 解析「实体级mapping」页签
  │     │
  │     ├── 1:1 → 生成 VerificationTask
  │     ├── 1:N / N:1 → 生成 SkippedTask（记录原因）
  │     ├── 1:0 / 0:1 → 生成 InventoryTask（仅记录）
  │     └── 其他 → 报错
  │
  ├── 解析「属性级mapping」页签
  │     └── 按 {库}.{Schema}.{表} 分组，映射到对应 VerificationTask
  │         ├── 1:1 完全一致 → identical_columns
  │         ├── 1:1 字段类型变化 → cast_columns（需 CAST 后对比）
  │         └── 数据内容变化 → skipped_columns（记录但不校验）
  │
  └── 输出：任务列表 + 不可自动校验清单
```

---

## 9. 工程结构

```
data-diff-tool/
├── pyproject.toml              # 项目元数据与依赖
├── README.md
├── design.md                   # 本设计文档
├── src/
│   └── data_diff_tool/
│       ├── __init__.py
│       ├── cli.py              # CLI 入口（click 框架）
│       ├── config/
│       │   ├── __init__.py
│       │   ├── excel_parser.py # Excel 解析与任务生成
│       │   └── models.py       # 数据模型（Task, Column, Mapping）
│       ├── db/
│       │   ├── __init__.py
│       │   ├── connection.py   # 数据库连接管理
│       │   └── metadata.py     # 元数据查询（pg_attribute 系统表）
│       ├── verifier/
│       │   ├── __init__.py
│       │   ├── struct.py       # 模块 A：表结构校验
│       │   └── data.py         # 模块 B：数据一致性校验
│       └── report/
│           ├── __init__.py
│           └── generator.py    # Markdown/HTML 报告生成
├── tests/
│   ├── test_excel_parser.py
│   ├── test_struct_check.py
│   ├── test_data_check.py
│   └── test_report.py
└── examples/
    └── sample_mapping.xlsx     # 示例输入文件
```

---

## 10. CLI 接口设计

```bash
# 基本用法：指定 Excel 文件和数据库连接信息
data-diff run \
  --excel path/to/mapping.xlsx \
  --host dws-host \
  --port 8000 \
  --database edw \
  --user admin \
  --password secret

# 指定主键（当无法自动推断时）
data-diff run \
  --excel mapping.xlsx \
  --host dws-host --port 8000 --database edw --user admin --password secret \
  --primary-keys "contract_id"

# 指定过滤条件（如分区裁剪）
data-diff run \
  --excel mapping.xlsx \
  --host dws-host --port 8000 --database edw --user admin --password secret \
  --filter "dt = '2026-03-01'"

# 输出报告路径
data-diff run \
  --excel mapping.xlsx \
  --host dws-host --port 8000 --database edw --user admin --password secret \
  --output-dir ./reports

# 仅检查模式：解析 Excel 生成任务清单，不连接数据库
data-diff dry-run --excel mapping.xlsx
```

---

## 11. 核心数据模型

```python
@dataclass
class Column:
    name: str
    data_type: str          # 如 varchar(100), int8
    nullable: bool = True

@dataclass
class EntityMapping:
    old_fqn: str            # old_db.old_schema.old_table
    new_fqn: str            # new_db.new_schema.new_table
    mapping_type: str       # "1:1", "1:N", "N:1", "1:0", "0:1"

    @property
    def composite_key(self) -> tuple[str, str]:
        """组合主键：(old_fqn, new_fqn)，用于关联属性级 mapping"""
        return (self.old_fqn, self.new_fqn)

@dataclass
class ColumnMapping:
    old_col: Column
    new_col: Column
    change_type: str        # "1:1 完全一致", "1:1 字段类型变化", ...
    data_changed: bool      # 数据内容是否变化

@dataclass
class VerificationTask:
    entity: EntityMapping
    primary_keys: list[str]         # 复合主键列表
    identical_columns: list[str]    # 严格等值对比
    cast_columns: list[str]         # CAST 后对比
    skipped_columns: list[str]      # 数据有变化，跳过
    filter_cond: str | None         # WHERE 过滤条件

@dataclass
class TaskResult:
    task: VerificationTask
    struct_check: StructCheckResult
    data_check: DataCheckResult | None
    status: str             # "passed", "failed", "skipped"
    elapsed_ms: int
```

---

## 12. 动态 SQL 生成（修订版）

DWS 基于 PostgreSQL/GaussDB，等值对比使用 `IS NOT DISTINCT FROM`（NULL-safe），而非原文档中的 MySQL 风格 `<=>`。

**完整 SQL 模板**：

```sql
SELECT
    COUNT(1) AS total_count,
    SUM(CASE WHEN a.pk_col IS NULL THEN 1 ELSE 0 END) AS new_only_count,
    SUM(CASE WHEN b.pk_col IS NULL THEN 1 ELSE 0 END) AS old_only_count,
    -- identical_columns（严格等值）
    SUM(CASE WHEN NOT (a.user_id IS NOT DISTINCT FROM b.user_id) THEN 1 ELSE 0 END) AS user_id_diff_cnt,
    SUM(CASE WHEN NOT (a.order_amount IS NOT DISTINCT FROM b.order_amount) THEN 1 ELSE 0 END) AS order_amount_diff_cnt,
    -- cast_columns（类型不同但数据一致，CAST 后对比）
    SUM(CASE WHEN NOT (CAST(a.contract_no AS VARCHAR) IS NOT DISTINCT FROM CAST(b.contract_num AS VARCHAR)) THEN 1 ELSE 0 END) AS contract_no_diff_cnt
FROM old_db.old_schema.old_table a
FULL JOIN new_db.new_schema.new_table b
  ON a.pk1 = b.pk1 AND a.pk2 = b.pk2
WHERE {filter_cond OR '1=1'};
```

**多主键处理**：JOIN 条件用 `AND` 连接所有主键列。

---

## 13. 类型兼容判定规则

结构校验时，以下类型转换视为兼容：

| 旧类型 | 新类型 | 兼容 |
|--------|--------|------|
| varchar(N) | varchar(M), M >= N | ✅ |
| varchar(N) | text | ✅ |
| int2 | int4 / int8 | ✅ |
| int4 | int8 | ✅ |
| numeric(P,S) | numeric(P',S'), P'>=P, S'>=S | ✅ |
| 其他 | 不同 | ❌ |

---

## 14. 执行时序

```
1. 解析 Excel → 生成任务列表
2. 连接 DWS
3. 对每个 VerificationTask：
   3a. 查询 pg_attribute 系统表获取新旧表元数据
   3b. 执行结构校验（模块 A）
   3c. 若结构校验通过，生成并执行数据校验 SQL（模块 B）
   3d. 记录结果
4. 汇总所有结果，生成报告
5. 输出报告文件 + 控制台摘要
```

---

## 15. MVP 实施计划（修订）

| 阶段 | 任务 | 预计工时 |
|------|------|----------|
| Day 1 | 搭建项目骨架（pyproject.toml, 目录结构）、CLI 入口、依赖安装 | 1d |
| Day 2 | Excel 解析模块：读取两个页签，生成 VerificationTask 列表 | 1d |
| Day 3 | 数据库连接模块 + 元数据查询（pg_attribute 系统表） | 1d |
| Day 4 | 结构校验模块：类型兼容判定 | 1d |
| Day 5 | 数据校验模块：动态 SQL 生成与执行（1:1 场景） | 1d |
| Day 6 | 报告生成模块：Markdown 输出 + 控制台摘要 | 1d |
| Day 7 | 端到端测试：使用真实 DWS 表验证完整流程 | 1d |

**MVP 明确不做**：

- 1:N / N:1 自动校验（输出待办清单）
- HTML 报告（仅 Markdown）
- 数据内容变化字段的还原对比
- 增量校验
