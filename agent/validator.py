import subprocess
import tempfile
import os
import json
import shutil
import os as _os

TS_NODE = shutil.which("ts-node") or r"C:\Users\meepo\AppData\Roaming\npm\ts-node.cmd"
TSC     = shutil.which("tsc")     or r"C:\Users\meepo\AppData\Roaming\npm\tsc.cmd"

_TEXT_TYPES = {"csv", "tsv", "json", "jsonl"}


def run_tsc(ts_code: str) -> tuple[bool, list[str], str]:
    if not ts_code:
        return False, ["ts_code пустой"], ""

    # добавляем объявления чтобы tsc не ругался на внешние зависимости
    prelude = "declare const XLSX: any;\ntype TargetData = Record<string, any>;\n\n"
    full_code = prelude + ts_code

    with tempfile.NamedTemporaryFile(
        suffix=".ts", delete=False,
        mode="w", encoding="utf-8"
    ) as f:
        f.write(full_code)
        fname = f.name
    try:
        r = subprocess.run(
            [TSC, "--noEmit", "--target", "ES2020", "--strictNullChecks", "false", fname],
            capture_output=True, text=True, timeout=15
        )
        ok     = r.returncode == 0
        errors = r.stdout.strip().splitlines() if not ok else []
        tsc_out = r.stdout.strip() if r.stdout.strip() else ("tsc → 0 errors" if ok else "")
        return ok, errors, tsc_out
    except FileNotFoundError:
        return True, [], "tsc not found, skipped"
    finally:
        os.unlink(fname)


def run_ts_function(ts_code: str, file_b64: str, file_type: str = "csv") -> tuple[bool, list[dict], str]:
    import base64 as b64lib

    # для текстовых форматов убираем BOM и перекодируем в чистый utf-8
    if file_type in _TEXT_TYPES:
        csv_text  = b64lib.b64decode(file_b64).decode("utf-8-sig")
        clean_b64 = b64lib.b64encode(csv_text.encode("utf-8")).decode()
    else:
        clean_b64 = file_b64  # для xlsx передаём бинарный base64 как есть

    # пишем base64 в отдельный файл — безопасно от кавычек в f-string
    with tempfile.NamedTemporaryFile(
        suffix=".txt", delete=False,
        mode="w", encoding="utf-8"
    ) as bf:
        bf.write(clean_b64)
        b64_fname = bf.name

    js_code = ts_code.replace("export default function", "function transform")

    runner = f"""
const fs   = require('fs');
const XLSX = require('xlsx');
global.atob = (b) => Buffer.from(b, 'base64').toString('utf-8');

{js_code}

const clean_b64 = fs.readFileSync({repr(b64_fname)}, 'utf-8').trim();
const result = transform(clean_b64);
process.stdout.write(JSON.stringify(result));
"""
    with tempfile.NamedTemporaryFile(
        suffix=".ts", delete=False,
        mode="w", encoding="utf-8"
    ) as f:
        f.write(runner)
        fname = f.name

    try:
        r = subprocess.run(
            [TS_NODE, "--skip-project", "--transpile-only",
             "--compiler-options", '{"module":"CommonJS","target":"ES2020"}',
             fname],
            capture_output=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
            env={
                **_os.environ,
                "NODE_PATH": r"C:\work\hack_3\node_modules",  # ← путь к node_modules
            }
        )
        if r.returncode != 0:
            print(f"DEBUG stderr: {r.stderr[:500]}")
            return False, [], r.stderr.strip(), r.stderr.strip()
        if not r.stdout:
            print(f"DEBUG stdout empty, stderr: {r.stderr[:200]}")
            return False, [], "stdout empty", r.stderr.strip()
        data = json.loads(r.stdout)
        return True, data, "", r.stderr.strip()
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"DEBUG exception: {e}")
        return False, [], str(e), ""
    finally:
        os.unlink(fname)
        os.unlink(b64_fname)