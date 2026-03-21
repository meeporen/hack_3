import json
import pandas as pd
import pdfplumber


def _map_dtype(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):           return "bool"
    if pd.api.types.is_integer_dtype(series):        return "int64"
    if pd.api.types.is_float_dtype(series):          return "float64"
    if pd.api.types.is_datetime64_any_dtype(series): return "datetime"
    if pd.api.types.is_timedelta64_dtype(series):    return "timedelta"
    if isinstance(series.dtype, pd.CategoricalDtype):return "category"
    return "str"

def _build_columns(df: pd.DataFrame) -> list:
    # сбрасываем дублированные колонки
    df.columns = [f"col_{i}" if df.columns.tolist().count(c) > 1 else c
                  for i, c in enumerate(df.columns)]
    columns = []
    for i, col in enumerate(df.columns):
        series = df.iloc[:, i]  # берём по индексу а не по имени
        null_count = int(series.isna().sum())
        non_null = series.dropna()
        sample = non_null.unique()[0] if len(non_null) > 0 else None
        if hasattr(sample, "item"):
            sample = sample.item()
        columns.append({
            "name": str(col),
            "dtype": _map_dtype(series),
            "sample": sample,
            "has_nulls": null_count > 0,
        })
    return columns


def generate_schema_hint(filepath: str) -> dict:
    tables_info = []
    text_sample = ""

    with pdfplumber.open(filepath) as pdf:
        page_count = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages):
            if not text_sample:
                text = page.extract_text()
                if text:
                    text_sample = text[:200]

            for table in page.extract_tables({
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
            }):
                if not table or not table[0]:
                    continue

                # чистим заголовки — убираем None
                headers = [str(h) if h is not None else f"col_{i}"
                           for i, h in enumerate(table[0])]

                df = pd.DataFrame(table[1:], columns=headers)
                tables_info.append({
                    "page": page_num + 1,
                    "row_count": len(df),
                    "col_count": len(df.columns),
                    "columns": _build_columns(df),
                })

    return {
        "file_type": "pdf",
        "page_count": page_count,
        "text_sample": text_sample,
        "tables": tables_info,
    }

if __name__ == "__main__":
    import sys
    import traceback
    path = sys.argv[1] if len(sys.argv) > 1 else input("Путь к файлу: ")
    try:
        print(json.dumps(generate_schema_hint(path), ensure_ascii=False, indent=4))
    except Exception as e:
        traceback.print_exc()