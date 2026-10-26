#!/usr/bin/env python3
"""One-time, owner-entered EmDash migration for the new diary D1 only."""
from __future__ import annotations

import termios
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SITE = Path(__file__).resolve().parents[1]
ACCOUNT = "7255fd8ded983ed62a629fe7bd775440"
DATABASE = "ddc23f40-9355-4b22-97f9-0256a0decd06"
WORKER = "yhei-diary-emdash"
TARGET_LABEL = f"{ACCOUNT}/{WORKER}/{DATABASE}"
PAUSE_VERSION = "12632ef3-c99d-453d-8f16-469d3f26d35c"
FINGERPRINT = "2a9a924b879044aa88afa743e56a1865cda3a786d78eeaa59d27bd04aad32026"
LOCK_ID = "1792925270916"
LOCK_SINCE = "2026-10-25T10:47:50.916Z"
EMDASH = SITE / "node_modules/.bin/emdash"
WRANGLER = SITE / "node_modules/.bin/wrangler"


def hidden_input(prompt: str) -> str:
    """Read from the controlling TTY only; never fall back to echoed stdin."""
    fd = os.open("/dev/tty", os.O_RDWR)
    original = termios.tcgetattr(fd)
    hidden = original.copy()
    hidden[3] &= ~(termios.ECHO | termios.ECHONL)
    try:
        termios.tcsetattr(fd, termios.TCSANOW, hidden)
        os.write(fd, prompt.encode())
        raw = os.read(fd, 1024)
        return raw.rstrip(b"\r\n").decode("utf-8")
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, original)
        os.write(fd, b"\n")
        os.close(fd)


class StopMigration(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StopMigration(message)


def parse_report(stdout: str) -> dict:
    # EmDash v1.3.1 emits the JSON report on stdout and target diagnostics on
    # stderr. Do not append stderr to stdout: that makes valid JSON look broken.
    try:
        report = json.loads(stdout.strip())
    except json.JSONDecodeError as error:
        raise StopMigration("公式 CLI の stdout が単一の JSON report ではありません。自動適用しません。") from error
    require(isinstance(report, dict), "公式 CLI の JSON report が object ではありません。")
    for field in ("target", "knownApplied", "pending", "unknownApplied", "executed"):
        require(field in report, f"公式 CLI の JSON report に必須項目 {field} がありません。")
    require(isinstance(report["target"], dict), "公式 CLI の target の型が違います。")
    for field in ("kind", "label", "fingerprint", "accountId", "resourceId"):
        require(isinstance(report["target"].get(field), str), f"公式 CLI の target.{field} の型が違います。")
    for field in ("knownApplied", "pending", "unknownApplied", "executed"):
        require(isinstance(report[field], list) and all(isinstance(name, str) for name in report[field]),
                f"公式 CLI の {field} の型が違います。")
    if "lock" in report:
        require(isinstance(report["lock"], dict) and
                isinstance(report["lock"].get("id"), str) and
                isinstance(report["lock"].get("heldSince"), str),
                "公式 CLI の lock の型が違います。")
    return report


def validate_report(report: dict, manifest_names: list[str], *, expect_pending: bool) -> None:
    target = report.get("target") or {}
    require(target.get("kind") == "d1", "移行対象の種類が D1 ではありません。")
    require(target.get("label") == TARGET_LABEL, "移行対象ラベルが違います。")
    require(target.get("accountId") == ACCOUNT, "移行対象アカウントが違います。")
    require(target.get("resourceId") == DATABASE, "移行対象 D1 UUID が違います。")
    require(target.get("fingerprint") == FINGERPRINT, "移行対象 fingerprint が変わりました。再評価が必要です。")
    require(not report.get("unknownApplied"), "未知の migration が DB にあります。")
    if expect_pending:
        require(report.get("knownApplied") == manifest_names[:40], "適用済み migration の状態が変わりました。")
        require(report.get("pending") == manifest_names[40:], "未適用 migration の状態が変わりました。")
        require(report.get("executed") == [], "migration 実行中または途中実行の記録があります。")
        lock = report.get("lock") or {}
        require(lock.get("id") == LOCK_ID and lock.get("heldSince") == LOCK_SINCE, "migration lock が変わりました。")
    else:
        require(report.get("knownApplied") == manifest_names, "公式 migration の適用数が一致しません。")
        require(report.get("pending") == [], "未適用 migration が残っています。")
        require(not report.get("lock"), "migration lock が残っています。")


def validate_deployments(records: list[dict]) -> None:
    require(isinstance(records, list) and records, "Worker deployment を確認できません。")
    current = max(records, key=lambda item: item.get("created_on", ""))
    versions = current.get("versions") or []
    require(len(versions) == 1 and versions[0].get("version_id") == PAUSE_VERSION and versions[0].get("percentage") == 100,
            "Worker が確認済み休止版から変わっています。")


def local_preflight() -> list[str]:
    require(EMDASH.is_file() and WRANGLER.is_file(), "project local CLI がありません。")
    require(datetime.now(timezone.utc) < datetime(2026, 10, 31, 10, 50, tzinfo=timezone.utc),
            "移行前 Time Travel bookmark の保管期限が近いか過ぎています。新しい復旧点が必要です。")
    require(not os.environ.get("CLOUDFLARE_API_TOKEN"), "既存 CLOUDFLARE_API_TOKEN を上書きできません。新しい Terminal を使ってください。")
    other_account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    require(not other_account or other_account == ACCOUNT, "既存 CLOUDFLARE_ACCOUNT_ID が違います。")
    manifest = json.loads((SITE / ".emdash/migrations.json").read_text())
    require(manifest.get("emdashVersion") == "1.3.1", "EmDash の build manifest が変わりました。")
    names = manifest["migrationSet"]["names"]
    require(len(names) == 90 and names[39] == "041_content_locale_list_index" and names[40] == "042_byline_fields",
            "migration manifest が確認済み状態と異なります。")
    paused = json.loads((SITE / "maintenance/wrangler.jsonc").read_text())
    require(paused.get("name") == WORKER and paused.get("account_id") == ACCOUNT and
            paused.get("preview_urls") is False and paused.get("triggers") == {"crons": []},
            "休止 Worker の設定が変わりました。")
    # Check only process names, not environment variables or command output.
    processes = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=True).stdout
    require(not any("emdash migrate" in line and "migrate_production_d1.py" not in line for line in processes.splitlines()),
            "別のローカル EmDash migration が実行中です。")
    result = subprocess.run([str(WRANGLER), "deployments", "list", "--name", WORKER, "--json"],
                            cwd=SITE, capture_output=True, text=True, timeout=40)
    require(result.returncode == 0, "Worker の現行 deployment を確認できません。")
    try:
        validate_deployments(json.loads(result.stdout))
    except json.JSONDecodeError as error:
        raise StopMigration("Worker deployment の JSON を解釈できません。") from error
    return names


