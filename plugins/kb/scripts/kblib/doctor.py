"""Read-only checks for the plugin shell."""

import os
import sys

from .config import config_path, resolve_vault


def diagnose() -> dict:
    vault = resolve_vault()
    checks = [
        {"name": "python", "ok": sys.version_info >= (3, 9), "message": "Python 版本需要为 3.9 或更高"},
        {"name": "vault", "ok": os.access(vault, os.R_OK | os.X_OK), "message": "知识库目录需要可读取和进入"},
    ]
    ok = all(check["ok"] for check in checks)
    return {
        "ok": ok, "config": str(config_path()), "vault": str(vault), "checks": checks,
        "error": None if ok else "自检发现问题，请按检查结果修复后重试。",
    }
