import pandas as pd


def _map_dtype(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):            return "bool"
    if pd.api.types.is_integer_dtype(series):         return "int64"
    if pd.api.types.is_float_dtype(series):           return "float64"
    if pd.api.types.is_datetime64_any_dtype(series):  return "datetime"
    if pd.api.types.is_timedelta64_dtype(series):     return "timedelta"
    if isinstance(series.dtype, pd.CategoricalDtype): return "category"
    return "str"


def _build_columns(df: pd.DataFrame) -> list:
    columns = []
    for col in df.columns:
        series   = df[col]
        non_null = series.dropna()

        # список из 2 значений
        sample = []
        for val in non_null.head(2):
            sample.append(val.item() if hasattr(val, "item") else val)

        columns.append({
            "name":     col,
            "dtype":    _map_dtype(series),
            "sample":   sample,                        # ← список
            "nullable": int(series.isna().sum()) > 0,  # ← nullable не has_nulls
        })
    return columns


def _generate_schema_hint(filepath: str) -> dict:
    df = pd.read_excel(filepath, engine="openpyxl", nrows=5)  # ← nrows=5
    return {
        "file_type": "xlsx",
        "separator": "xlsx",   # ← не None, а "xlsx" чтобы промпт не писал split('None')
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns":   _build_columns(df),
    }


if __name__ == "__main__":
    import sys, json
    path = sys.argv[1] if len(sys.argv) > 1 else input("Путь к файлу: ")
    try:
        print(json.dumps(_generate_schema_hint(path), ensure_ascii=False, indent=4))
    except Exception as e:
        print(f"Ошибка: {e}")