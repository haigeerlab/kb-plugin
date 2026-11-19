"""Explicit configuration storage and vault resolution."""

import json
import os
from pathlib import Path
import shlex
from typing import Mapping

from . import KbError


CONFIG_ENV = "KB_CONFIG"
DEFAULT_CONFIG = Path.home() / ".config" / "kb" / "config.json"


class VaultNotConfigured(KbError):
    pass


def config_path(environ: Mapping[str, str] = os.environ) -> Path:
    return Path(environ.get(CONFIG_ENV) or DEFAULT_CONFIG).expanduser().absolute()


def configuration_error(path: Path, reason: str) -> VaultNotConfigured:
    entry = shlex.quote(str(Path(__file__).resolve().parents[1] / "kb.py"))
    return VaultNotConfigured(
        f"配置 {path}：{reason}；请运行 python3 -B {entry} config set-vault <路径> "
        "预览，确认后追加 --confirm 写入。"
    )


def resolve_vault(environ: Mapping[str, str] = os.environ) -> Path:
    """Return the configured vault. Never discover a vault from cwd."""
    path = config_path(environ)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise configuration_error(path, "未找到配置文件") from None
    except (OSError, UnicodeError):
        raise configuration_error(path, "无法读取配置文件（需要 UTF-8 文本）") from None
    try:
        data = json.loads(raw)
    except ValueError:
        raise configuration_error(path, "JSON 损坏") from None
    if not isinstance(data, dict):
        raise configuration_error(path, "配置必须是 JSON 对象")
    if type(data.get("version")) is not int or data["version"] != 1:
        raise configuration_error(path, "不支持的 version，当前仅支持整数 1")
    value = data.get("vault")
    if not isinstance(value, str) or not value:
        raise configuration_error(path, "vault 必须是非空的绝对路径字符串")
    vault = Path(value)
    if not vault.is_absolute():
        raise configuration_error(path, "vault 必须是绝对路径")
    try:
        if not vault.exists():
            raise configuration_error(path, f"知识库目录不存在：{vault}")
        if not vault.is_dir():
            raise configuration_error(path, f"知识库路径不是目录：{vault}")
    except (OSError, ValueError):
        raise configuration_error(path, "无法检查 vault 目录") from None
    return vault


def set_vault(value: str, confirm: bool = False) -> dict:
    path = config_path()
    try:
        vault = Path(value).expanduser().resolve()
        if not vault.is_dir():
            raise configuration_error(path, f"知识库路径必须是已存在的目录：{vault}")
    except (OSError, ValueError, RuntimeError):
        raise configuration_error(path, "无法解析知识库路径") from None
    content = {"version": 1, "vault": str(vault)}
    if confirm:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except (OSError, UnicodeError):
            raise configuration_error(path, "无法写入配置文件，请检查路径与权限") from None
    return {"ok": True, "config": str(path), "content": content, "written": confirm, "error": None}
