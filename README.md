# Data-Diff-Tool

数据仓库迁移验证工具。在数仓系统切换场景下，自动化验证新旧表之间的结构兼容性与数据一致性，生成 HTML 可视化报告。

## 功能概述

- **结构校验**：对比新旧表字段类型、长度、可空性，自动判定类型兼容性（varchar 扩容、int 升级、numeric 精度增长等）
- **数据一致性校验**：通过 FULL JOIN + 主键关联，统计字段差异行数与差异率
- **抽样配置**：通过 Excel 指定每张表的校验主键和过滤条件
- **HTML 报告**：单文件自包含报告，浏览器直接打开，差异行红色高亮
- **Web UI**：基于 Streamlit 的浏览器界面，无需命令行操作

## 安装

```bash
pip install -e .
```

CLI 模式（含开发依赖）：

```bash
pip install -e ".[dev]"
```

Web UI 模式：

```bash
pip install -e ".[web]"
```

> 需要 Python 3.12+

## 运行方式

### Web UI（推荐）

```bash
streamlit run src/data_diff_tool/web/app.py
```

启动后访问 `http://localhost:8501`，通过浏览器完成：
1. 上传 Mapping Excel 文件
2. 配置数据源（侧边栏文本编辑或上传 YAML）
3. 预览任务列表
4. 一键执行校验（实时进度展示）
5. 查看/下载 HTML 报告

### CLI 模式

完整校验（连接 DWS 执行）：

```bash
data-diff run --excel mapping.xlsx --config dws_sources.yaml --output-dir ./reports
```

仅解析模式（不连接数据库）：

```bash
data-diff dry-run --excel mapping.xlsx
```

## 配置方式

### 方式一：配置文件（推荐）

创建 `dws_sources.yaml` 文件，按数据库名组织连接信息：

```yaml
sources:
  edw:
    host: 10.0.1.100
    port: 8000
    database: edw
    user: admin
    password: changeme
  ods:
    host: 10.0.2.200
    port: 8000
    user: readonly
    password: changeme
```

Key（如 `edw`）对应 Excel 中 FQN 的第一部分（库名）。`database` 字段为实际连接的数据库名，可与 Key 不同。一个配置文件可管理多个数据库。

```bash
data-diff run --excel mapping.xlsx --config dws_sources.yaml
```

Web UI 中可在侧边栏直接编辑 YAML 文本或上传 YAML 文件。

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

### 方式四：环境变量

```bash
export DWS_HOST=dws-host
export DWS_PORT=8000
export DWS_DBNAME=edw
export DWS_USER=admin
export DWS_PASSWORD=mypassword

data-diff run --excel mapping.xlsx
```

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
| Web UI | streamlit |
| 数据库 | psycopg2-binary (PostgreSQL/GaussDB/DWS) |
| Excel | openpyxl |
| 报告 | Jinja2 |
| 配置 | PyYAML |

## 运行测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
