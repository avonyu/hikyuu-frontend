"""路径与运行时配置。"""
from __future__ import annotations

import os
from pathlib import Path

# 项目根目录（backend/）
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# 数据根目录，可用环境变量覆盖
DATA_ROOT = Path(os.environ.get("HK_DATA_ROOT", BACKEND_ROOT.parent / "data_root"))

DATA_DIR = DATA_ROOT / "data"
CFG_DIR = DATA_ROOT / "cfg"
STOCK_DB = CFG_DIR / "stock.db"
HIKYUU_INI = CFG_DIR / "hikyuu.ini"

# 每个市场的 HDF5 文件
H5_FILES = {
    "SH": DATA_DIR / "sh_day.h5",
    "SZ": DATA_DIR / "sz_day.h5",
    "BJ": DATA_DIR / "bj_day.h5",
}

# 交易日历来源：Hikyuu 用市场主指数推导交易日历，必须导入
CALENDAR_INDEXES = [
    ("SH", "000001", "上证指数"),
    ("SH", "000300", "沪深300"),
]

# Hikyuu 加载时需要预载的标的（指数 + 已入库标的）
PRELOAD_CODES = ["sh000001", "sh000300"]


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CFG_DIR.mkdir(parents=True, exist_ok=True)


def write_hikyuu_ini() -> Path:
    """生成 Hikyuu 配置文件，指向本项目的数据目录。"""
    ensure_dirs()
    ini = f"""[hikyuu]
tmpdir = {DATA_DIR}/tmp
datadir = {DATA_DIR}
reload_time = 00:00
quotation_server = ipc://{DATA_DIR}/quote.ipc
lazy_preload = False
use_shm_server = False
shm_ipc_dir = {CFG_DIR}/ipc

[block]
type = sqlite3
db = {STOCK_DB}

[preload]
day = True
week = False
month = False
quarter = False
halfyear = False
year = False
day_max = 100000

[baseinfo]
type = sqlite3
db = {STOCK_DB}

[kdata]
type = hdf5
sh_day = {DATA_DIR}/sh_day.h5
sh_min = {DATA_DIR}/sh_1min.h5
sh_min5 = {DATA_DIR}/sh_5min.h5
sz_day = {DATA_DIR}/sz_day.h5
sz_min = {DATA_DIR}/sz_1min.h5
sz_min5 = {DATA_DIR}/sz_5min.h5
bj_day = {DATA_DIR}/bj_day.h5
bj_min = {DATA_DIR}/bj_1min.h5
bj_min5 = {DATA_DIR}/bj_5min.h5
"""
    HIKYUU_INI.write_text(ini, encoding="utf-8")
    return HIKYUU_INI
