import asyncio
import base64
import tempfile
import os
import re

from langchain_core.callbacks import BaseCallbackHandler
from langchain_gigachat import GigaChat
from langchain_core.output_parsers import StrOutputParser

from agent.state import AgentState
from agent.prompts import CODE_PROMPT, get_boilerplate
from agent.output_parsers import extract_ts_code
from agent.validator import run_tsc, run_ts_function
from utils.converter import convert_to_csv

llm = GigaChat(verify_ssl_certs=False, temperature=0)

_PRESERVE_TYPES = {"xlsx", "xls"}


class TokenCounter(BaseCallbackHandler):
    def __init__(self):
        self.total = 0

    def on_llm_end(self, response, **kwargs):
        usage = (response.llm_output or {}).get("token_usage", {})
        self.total += usage.get("total_tokens", 0)


_PROP_LINE_RE = re.compile(r'^\s{2,}[a-zA-Z_][a-zA-Z0-9_]*\s*:')
_VALUE_END_RE  = re.compile(r'[)\]"\'a-zA-Z0-9_]$')


def _add_missing_commas(ts_code: str) -> str:
    """Построчно добавляет запятые перед строками-свойствами объекта."""
    lines = ts_code.split('\n')
    result = []
    for i, line in enumerate(lines):
        rline = line.rstrip()
        if (i < len(lines) - 1
                and _PROP_LINE_RE.match(lines[i + 1])
                and _VALUE_END_RE.search(rline)
                and not rline.endswith(',')):
            result.append(rline + ',')
        else:
            result.append(line)
    return '\n'.join(result)


def fix_common_errors(ts_code: str) -> str:
    # исправляем toNum(get(VAR, '...(с НДС)'), → toNum(get(VAR, '...(с НДС)')),
    # VAR может быть cells (CSV) или row (XLSX/JSON)
    ts_code = re.sub(
        r"toNum\(get\((\w+),\s*'([^']+\(с НДС\))'\),",
        r"toNum(get(\1, '\2')),",
        ts_code
    )
    # исправляем ccells → cells
    ts_code = ts_code.replace('ccells', 'cells')
    # исправляем toBool(get(...) === '...') → get(...) === '...'
    ts_code = re.sub(
        r'toBool\((get\(cells,\s*\'[^\']+\'\)\s*===\s*\'[^\']+\')\)',
        r'\1',
        ts_code
    )
    # добавляем пропущенные запятые между свойствами объекта
    ts_code = _add_missing_commas(ts_code)
    return ts_code


def _get_parser(file_type: str):
    if file_type == "csv":
        from parsers.csv_parser import _generate_schema_hint
        return _generate_schema_hint
    elif file_type == "pdf":
        from parsers.pdf_parser import generate_schema_hint
        return generate_schema_hint
    elif file_type == "docx":
        from parsers.docx_parser import generate_schema_hint
        return generate_schema_hint
    elif file_type in ("jpg", "jpeg", "png"):
        from parsers.image_parser import generate_schema_hint
        return generate_schema_hint
    else:
        raise ValueError(f"Unsupported file_type: {file_type}")


async def parse_file(state: AgentState) -> dict:
    file_type = state["file_type"].lower()
    raw_bytes = base64.b64decode(state["file_b64"])

    original_type  = file_type
    original_bytes = raw_bytes

    raw_bytes, file_type = convert_to_csv(raw_bytes, file_type)
    parser = _get_parser(file_type)

    with tempfile.NamedTemporaryFile(suffix=f".{file_type}", delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        schema_hint = await asyncio.to_thread(parser, tmp_path)
    finally:
        os.unlink(tmp_path)

    # Для изображений image_parser кладёт CSV в schema_hint["_csv_bytes_b64"].
    csv_b64 = schema_hint.pop("_csv_bytes_b64", None)
    schema_hint.pop("_original_type", None)
    if csv_b64:
        return {
            "schema_hint": schema_hint,
            "file_b64":    csv_b64,
            "file_type":   "csv",
        }

    # Для xlsx/xls/json/jsonl — schema_hint строится из CSV-представления,
    # но в TypeScript передаём оригинальный файл.
    if original_type in _PRESERVE_TYPES:
        schema_hint["file_type"] = original_type
        return {
            "schema_hint": schema_hint,
            "file_b64":    base64.b64encode(original_bytes).decode(),
            "file_type":   original_type,
        }

    return {
        "schema_hint": schema_hint,
        "file_b64":    base64.b64encode(raw_bytes).decode(),
        "file_type":   file_type,
    }


async def generate_code(state: AgentState) -> dict:
    schema  = state["schema_hint"]
    counter = TokenCounter()
    chain   = CODE_PROMPT | llm | StrOutputParser()

    errors = state.get("errors", [])
    retry  = state.get("retry_count", 0)
    tokens = state.get("tokens_used", 0)

    if errors:
        errors_str = f"Попытка {retry}. Исправь эти ошибки:\n" + "\n".join(errors)
    else:
        errors_str = "Первая попытка — ошибок нет."

    file_type = schema["file_type"]
    separator = schema.get("separator") or ";"

    raw = await chain.ainvoke(
        {
            "file_type":   file_type,
            "separator":   separator,
            "row_count":   schema["row_count"],
            "col_count":   schema["col_count"],
            "columns":     schema["columns"],
            "target_json": state["target_json"],
            "errors":      errors_str,
            "boilerplate": get_boilerplate(file_type, separator),
        },
        config={"callbacks": [counter]}
    )

    ts_code = extract_ts_code(raw)
    ts_code = fix_common_errors(ts_code)

    return {
        "ts_code":     ts_code,
        "tokens_used": tokens + counter.total,
    }


async def validate_code(state: AgentState) -> dict:
    ts_code = state.get("ts_code", "")

    if not ts_code:
        return {
            "is_valid":    False,
            "errors":      ["LLM вернула пустой код"],
            "retry_count": state.get("retry_count", 0) + 1,
            "result_json": [],
        }

    is_valid, errors = await asyncio.to_thread(run_tsc, ts_code)

    result_json = []
    if is_valid:
        is_valid, result_json, err = await asyncio.to_thread(run_ts_function,
            ts_code,
            state["file_b64"],
            state.get("file_type", "csv"),
        )
        if not is_valid:
            errors = [err]

    return {
        "is_valid":    is_valid,
        "errors":      errors,
        "retry_count": state.get("retry_count", 0) + 1,
        "result_json": result_json,
    }