#!/usr/bin/env python3
"""连板选股 CLI。只读 get 的 JSON，不写复盘库。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from streakpicker.pick import PickError, pick  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从 daily-market-review 的 get 结果生成连板候选")
    subparsers = parser.add_subparsers(dest="command", required=True)
    pick_parser = subparsers.add_parser("pick", help="按已定稿规则输出强势板块、龙头、一排和二排")
    pick_parser.add_argument("--input", default="-", help="get 的完整 JSON；- 表示标准输入")
    args = parser.parse_args(argv)
    if args.command == "pick":
        return cmd_pick(args)
    parser.error(f"未知命令：{args.command}")
    return 2


def cmd_pick(args: argparse.Namespace) -> int:
    try:
        payload = _read_json(args.input)
        data = _unwrap_get(payload)
        _success(pick(data))
    except PickError as exc:
        _failure(exc.message)
        return 1
    except json.JSONDecodeError:
        _failure("pick 输入不是合法 JSON")
        return 1
    return 0


def _read_json(source: str) -> Any:
    if source == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(source).read_text(encoding="utf-8")
    if not raw.strip():
        raise PickError("pick 输入为空")
    return json.loads(raw)


def _unwrap_get(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PickError("pick 输入必须是 JSON 对象")
    if "ok" in payload:
        if payload.get("ok") is not True:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            code = error.get("code") or "GET_FAILED"
            message = error.get("message") or "get 未成功"
            raise PickError(f"get 未成功：{code} {message}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise PickError("get 成功响应缺少 data 对象")
        return data
    return payload


def _success(data: dict[str, Any]) -> None:
    json.dump({"ok": True, "data": data, "error": None}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def _failure(message: str) -> None:
    json.dump(
        {"ok": False, "data": None, "error": {"code": "PICK_FAILED", "message": message}},
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
