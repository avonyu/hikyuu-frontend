# Hikyuu 回测前端 — 后端

基于 [Hikyuu](https://hikyuu.org) 量化回测框架的 FastAPI 服务，为 React 前端提供回测能力。

## 环境准备

Hikyuu 声明了 PySide6 依赖（435MB Qt GUI 框架），服务端用不上。
已在 `pyproject.toml` 里用 `[tool.uv] exclude-dependencies` 在解析阶段剔除，
因此直接 `uv sync` 即可，无需额外步骤：

```bash
export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"   # PyPI 直连过慢，必须用镜像
uv sync
```

安装后虚拟环境约 612MB（未剔除 PySide6 时为 1.8GB）。
注意：`hikyuu` 的 GUI 相关子模块（`hikyuu.gui.*`）会因缺少 PySide6 无法导入，
核心回测 API（`hikyuu.core` / `hikyuu.trade_manage`）不受影响。

## 初始化数据

```bash
uv run python scripts/seed_data.py --symbols sh510300,sh510500
```

标的写成「市场前缀 + 6 位代码」。类别默认按代码段自动判定，也可用
`--kind ETF|STOCK|INDEX` 覆盖：

```bash
# 个股（自动识别为 STOCK，沪/深/北均可）
uv run python scripts/seed_data.py --symbols sh600519,sz000001

# 深市指数（腾讯源，注意必须带 sz 前缀）
uv run python scripts/seed_data.py --symbols sz399006
```

`000xxx` 段沪市是指数、深市是股票（`sh000001` 上证指数 vs `sz000001`
平安银行），裸代码无法判定，必须写市场前缀。

这会拉取行情写入 `data_root/data/*.h5`（Hikyuu HDF5 格式），
并在 `data_root/cfg/stock.db` 注册证券元信息。

## 启动服务

```bash
uv run uvicorn app.api.server:app --reload --port 8000
```

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/backtests` | 提交回测，返回 job id |
| GET | `/api/backtests/{id}` | 查询回测状态与结果 |
| GET | `/api/symbols` | 本地标的清单 |
| POST | `/api/symbols/refresh` | 触发增量更新 |
| GET | `/api/health` | 引擎状态 |

## 模块结构

- `app/core/engine.py` — Hikyuu 3.0 API 适配层，隔离版本差异
- `app/data/sources.py` — 行情数据源适配（akshare / 腾讯指数源）
- `app/data/importer.py` — HDF5 写入 + SQLite 注册
- `app/api/server.py` — FastAPI 应用与作业队列
