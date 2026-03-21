import asyncio
import base64
import json
import os
from dotenv import load_dotenv

load_dotenv()

FORMATS = [
    ("crmData.csv",   "csv"),
    ("crmData.xlsx",  "xlsx"),
    ("crmData.xls",   "xls"),
    ("crmData.json",  "json"),
    ("crmData.jsonl", "jsonl"),
]

OUTPUT_DIR = "main_test"


async def run_one(graph, file_path: str, file_type: str, target: dict) -> dict:
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    return await graph.ainvoke({
        "file_b64":    b64,
        "file_type":   file_type,
        "target_json": target,
    })


async def main():
    from agent.graph import get_graph_agent

    with open("crm.json", encoding="utf-8") as f:
        target = json.load(f)[0]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    graph = get_graph_agent()

    summary = []

    for file_path, file_type in FORMATS:
        print(f"\n{'='*50}")
        print(f"Формат: {file_type}  ({file_path})")
        print('='*50)

        try:
            result = await run_one(graph, file_path, file_type, target)

            valid   = result["is_valid"]
            retries = result["retry_count"]
            records = len(result.get("result_json", []))
            tokens  = result.get("tokens_used", 0)

            print(f"valid:   {valid}")
            print(f"retries: {retries}")
            print(f"records: {records}")
            print(f"tokens:  {tokens}")

            out_path = os.path.join(OUTPUT_DIR, f"result_{file_type}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({
                    "file_type":   file_type,
                    "is_valid":    valid,
                    "retry_count": retries,
                    "tokens_used": tokens,
                    "ts_code":     result.get("ts_code", ""),
                    "errors":      result.get("errors", []),
                    "result_json": result.get("result_json", []),
                }, f, ensure_ascii=False, indent=2)

            print(f"Сохранено: {out_path}")
            summary.append({"file_type": file_type, "valid": valid, "retries": retries, "records": records, "tokens": tokens, "error": None})

        except Exception as e:
            print(f"ОШИБКА: {e}")
            summary.append({"file_type": file_type, "valid": False, "retries": 0, "records": 0, "tokens": 0, "error": str(e)})

    print(f"\n{'='*50}")
    print("ИТОГ:")
    print('='*50)
    for s in summary:
        status = "OK" if s["valid"] else "FAIL"
        err    = f"  ({s['error']})" if s["error"] else ""
        print(f"  {s['file_type']:<8} {status}  retries={s['retries']}  records={s['records']}  tokens={s['tokens']}{err}")

    summary_path = os.path.join(OUTPUT_DIR, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nСводка: {summary_path}")


asyncio.run(main())
