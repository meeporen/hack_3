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
from utils.langfuse_client import get_langfuse_client

llm = GigaChat(verify_ssl_certs=False, temperature=0)

_PRESERVE_TYPES = {"xlsx", "xls"}


class TokenCounter(BaseCallbackHandler):
    def __init__(self):
        self.total             = 0
        self.prompt_tokens     = 0
        self.completion_tokens = 0
        self.last_prompt       = ""
        self.last_completion   = ""

    def on_llm_start(self, serialized, prompts, **kwargs):
        self.last_prompt = prompts[0] if prompts else ""

    def on_llm_end(self, response, **kwargs):
        usage = (response.llm_output or {}).get("token_usage", {})
        self.prompt_tokens     += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        self.total             += usage.get("total_tokens", 0)
        try:
            self.last_completion = response.generations[0][0].text
        except Exception:
            pass


_PROP_LINE_RE = re.compile(r'^\s{2,}[a-zA-Z_][a-zA-Z0-9_]*\s*:')
_VALUE_END_RE  = re.compile(r'[)\]"\'a-zA-Z0-9_]$')


def _add_missing_commas(ts_code: str) -> str:
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
    ts_code = re.sub(
        r"toNum\(get\((\w+),\s*'([^']+\(с НДС\))'\),",
        r"toNum(get(\1, '\2')),",
        ts_code
    )
    ts_code = ts_code.replace('ccells', 'cells')
    ts_code = re.sub(
        r'toBool\((get\(cells,\s*\'[^\']+\'\)\s*===\s*\'[^\']+\')\)',
        r'\1',
        ts_code
    )
    # fix: get(row, '...').split(...) → (get(row, '...') ?? '').split(...)
    ts_code = re.sub(
        r"(get\(\w+,\s*'[^']+'\))\.split\(",
        r"(String(\1 ?? '')).split(",
        ts_code
    )
    # fix: get(row, '...').replace(...) → (get(row, '...') ?? '').replace(...)
    ts_code = re.sub(
        r"(get\(\w+,\s*'[^']+'\))\.replace\(",
        r"(String(\1 ?? '')).replace(",
        ts_code
    )
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

    v_in  = schema_hint.pop("_vision_prompt_tokens",     0) or 0
    v_out = schema_hint.pop("_vision_completion_tokens", 0) or 0
    schema_hint.pop("_strategy", None)

    vision_token_update = {}
    if v_in or v_out:
        langfuse = get_langfuse_client()
        job_id = state.get("job_id", "")
        if langfuse:
            with langfuse.start_as_current_observation(
                as_type="generation",
                name=f"vision_parse job={job_id[:8] if job_id else 'unknown'}",
                model="qwen/qwen2.5-vl-72b-instruct",
                metadata={"job_id": job_id, "file_type": original_type},
            ) as gen:
                gen.update(usage_details={"input": v_in, "output": v_out})
            langfuse.flush()
        vision_token_update = {
            "prompt_tokens":     state.get("prompt_tokens", 0)     + v_in,
            "completion_tokens": state.get("completion_tokens", 0) + v_out,
            "tokens_used":       state.get("tokens_used", 0)       + v_in + v_out,
        }

    csv_b64 = schema_hint.pop("_csv_bytes_b64", None)
    schema_hint.pop("_original_type", None)
    if csv_b64:
        return {
            "schema_hint": schema_hint,
            "file_b64":    csv_b64,
            "file_type":   "csv",
            **vision_token_update,
        }

    if original_type in _PRESERVE_TYPES:
        schema_hint["file_type"] = original_type
        return {
            "schema_hint": schema_hint,
            "file_b64":    base64.b64encode(original_bytes).decode(),
            "file_type":   original_type,
            **vision_token_update,
        }

    return {
        "schema_hint": schema_hint,
        "file_b64":    base64.b64encode(raw_bytes).decode(),
        "file_type":   file_type,
        **vision_token_update,
    }


async def generate_code(state: AgentState) -> dict:
    schema  = state["schema_hint"]
    counter = TokenCounter()
    chain   = CODE_PROMPT | llm | StrOutputParser()

    errors = state.get("errors", [])
    retry  = state.get("retry_count", 0)
    tokens = state.get("tokens_used", 0)
    prompt_acc     = state.get("prompt_tokens", 0)
    completion_acc = state.get("completion_tokens", 0)
    job_id = state.get("job_id", "")

    if errors:
        errors_str = f"Попытка {retry}. Исправь эти ошибки:\n" + "\n".join(errors)
    else:
        errors_str = "Первая попытка — ошибок нет."

    file_type = schema["file_type"]
    separator = schema.get("separator") or ";"

    langfuse = get_langfuse_client()
    trace_name = f"generate_code attempt={retry + 1} job={job_id[:8] if job_id else 'unknown'}"

    async def _invoke():
        return await chain.ainvoke(
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

    if langfuse:
        with langfuse.start_as_current_observation(
            as_type="generation",
            name=trace_name,
            model="GigaChat",
            metadata={"job_id": job_id},
        ) as generation:
            raw = await _invoke()
            generation.update(
                input=counter.last_prompt,
                output=counter.last_completion,
                usage_details={
                    "input":  counter.prompt_tokens,
                    "output": counter.completion_tokens,
                }
            )
        langfuse.flush()
        print(f"[langfuse] trace отправлен: {trace_name} | prompt={counter.prompt_tokens} completion={counter.completion_tokens}")
    else:
        raw = await _invoke()

    ts_code = extract_ts_code(raw)
    ts_code = fix_common_errors(ts_code)

    return {
        "ts_code":          ts_code,
        "tokens_used":      tokens + counter.total,
        "prompt_tokens":    prompt_acc + counter.prompt_tokens,
        "completion_tokens": completion_acc + counter.completion_tokens,
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

    is_valid, errors, tsc_out = await asyncio.to_thread(run_tsc, ts_code)

    console_lines = []
    if tsc_out:
        console_lines.append(tsc_out)
    else:
        console_lines.append("tsc → 0 errors ✓")

    result_json = []
    node_stderr = ""
    if is_valid:
        is_valid, result_json, err, node_stderr = await asyncio.to_thread(run_ts_function,
            ts_code,
            state["file_b64"],
            state.get("file_type", "csv"),
        )
        if node_stderr:
            console_lines.append(node_stderr)
        if not is_valid:
            errors = [err]

    return {
        "is_valid":      is_valid,
        "errors":        errors,
        "retry_count":   state.get("retry_count", 0) + 1,
        "result_json":   result_json,
        "console_output": "\n".join(console_lines),
    }