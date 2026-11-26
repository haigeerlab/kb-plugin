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


def read_optional_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return ''
    except (OSError, UnicodeError):
        raise KbError('无法读取脱敏配置文件，需要可读取的 UTF-8 文本') from None


def load_blocklist(environ: Mapping[str, str] = os.environ) -> list:
    text = read_optional_text(config_path(environ).parent / 'blocklist.txt')
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]


def load_aliases(environ: Mapping[str, str] = os.environ) -> dict:
    path = config_path(environ).parent / 'aliases.json'
    text = read_optional_text(path)
    if not text and not path.exists():
        return {}
    try:
        aliases = json.loads(text)
    except ValueError:
        raise KbError('代号配置 aliases.json：JSON 格式错误') from None
    if (not isinstance(aliases, dict)
            or any(not isinstance(name, str) or not name or not isinstance(alias, str) or not alias
                   for name, alias in aliases.items())):
        raise KbError('代号配置 aliases.json：必须是非空名称到非空代号字符串的 JSON 对象')
    return aliases


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


def init_redaction(confirm: bool = False) -> dict:
    path = config_path()
    templates = {
        'blocklist.txt': (
            '# 本地黑名单：一行一个词，不区分大小写，按子串匹配。\n'
            '# 以 # 开头的行是注释。\n'
            '# 在这里写客户名、品牌、公司域名等不能进知识库的词。\n'
            '# 这个文件只留在本机，不要放进任何仓库。\n'
        ),
        'aliases.json': '{}\n',
    }
    result = {'ok': True, 'config': str(path), 'create': [], 'skip': [],
              'written': confirm, 'error': None}
    try:
        for name, content in templates.items():
            target = path.parent / name
            if os.path.lexists(target):
                result['skip'].append(name)
                continue
            if confirm:
                missing = []
                directory = path.parent
                while not directory.exists():
                    missing.append(directory)
                    directory = directory.parent
                for directory in reversed(missing):
                    directory.mkdir(mode=0o700, exist_ok=True)
                try:
                    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    # A concurrent creator wins, including a newly added symlink.
                    result['skip'].append(name)
                    continue
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(content)
            result['create'].append(name)
    except OSError:
        raise KbError(f'脱敏配置 {path.parent}：无法创建文件，可能已部分创建；请检查路径与权限后重新预览') from None
    return result


CAPTURE_DEFAULTS = {'session_capture': True, 'capture_min_user_messages': 2,
                    'capture_ignore_dirs': [], 'delegate_capture': True,
                    'delegate_min_answer_bytes': 200}


def _capture_config(environ):
    path = config_path(environ)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, ValueError):
        raise KbError(f'采集配置 {path}：无法读取配置或 JSON 损坏') from None
    if not isinstance(data, dict):
        raise KbError(f'采集配置 {path}：配置必须是 JSON 对象')
    if 'version' in data and (type(data['version']) is not int or data['version'] != 1):
        raise KbError(f'采集配置 {path}：version 仅支持整数 1')
    return data


def _capture_settings(data):
    settings = {key: data.get(key, default) for key, default in CAPTURE_DEFAULTS.items()}
    if type(settings['session_capture']) is not bool:
        raise KbError('采集配置：session_capture 必须是布尔值')
    if type(settings['delegate_capture']) is not bool:
        raise KbError('采集配置：delegate_capture 必须是布尔值')
    minimum_bytes = settings['delegate_min_answer_bytes']
    if type(minimum_bytes) is not int or minimum_bytes < 0:
        raise KbError('采集配置：delegate_min_answer_bytes 必须是非负整数')
    minimum = settings['capture_min_user_messages']
    if type(minimum) is not int or minimum <= 0:
        raise KbError('采集配置：capture_min_user_messages 必须是正整数')
    ignored = settings['capture_ignore_dirs']
    if (not isinstance(ignored, list)
            or any(not isinstance(value, str) or not value.strip() or '\0' in value for value in ignored)):
        raise KbError('采集配置：capture_ignore_dirs 必须是非空路径字符串的数组')
    return settings


def load_capture(environ: Mapping[str, str] = os.environ) -> dict:
    return _capture_settings(_capture_config(environ))


def set_capture(enabled, min_user_messages=None, ignore_dirs=None, confirm=False) -> dict:
    path = config_path()
    content = _capture_config(os.environ)
    content.setdefault('version', 1)
    content['session_capture'] = enabled
    if min_user_messages is not None:
        content['capture_min_user_messages'] = min_user_messages
    if ignore_dirs is not None:
        content['capture_ignore_dirs'] = ignore_dirs
    settings = _capture_settings(content)
    # Keep implicit delegate defaults out of existing session-only config files.
    content.update({key: value for key, value in settings.items()
                    if not key.startswith('delegate_') or key in content})
    if confirm:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except (OSError, UnicodeError):
            raise KbError(f'采集配置 {path}：无法写入配置文件，请检查路径与权限') from None
    return {'ok': True, 'config': str(path), 'content': content, 'written': confirm, 'error': None}
