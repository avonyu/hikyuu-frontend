"""应用包初始化。

hikyuu 在 import 时会无条件在用户主目录建 `~/.hikyuu` 并写日志文件。
受限账户、沙箱环境或漫游配置异常时这一步会抛 PermissionError，整个应用
（包括 seed 脚本）都起不来。这里在导入 hikyuu 之前先探测主目录可写性，
不可写就把 HOME 重定向到 `data_root/home`，让项目自包含。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# HDF5 默认会对文件加字节锁。后端进程加载行情后会一直持有句柄，
# 此时 seed 脚本再以写模式打开同一文件就会失败（Win32 GetLastError()=33）。
# 单机自用场景下关闭文件锁；代价是并发写没有保护，别同时跑两个导入。
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

_MARKER = ".write_test"


def _data_root() -> Path:
    env = os.environ.get("HK_DATA_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    # app/__init__.py -> backend/app -> backend -> 仓库根
    return Path(__file__).resolve().parents[2] / "data_root"


def _redirect_home_if_needed() -> None:
    home = Path(os.path.expanduser("~"))
    probe = home / ".hikyuu" / _MARKER
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.touch()
        probe.unlink()
        return
    except OSError:
        pass

    fallback = _data_root() / "home"
    fallback.mkdir(parents=True, exist_ok=True)
    drive = fallback.drive or "C:"
    os.environ["USERPROFILE"] = str(fallback)
    os.environ["HOME"] = str(fallback)
    os.environ["HOMEDRIVE"] = drive
    os.environ["HOMEPATH"] = str(fallback)[len(drive):]
    print(
        f"[hikyuu] 用户目录不可写（{home}），已把 HOME 重定向到 {fallback}",
        file=sys.stderr,
    )


_redirect_home_if_needed()
