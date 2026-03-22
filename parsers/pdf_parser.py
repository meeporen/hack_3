import base64
import json
import os
import sys
import tempfile

import pandas as pd
import pdfplumber
from PIL import Image, ImageEnhance
from openai import OpenAI

_MODEL_VISION = "qwen/qwen2.5-vl-72b-instruct"

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


def generate_schema_hint(filepath: str, api_key: str | None = None) -> dict:
    if api_key is None:
        from src.config import settings
        api_key = settings.OPENROUTER_API_KEY

    print(f"\n[pdf_parser] ── старт ──────────────────────────────────────")
    print(f"[pdf_parser] filepath : {filepath}")

    print(f"\n[pdf_parser] ── шаг 1: pdfplumber ─────────────────────────")
    schema = _try_pdfplumber(filepath)
    if schema is not None:
        print(f"[pdf_parser] ✓ структурированная таблица найдена, vision не нужен")
        return schema

    print(f"[pdf_parser] ✗ таблица не найдена — переходим в vision pipeline")
    return _vision_pipeline(filepath, api_key)


def _try_pdfplumber(filepath: str) -> dict | None:
    all_tables = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if table:
                    all_tables.append(table)

    if not all_tables:
        print(f"[pdf_parser] pdfplumber: таблиц не найдено")
        return None

    print(f"[pdf_parser] pdfplumber: найдено таблиц: {len(all_tables)}")

    table = max(all_tables, key=lambda t: len(t) * len(t[0]))
    print(f"[pdf_parser] pdfplumber: выбрана таблица {len(table)}x{len(table[0])}")

    headers = [' '.join(str(h).replace('\n', ' ').split()) if h else f"col_{i}" for i, h in enumerate(table[0])]
    rows_sample = table[1:6]
    rows_sample = [[str(cell) if cell else "" for cell in row] for row in rows_sample]

    max_cols = max(len(headers), max((len(r) for r in rows_sample), default=0))
    headers += [f"col_{i}" for i in range(len(headers), max_cols)]
    rows_sample = [r + [""] * (max_cols - len(r)) for r in rows_sample]

    all_rows = [[str(cell) if cell else "" for cell in row] for row in table[1:]]
    all_rows = [r + [""] * (max_cols - len(r)) for r in all_rows]

    df_full = pd.DataFrame(all_rows, columns=headers)
    df_full = df_full.replace("", pd.NA)
    df_full = df_full.apply(lambda col: pd.to_numeric(col, errors="coerce").fillna(col))

    df_sample = pd.DataFrame(rows_sample, columns=headers)
    df_sample = df_sample.replace("", pd.NA)
    df_sample = df_sample.apply(lambda col: pd.to_numeric(col, errors="coerce").fillna(col))

    columns = []
    for col in df_sample.columns:
        series = df_sample[col]
        non_null = series.dropna()
        sample = non_null.unique()[0] if len(non_null) > 0 else None
        if hasattr(sample, "item"):
            sample = sample.item()
        columns.append({
            "name": str(col),
            "dtype": _map_dtype(df_full[col]),
            "sample": str(sample) if sample is not None else None,
            "has_nulls": bool(df_full[col].isna().any()),
        })

    csv_bytes = df_full.to_csv(sep=";", index=False).encode("utf-8")

    print(f"\n[pdf_parser] ── данные таблицы ─────────────────────────────")
    print(df_full.to_string(index=False))

    return {
        "file_type": "csv",
        "separator": ";",
        "row_count": len(df_full),
        "col_count": len(df_full.columns),
        "columns": columns,
        "_csv_bytes_b64": base64.b64encode(csv_bytes).decode(),
        "_original_type": "pdf",
        "_strategy": "pdfplumber",
    }


