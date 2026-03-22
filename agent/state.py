from typing import TypedDict

class AgentState(TypedDict):
    file_b64:          str
    file_type:         str
    target_json:       dict
    schema_hint:       dict
    ts_code:           str
    tokens_used:       int
    prompt_tokens:     int
    completion_tokens: int
    is_valid:          bool
    errors:            list[str]
    retry_count:       int
    result_json:       list[dict]
    console_output:    str
    job_id:            str
