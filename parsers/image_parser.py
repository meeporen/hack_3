"""
image_parser.py

Pipeline: PNG/JPG → Llama-3.2-90B vision (OpenRouter) → JSON array → DataFrame → CSV → csv_parser → schema
"""

import base64
import json
import os
import re
import tempfile

import pandas as pd
from openai import OpenAI
from PIL import Image, ImageEnhance

from parsers.csv_parser import _generate_schema_hint

_MODEL = "qwen/qwen2.5-vl-72b-instruct"

_PROMPT_HEADERS = (
    "Изучи таблицу на изображении.\n"
    "Верни ТОЛЬКО JSON-массив строк — названия всех столбцов таблицы строго слева направо.\n"
    "Каждый столбец — отдельный элемент массива, не объединяй соседние столбцы.\n"
    "Пример: [\"№\", \"Команда\", \"И\", \"В\", \"ВО\"]\n"
    "Без объяснений, без markdown."
)

_PROMPT_DATA = (
    "Изучи таблицу на изображении.\n"
    "Столбцы таблицы пронумерованы строго слева направо:\n"
    "{numbered_headers}\n\n"
    "Верни ТОЛЬКО валидный JSON-массив объектов.\n"
    "Каждый объект — одна строка данных.\n"
    "ВАЖНО: в каждой строке ровно {count} значений — по одному на каждый пронумерованный столбец.\n"
    "Значение столбца №N — это N-е значение слева в этой строке таблицы.\n"
    "Числа возвращай числами, строки — строками.\n"
    "Без объяснений, без markdown."
)


def generate_schema_hint(filepath: str) -> dict:
    from src.config import settings

    ext = filepath.lower().rsplit(".", 1)[-1]
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"

    print(f"\n[image_parser] ── шаг 1: чтение и предобработка ───────────")
    print(f"[image_parser] filepath : {filepath}")
    print(f"[image_parser] model    : {_MODEL}")

    processed = _preprocess(filepath)
    print(f"[image_parser] preprocessed : {processed}")

    with open(processed, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )

    # Запрос 1 — только заголовки
    print(f"\n[image_parser] ── шаг 2: запрос заголовков ─────────────────")
    r_headers = client.chat.completions.create(
        model=_MODEL,
        temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": _PROMPT_HEADERS},
        ]}],
    )
    raw_headers = r_headers.choices[0].message.content.strip()
    if raw_headers.startswith("```"):
        raw_headers = raw_headers.split("```")[1].lstrip("json").strip()
    headers = json.loads(raw_headers)
    print(f"[image_parser] заголовки ({len(headers)}): {headers}")

    # Запрос 2 — данные с явными заголовками
    print(f"\n[image_parser] ── шаг 3: запрос данных ────────────────────")
    numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headers))
    prompt_data = _PROMPT_DATA.format(
        numbered_headers=numbered,
        count=len(headers),
    )
    r_data = client.chat.completions.create(
        model=_MODEL,
        temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": prompt_data},
        ]}],
    )
    raw = r_data.choices[0].message.content.strip()

    print(f"\n[image_parser] ── шаг 4: ответ LLM (данные) ───────────────")
    print(f"[image_parser] raw ({len(raw)} chars):\n{raw[:1000]}")
    if len(raw) > 1000:
        print(f"[image_parser] ... (обрезано, полная длина {len(raw)})")

    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
        print(f"[image_parser] (markdown-обёртка снята)")

    # JSON → DataFrame → CSV bytes
    print(f"\n[image_parser] ── шаг 5: JSON → DataFrame → CSV ─────────")
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[image_parser] ОШИБКА JSON: {e}")
        print(f"[image_parser] полный raw:\n{raw}")
        raise
    print(f"[image_parser] строк в JSON : {len(rows)}")
    if rows:
        print(f"[image_parser] колонки      : {list(rows[0].keys())}")
        print(f"[image_parser] первая строка: {rows[0]}")

    df = pd.DataFrame(rows)
    csv_bytes = df.to_csv(sep=";", index=False).encode("utf-8")
    lines = csv_bytes.decode("utf-8").splitlines()

    print(f"\n[image_parser] ── шаг 6: CSV (всего строк: {len(lines)}) ────────")
    for line in lines:
        print(f"[image_parser]   {line}")

    # CSV → schema hint
    print(f"\n[image_parser] ── шаг 7: csv_parser → schema ───────────────")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as tmp:
        tmp.write(csv_bytes)
        tmp_path = tmp.name

    try:
        schema = _generate_schema_hint(tmp_path)
    finally:
        os.unlink(tmp_path)

    print(f"[image_parser] col_count : {schema['col_count']}")
    print(f"[image_parser] row_count : {schema['row_count']}")
    for col in schema["columns"]:
        print(f"[image_parser]   {col['name']!r:30s} dtype={col['dtype']:8s} sample={col['sample']}")
    print(f"[image_parser] ────────────────────────────────────────────\n")

    # Удаляем временный preprocessed файл
    if processed != filepath:
        try:
            os.unlink(processed)
        except OSError:
            pass

    schema["_csv_bytes_b64"] = base64.b64encode(csv_bytes).decode()
    schema["_original_type"] = ext
    return schema


def _preprocess(filepath: str) -> str:
    """Увеличивает контрастность и резкость изображения перед отправкой в модель."""
    img = Image.open(filepath).convert("RGB")

    w, h = img.size
    if w < 2000:
        scale = 2000 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        print(f"[image_parser] resize: {w}x{h} → {img.size[0]}x{img.size[1]}")

    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = ImageEnhance.Sharpness(img).enhance(2.0)

    out_path = filepath.rsplit(".", 1)[0] + "_processed.png"
    img.save(out_path, "PNG")
    return out_path