def _vision_pipeline(filepath: str, api_key: str) -> dict:
    try:
        from parsers.csv_parser import _generate_schema_hint
    except ModuleNotFoundError:
        from csv_parser import _generate_schema_hint

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    print(f"\n[pdf_parser] ── шаг 2: рендер страниц PDF ──────────────────")
    page_images = _rasterize_pdf(filepath)
    print(f"[pdf_parser] страниц отрендерено: {len(page_images)}")

    all_rows: list[dict] = []
    headers: list[str] | None = None
    total_in, total_out = 0, 0

    for i, img_path in enumerate(page_images):
        page_num = i + 1
        print(f"\n[pdf_parser] ── страница {page_num}/{len(page_images)} ────────────────────")

        b64, mime = _img_to_b64(img_path)

        if headers is None:
            print(f"[pdf_parser] запрос заголовков...")
            r_h = client.chat.completions.create(
                model=_MODEL_VISION,
                temperature=0,
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": _PROMPT_HEADERS},
                ]}],
            )
            u = r_h.usage
            total_in += u.prompt_tokens; total_out += u.completion_tokens
            print(f"[pdf_parser] токены (заголовки): in={u.prompt_tokens} out={u.completion_tokens}")
            raw_h = _strip_markdown(r_h.choices[0].message.content.strip())
            try:
                headers = json.loads(raw_h)
                print(f"[pdf_parser] заголовки ({len(headers)}): {headers}")
            except json.JSONDecodeError:
                print(f"[pdf_parser] WARN: не удалось распарсить заголовки: {raw_h!r}")
                continue

        numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headers))
        prompt_data = _PROMPT_DATA.format(numbered_headers=numbered, count=len(headers))

        r_d = client.chat.completions.create(
            model=_MODEL_VISION,
            temperature=0,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": prompt_data},
            ]}],
        )
        u = r_d.usage
        total_in += u.prompt_tokens; total_out += u.completion_tokens
        print(f"[pdf_parser] токены (данные): in={u.prompt_tokens} out={u.completion_tokens}")
        raw_d = _strip_markdown(r_d.choices[0].message.content.strip())
        print(f"[pdf_parser] raw данные ({len(raw_d)} chars): {raw_d[:300]}")

        page_rows = _parse_json_rows(raw_d)
        print(f"[pdf_parser] строк на странице: {len(page_rows)}")
        all_rows.extend(page_rows)

        try:
            os.unlink(img_path)
        except OSError:
            pass

    print(f"\n[pdf_parser] ── токены итого ────────────────────────────────")
    print(f"[pdf_parser] input:  {total_in}")
    print(f"[pdf_parser] output: {total_out}")
    print(f"[pdf_parser] total:  {total_in + total_out}")
    print(f"\n[pdf_parser] ── шаг 3: итого строк: {len(all_rows)} ──────────")

    df = pd.DataFrame(all_rows)
    csv_bytes = df.to_csv(sep=";", index=False).encode("utf-8")

    lines = csv_bytes.decode("utf-8").splitlines()
    print(f"\n[pdf_parser] ── CSV ({len(lines)} строк) ─────────────────────")
    for line in lines[:20]:
        print(f"[pdf_parser]   {line}")
    if len(lines) > 20:
        print(f"[pdf_parser]   ... ({len(lines) - 20} more lines)")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as tmp:
        tmp.write(csv_bytes)
        tmp_path = tmp.name

    try:
        schema = _generate_schema_hint(tmp_path)
    finally:
        os.unlink(tmp_path)

    schema["_csv_bytes_b64"] = base64.b64encode(csv_bytes).decode()
    schema["_original_type"] = "pdf"
    schema["_strategy"] = "vision"
    schema["_vision_prompt_tokens"] = total_in
    schema["_vision_completion_tokens"] = total_out
    return schema


def _rasterize_pdf(filepath: str, dpi: int = 120) -> list[str]:
    """Рендерит каждую страницу PDF в PNG через PyMuPDF."""
    import fitz

    doc = fitz.open(filepath)
    paths = []

    for i, page in enumerate(doc):
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

        out_path = tempfile.mktemp(suffix=f"_page{i+1}.png")
        pix.save(out_path)

        img = Image.open(out_path).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(1.4)
        img = ImageEnhance.Sharpness(img).enhance(1.8)
        img.save(out_path, "PNG")

        print(f"[pdf_parser]   page {i+1}: {pix.width}x{pix.height} -> {out_path}")
        paths.append(out_path)

    doc.close()
    return paths


def _img_to_b64(path: str) -> tuple[str, str]:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode(), "image/png"


def _strip_markdown(text: str) -> str:
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _parse_json_rows(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError as e:
        print(f"[pdf_parser]   WARN JSON: {e} | raw: {raw[:300]!r}")
    return []


def _map_dtype(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):            return "bool"
    if pd.api.types.is_integer_dtype(series):         return "int64"
    if pd.api.types.is_float_dtype(series):           return "float64"
    if pd.api.types.is_datetime64_any_dtype(series):  return "datetime"
    if pd.api.types.is_timedelta64_dtype(series):     return "timedelta"
    if isinstance(series.dtype, pd.CategoricalDtype): return "category"
    return "str"


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else input("Путь к PDF: ")
    try:
        result = generate_schema_hint(path)
        result.pop("_csv_bytes_b64", None)
        print(json.dumps(result, ensure_ascii=False, indent=4))
    except Exception:
        import traceback
        traceback.print_exc()
