import base64
from io import StringIO

import pandas as pd
from langchain_gigachat import GigaChat
from langchain_core.output_parsers import StrOutputParser

from agent.state import AgentState
from agent.prompts import CODE_PROMPT
from agent.output_parsers import extract_ts_code
from agent.validator import run_tsc, run_ts_function

llm = GigaChat(verify_ssl_certs=False)


async def parse_file(state: AgentState) -> dict:
    raw = base64.b64decode(state["file_b64"]).decode("utf-8-sig")
    sep = ";" if raw.count(";") > raw.count(",") else ","
    df  = pd.read_csv(StringIO(raw), sep=sep, nrows=5)

    columns = []
    for col in df.columns:
        s = df[col].dropna()
        columns.append({
            "name":     col,
            "dtype":    str(df[col].dtype),
            "sample":   s.head(2).tolist(),
            "nullable": bool(df[col].isna().any()),
        })

    return {"schema_hint": {
        "file_type": "csv",
        "separator": sep,
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns":   columns,
    }}


async def generate_code(state: AgentState) -> dict:
    schema = state["schema_hint"]
    chain  = CODE_PROMPT | llm | StrOutputParser()

    errors    = state.get("errors", [])
    retry     = state.get("retry_count", 0)
    tokens    = state.get("tokens_used", 0)

    if errors:
        errors_str = f"Попытка {retry}. Исправь эти ошибки:\n" + "\n".join(errors)
    else:
        errors_str = "Первая попытка — ошибок нет."

    raw = await chain.ainvoke({
        "file_type":   schema["file_type"],
        "separator":   schema.get("separator", ","),
        "row_count":   schema["row_count"],
        "col_count":   schema["col_count"],
        "columns":     schema["columns"],
        "target_json": state["target_json"],
        "errors":      errors_str,
    })

    ts_code = extract_ts_code(raw)

    return {
        "ts_code":    ts_code,
        "tokens_used": tokens + len(raw) // 4,
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

    # проверка 1: tsc компиляция
    is_valid, errors = run_tsc(ts_code)

    result_json = []
    if is_valid:
        is_valid, result_json, err = run_ts_function(
            ts_code,
            state["file_b64"],
        )
        if not is_valid:
            errors = [err]

    return {
        "is_valid":    is_valid,
        "errors":      errors,
        "retry_count": state.get("retry_count", 0) + 1,
        "result_json": result_json,
    }