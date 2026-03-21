import pandas as pd
import json


def _generate_schema_hint(filepath: str, sample_size: int = 2) -> dict:
    separator = _detect_separator(filepath)

    # utf-8-sig убирает BOM
    df = pd.read_csv(filepath, sep=separator, encoding="utf-8-sig")

    columns = []
    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        non_null = series.dropna()

        dtype = _map_dtype(series)

        # список из 2 значений вместо одного
        sample = []
        for val in non_null.head(sample_size):
            if hasattr(val, "item"):
                sample.append(val.item())
            else:
                sample.append(val)

        entry = {
            "name":     col,
            "dtype":    dtype,
            "sample":   sample,           # ← список
            "nullable": null_count > 0,   # ← было has_nulls, теперь nullable
        }
        columns.append(entry)

    return {
        "file_type": "csv",
        "separator": separator,
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns":   columns,
    }


def _detect_separator(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8-sig") as f:
        first_line = f.readline()

    candidates = [";", ",", "\t", "|"]
    counts = {sep: first_line.count(sep) for sep in candidates}
    return max(counts, key=counts.get)


def _map_dtype(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):            return "bool"
    if pd.api.types.is_integer_dtype(series):         return "int64"
    if pd.api.types.is_float_dtype(series):           return "float64"
    if pd.api.types.is_datetime64_any_dtype(series):  return "datetime"
    if pd.api.types.is_timedelta64_dtype(series):     return "timedelta"
    if isinstance(series.dtype, pd.CategoricalDtype): return "category"
    return "str"


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else input("Путь к файлу: ")
    try:
        print(json.dumps(_generate_schema_hint(path), ensure_ascii=False, indent=4))
    except Exception as e:
        print(f"Ошибка: {e}")