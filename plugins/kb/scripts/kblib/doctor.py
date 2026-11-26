"""Read-only checks for the plugin shell."""

import os
from pathlib import Path
import shlex
import sys

from .config import config_path, resolve_vault


def diagnose() -> dict:
    vault = resolve_vault()
    checks = [
        {"name": "python", "ok": sys.version_info >= (3, 9), "message": "Python 版本需要为 3.9 或更高"},
        {"name": "vault", "ok": os.access(vault, os.R_OK | os.X_OK), "message": "知识库目录需要可读取和进入"},
    ]
    ok = all(check["ok"] for check in checks)
    entry = shlex.quote(str(Path(__file__).resolve().parents[1] / 'kb.py'))
    command = f'python3 -B {entry} config init-redaction'
    for name, filename, rule in (
            ('blocklist', 'blocklist.txt', '本地黑名单拦截规则'),
            ('aliases', 'aliases.json', '真实名称到项目代号的替换规则')):
        path = config_path().parent / filename
        # Existence only: never open the user's rule files.
        if os.path.exists(path):
            level, message = 'info', f'脱敏规则文件已存在：{path}'
        elif os.path.lexists(path):
            level, message = 'warn', f'{path} 是符号链接但目标不存在，{rule}不生效；请修复链接或删除后重新创建。'
        else:
            level, message = 'warn', (f'缺少 {path}，{rule}不生效；请运行 {command} 预览，'
                                      '确认后追加 --confirm 创建空模板，规则内容由用户自己填写。')
        # Reminders never fail doctor, so ok stays true: ok:false keeps meaning "failed".
        checks.append({'name': name, 'ok': True, 'level': level, 'message': message})
    return {
        "ok": ok, "config": str(config_path()), "vault": str(vault), "checks": checks,
        "error": None if ok else "自检发现问题，请按检查结果修复后重试。",
    }
