from functools import cache
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from agent.state import AgentState
from agent.nodes import parse_file, generate_code, validate_code


def should_retry(state: AgentState) -> str:
    if state.get("is_valid"):
        return END
    if state.get("retry_count", 0) >= 3:
        return END
    return "generate_code"


workflow = StateGraph(AgentState)

workflow.add_node("parse_file",    parse_file)
workflow.add_node("generate_code", generate_code)
workflow.add_node("validate_code", validate_code)

workflow.set_entry_point("parse_file")
workflow.add_edge("parse_file",    "generate_code")
workflow.add_edge("generate_code", "validate_code")

workflow.add_conditional_edges(
    "validate_code",
    should_retry,
    {
        "generate_code": "generate_code",
        END: END,
    }
)


@cache
def get_graph_agent() -> CompiledStateGraph:
    return workflow.compile()