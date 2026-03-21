import subprocess
import tempfile
import os
import json

TS_NODE = r"C:\Users\meepo\AppData\Roaming\npm\ts-node.cmd"

def run_tsc(ts_code: str) -> tuple[bool, list[str]]:
    with tempfile.NamedTemporaryFile(
        suffix=".ts", delete=False,
        mode="w", encoding="utf-8"
    ) as f:
        f.write(ts_code)
        fname = f.name
    try:
        r = subprocess.run(
            ["tsc", "--noEmit", "--strict", "--target", "ES2020", fname],
            capture_output=True, text=True, timeout=15
        )
        ok     = r.returncode == 0
        errors = r.stderr.strip().splitlines() if not ok else []
        return ok, errors
    except FileNotFoundError:
        return True, []
    finally:
        os.unlink(fname)


def run_ts_function(ts_code: str, file_b64: str) -> tuple[bool, list[dict], str]:
    import base64 as b64lib
    csv_text = b64lib.b64decode(file_b64).decode("utf-8-sig")
    clean_b64 = b64lib.b64encode(csv_text.encode("utf-8")).decode()

    runner = f"""
global.atob = (b: string) => Buffer.from(b, 'base64').toString('utf-8');

{ts_code.replace('export default function', 'function transform')}

const result = transform("{clean_b64}");
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
            encoding="utf-8",   # ← явно utf-8 вместо cp1251
            errors="replace",   # ← не падать на невалидных символах
        )
        if r.returncode != 0:
            return False, [], r.stderr.strip()
        if not r.stdout:
            return False, [], "stdout empty"
        data = json.loads(r.stdout)
        return True, data, ""
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return False, [], str(e)
    finally:
        os.unlink(fname)