# Data-Diff-Tool

数据仓库迁移验证工具。在数仓系统切换场景下，自动化验证新旧表之间的结构兼容性与数据一致性，生成 HTML 可视化报告。

## 功能概述

- **结构校验**：对比新旧表字段类型、长度、可空性，自动判定类型兼容性（varchar 扩容、int 升级、numeric 精度增长等）
- **数据一致性校验**：通过 FULL JOIN + 主键关联，统计字段差异行数与差异率
- **抽样配置**：通过 Excel 指定每张表的校验主键和过滤条件
- **HTML 报告**：单文件自包含报告，浏览器直接打开，差异行红色高亮

## 安装

```bash
pip install -e .
```

或指定开发依赖：

```bash
pip install -e ".[dev]"
```

> 需要 Python 3.12+

## Excel 输入格式

工具读取一个 Excel 文件，包含三个页签：

### 1. 实体级mapping

| 序号 | 切换前库名 | 切换前Schema | 切换前表名 | 切换后库名 | 切换后Schema | 切换后表名 | 实体级变化类型 | 数据迁移策略 | 迁移后粒度是否发生变化 | 详细说明 |
|--|--|--|--|--|--|--|--|--|--|--|
| 1 | edw | sdi | sdi_contract_2000 | edw | sdi | sdi_contract_3000 | 1:1 | 全量迁移 | 否 | |

实体级变化类型说明：

| 类型 | 说明 | 工具行为 |
|------|------|----------|
| 1:1 | 旧表 → 新表 | 自动校验 |
| 1:N | 旧表拆分为多表 | 记录待办，不自动校验 |
| N:1 | 多表整合为新表 | 记录待办，不自动校验 |
| 1:0 | 旧表下线 | 仅记录清单 |
| 0:1 | 切换前不存在，切换后新增 | 仅记录清单 |

### 2. 属性级mapping

| 序号 | 切换前库名 | 切换前Schema | 切换前表名 | 切换前字段名 | 切换前字段中文名 | 切换前字段类型 | 切换后库名 | 切换后Schema | 切换后表名 | 切换后字段名 | 切换后字段中文名 | 切换后字段类型 | 字段级变化类型 | 数据内容变化 | 是否可还原 | 还原方案详细说明 |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| 1 | edw | sdi | sdi_contract_2000 | contract_id | 合同ID | nvarchar2(100) | edw | sdi | sdi_contract_3000 | contract_id | 合同ID | nvarchar2(100) | 1:1 完全一致 | 1.数据内容不变 | | |

字段级变化类型与校验策略：

| 类型 | 校验策略 |
|------|----------|
| 1:1 完全一致 | 严格等值对比 |
| 1:1 字段类型变化 | CAST 为 VARCHAR 后对比 |
| 1:1 数据内容变化 | 跳过对比，仅记录 |
| 1:1 字段类型变化 数据内容变化 | 跳过对比，仅记录 |

### 3. 抽样校验配置

| 序号 | 切换前库名 | 切换前Schema | 切换前表名 | 主键字段 | 过滤条件 | 备注 |
|--|--|--|--|--|--|--|
| 1 | edw | sdi | sdi_contract_2000 | contract_id | dt = '2026-03-01' | |
| 2 | edw | sdi | sdi_order_2000 | order_id,order_type | status = 'active' | 复合主键 |

- **主键字段**：逗号分隔，支持复合主键
- **过滤条件**：WHERE 子句，新旧表均使用相同过滤条件

## 配置方式

数据库连接支持三种配置方式（优先级从高到低）：

### 方式一：配置文件（推荐）

创建 `dws_sources.yaml` 文件，按数据库名组织连接信息：

```yaml
sources:
  edw:
    host: 10.0.1.100
    port: 8000
    user: admin
    password: changeme
  ods:
    host: 10.0.2.200
    port: 8000
    user: readonly
    password: changeme
```

工具会自动从 Excel 中的表 FQN（如 `edw.sdi.contract_2000`）提取数据库名，匹配对应的连接。一个配置文件可管理多个数据库，涉及多库时自动建立多个连接池。

```bash
data-diff run --excel mapping.xlsx --config dws_sources.yaml
```

### 方式二：DSN 连接串

### 方式二：DSN 连接串

```bash
data-diff run --excel mapping.xlsx \
  --dsn "postgresql://admin:password@dws-host:8000/edw"
```

### 方式三：CLI 参数

```bash
data-diff run --excel mapping.xlsx \
  --host dws-host --port 8000 --database edw \
  --user admin --password mypassword
```

### 方式三：CLI 参数

```bash
data-diff run --excel mapping.xlsx \
  --host dws-host --port 8000 --database edw \
  --user admin --password mypassword
```

### 方式四：环境变量

## 运行方式

### 完整校验（连接 DWS 执行）

使用配置文件（推荐）：

```bash
data-diff run --excel mapping.xlsx --config dws_sources.yaml --output-dir ./reports
```

使用 CLI 参数：

```bash
data-diff run --excel mapping.xlsx \
  --host dws-host --port 8000 --database edw \
  --user admin --password mypassword \
  --output-dir ./reports
```

可选参数：

| 参数 | 说明 |
|------|------|
| `--config` | 数据库源配置文件路径（推荐） |
| `--primary-keys` | 全局 fallback 主键（Excel 中未配置时使用） |
| `--filter` | 全局 fallback 过滤条件 |
| `--output-dir` | 报告输出目录，默认 `./reports` |
| `-v` | 开启 debug 日志 |

### 仅解析模式（不连接数据库）

预览 Excel 解析结果，确认任务列表：

```bash
data-diff dry-run --excel mapping.xlsx
```

## 输出报告

运行完成后在 `./reports` 目录下生成 `report_YYYYMMDD_HHMMSS.html`，包含：

- **汇总卡片**：Passed / Failed / Skipped 统计
- **结构校验表**：每个字段的类型对比、兼容性判定
- **数据一致性表**：字段差异行数、差异率、状态标签
- **跳过列清单**：因数据内容变化被跳过的字段
- **待办清单**：1:N / N:1 等需人工确认的映射

## 技术栈

| 组件 | 依赖 |
|------|------|
| CLI | click |
| 数据库 | psycopg2-binary (PostgreSQL/GaussDB/DWS) |
| Excel | openpyxl |
| 报告 | Jinja2 |

## 运行测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
