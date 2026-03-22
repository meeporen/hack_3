import re

def extract_ts_code(raw: str) -> str:
    if not raw or not raw.strip():
        return ""

    m = re.search(r"```typescript\s*(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()

    m = re.search(r"```\s*(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()

    if raw.strip().startswith(("interface", "export", "type", "const")):
        return raw.strip()

    return raw.strip()