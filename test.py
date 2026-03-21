import asyncio
import base64
import json
from dotenv import load_dotenv

load_dotenv()

async def test():
    from agent.graph import get_graph_agent

    with open("crmData.csv", "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    with open("crm.json", encoding="utf-8") as f:
        target = json.load(f)[0]

    print("запускаем граф...")
    result = await get_graph_agent().ainvoke({
        "file_b64":    b64,
        "file_type":   "csv",
        "target_json": target,
    })

    print(f"valid:      {result['is_valid']}")
    print(f"retries:    {result['retry_count']}")
    print(f"records:    {len(result.get('result_json', []))}")
    print()
    print("=== сгенерированный TypeScript ===")
    print(result["ts_code"])
    print()

    if result.get("result_json"):
        # сохраняем в файл
        with open("result.json", "w", encoding="utf-8") as f:
            json.dump(result["result_json"], f, ensure_ascii=False, indent=2)
        print("=== результат сохранён в result.json ===")
        print(json.dumps(result["result_json"][0], ensure_ascii=False, indent=2))
    else:
        print("errors:", result.get("errors"))

asyncio.run(test())