def cli(token: str, *args: str, timeout: int = 90, report: bool = True) -> dict | None:
    env = os.environ.copy()
    env["CLOUDFLARE_API_TOKEN"] = token
    env["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT
    try:
        result = subprocess.run([str(EMDASH), "migrate", *args, "--account-id", ACCOUNT, "--d1", DATABASE],
                                cwd=SITE, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise StopMigration("公式 CLI がタイムアウトしました。結果不確実のため再実行せず status を点検してください。") from error
    finally:
        env.pop("CLOUDFLARE_API_TOKEN", None)
    # The official CLI writes machine-readable JSON only to stdout. Its target
    # diagnostics go to stderr. Keep the streams separate, and redact both.
    safe_stdout = result.stdout.replace(token, "[redacted]")
    safe_stderr = result.stderr.replace(token, "[redacted]")
    require(result.returncode == 0,
            "公式 CLI が失敗しました。結果不確実のため再実行せず status を点検してください。詳細: " +
            (safe_stderr + "\n" + safe_stdout)[:900])
    return parse_report(safe_stdout) if report else None


def main() -> int:
    require(sys.stdin.isatty() and sys.stderr.isatty(), "本人の Mac mini Terminal で直接起動してください。パイプ入力は受け付けません。")
    if sys.argv[1:] == ["--self-test"]:
        require(sys.stdin.isatty() and sys.stderr.isatty(), "self-test は Terminal で実行してください。")
        dummy = hidden_input("Dummy secret (Cloudflare token は入力しない): ")
        try:
            require(dummy == "dummy-secret-for-test", "dummy 入力が違います。")
            print("SELF TEST ONLY: 非表示入力を確認。Cloudflare には接続していません。")
            return 0
        finally:
            dummy = None
    require(not sys.argv[1:], "引数なしで起動してください。")
    names = local_preflight()
    print("日記 D1 の休止版、対象アカウント、migration manifest を確認しました。")
    print("Cloudflare で本人が新規作成した D1 Edit 限定 token を貼り付けて Enter。入力は表示・保存しません。")
    token = hidden_input("D1 token: ")
    try:
        require(token.startswith(("cfat_", "cfut_")) and 40 <= len(token) <= 256,
                "token の形式を確認できません。")
        first = cli(token, "--status", "--json")
        validate_report(first, names, expect_pending=True)
        print(f"対象 D1 {DATABASE}: 適用済み40、未適用50、lock {LOCK_ID}。15秒後に再照合します。")
        time.sleep(15)
        # The same local process/deployment guards and remote status must still hold.
        local_preflight()
        second = cli(token, "--status", "--json")
        validate_report(second, names, expect_pending=True)
        require(first == second, "観測中に D1 の migration 状態が変わりました。")
        print("状態が不変で、別のローカル migration もありません。公式 lock 引継ぎを実行します。")
        cli(token, "--take-over-lock", LOCK_ID, "--expected-target-fingerprint", FINGERPRINT,
            "--json", timeout=300, report=False)
        # An interrupted apply has an uncertain outcome; do not retry it automatically.
        checked = cli(token, "--check", "--json")
        validate_report(checked, names, expect_pending=False)
        print(f"完了: {len(checked['knownApplied'])}件適用済み、未適用0、lock なし。")
        return 0
    finally:
        token = None


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (StopMigration, OSError, KeyError, ValueError, EOFError) as error:
        print("停止: " + str(error), file=sys.stderr)
        raise SystemExit(1)
