import base64
import tempfile
import os

from langchain_gigachat import GigaChat
from langchain_core.output_parsers import StrOutputParser

from agent.state import AgentState
from agent.prompts import CODE_PROMPT
from agent.output_parsers import extract_ts_code
from agent.validator import run_tsc, run_ts_function

llm = GigaChat(verify_ssl_certs=False)


def _get_parser(file_type: str):
    if file_type == "csv":
        from parsers.csv_parser import _generate_schema_hint
        return _generate_schema_hint
    elif file_type == "json":
        from parsers.json_parser import generate_schema_hint
        return generate_schema_hint
    elif file_type == "jsonl":
        from parsers.jsonl_parser import generate_schema_hint
        return generate_schema_hint
    elif file_type == "tsv":
        from parsers.tsv_parser import generate_schema_hint
        return generate_schema_hint
    elif file_type == "pdf":
        from parsers.pdf_parser import generate_schema_hint
        return generate_schema_hint
    elif file_type == "docx":
        from parsers.docx_parser import generate_schema_hint
        return generate_schema_hint
    elif file_type == "xlsx":
        from parsers.xlsx_parser import _generate_schema_hint
        return _generate_schema_hint
    elif file_type == "xls":
        from parsers.xls_parser import generate_schema_hint
        return generate_schema_hint
    else:
        raise ValueError(f"Unsupported file_type: {file_type}")


async def parse_file(state: AgentState) -> dict:
    file_type = state["file_type"].lower()
    raw_bytes = base64.b64decode(state["file_b64"])

    parser = _get_parser(file_type)

    with tempfile.NamedTemporaryFile(suffix=f".{file_type}", delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        schema_hint = parser(tmp_path)
    finally:
        os.unlink(tmp_path)

    return {"schema_hint": schema_hint}


async def generate_code(state: AgentState) -> dict:
    schema = state["schema_hint"]
    chain  = CODE_PROMPT | llm | StrOutputParser()

    errors = state.get("errors", [])
    retry  = state.get("retry_count", 0)
    tokens = state.get("tokens_used", 0)

    if errors:
        errors_str = f"Попытка {retry}. Исправь эти ошибки:\n" + "\n".join(errors)
    else:
        errors_str = "Первая попытка — ошибок нет."

    raw = await chain.ainvoke({
        "file_type":   schema["file_type"],
        "separator":   schema.get("separator") or "",
        "row_count":   schema["row_count"],
        "col_count":   schema["col_count"],
        "columns":     schema["columns"],
        "target_json": state["target_json"],
        "errors":      errors_str,
    })

    ts_code = extract_ts_code(raw)

    return {
        "ts_code":     ts_code,
        "tokens_used": tokens + len(raw) // 4,
    }


async def validate_code(state: AgentState) -> dict:
    ts_code = state.get("ts_code", "")

    # guard — пустой код
    if not ts_code:
        return {
            "is_valid":    False,
            "errors":      ["LLM вернула пустой код"],
            "retry_count": state.get("retry_count", 0) + 1,
            "result_json": [],
        }

    # guard — несбалансированные скобки
    opens  = ts_code.count('(')
    closes = ts_code.count(')')
    if opens != closes:
        return {
            "is_valid":    False,
            "errors":      [
                f"Несбалансированные скобки: открытых={opens}, закрытых={closes}. "
                f"Найди строку с 'НДС' — там ошибка: toNum(get(cells, '...НДС)'), "
                f"исправь на toNum(get(cells, '...НДС)')),  — нужны две )) перед запятой. "
                f"Проверь ВСЕ колонки содержащие скобки в названии."
            ],
            "retry_count": state.get("retry_count", 0) + 1,
            "result_json": [],
        }

    # guard — опечатка ccells
    if 'ccells' in ts_code:
        return {
            "is_valid":    False,
            "errors":      ["Опечатка: найдено 'ccells' — замени на 'cells'. ВЕРНО: siteLead: toBool(get(cells, 'Сделка - Лид с сайта'))"],
            "retry_count": state.get("retry_count", 0) + 1,
            "result_json": [],
        }

    # проверка 1: tsc компиляция
    is_valid, errors = run_tsc(ts_code)
    print(f"DEBUG tsc: is_valid={is_valid}, errors={errors}")

    result_json = []
    if is_valid:
        # проверка 2: runtime на реальных данных
        is_valid, result_json, err = run_ts_function(
            ts_code,
            state["file_b64"],
            state.get("file_type", "csv"),
        )
        if not is_valid:
            errors = [err]
            print(f"DEBUG run_ts_function error: {err}")

    return {
        "is_valid":    is_valid,
        "errors":      errors,
        "retry_count": state.get("retry_count", 0) + 1,
        "result_json": result_json,
    }