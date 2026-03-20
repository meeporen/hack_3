import pandas as pd


def _map_dtype(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):           return "bool"
    if pd.api.types.is_integer_dtype(series):        return "int64"
    if pd.api.types.is_float_dtype(series):          return "float64"
    if pd.api.types.is_datetime64_any_dtype(series): return "datetime"
    if pd.api.types.is_timedelta64_dtype(series):    return "timedelta"
    if isinstance(series.dtype, pd.CategoricalDtype):return "category"
    return "str"


def _build_columns(df: pd.DataFrame) -> list:
    columns = []
    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        non_null = series.dropna()

        sample = non_null.unique()[0] if len(non_null) > 0 else None

        if hasattr(sample, "item"):
            sample = sample.item()

        columns.append({
            "name": col,
            "dtype": _map_dtype(series),
            "sample": sample,
            "has_nulls": null_count > 0,
        })
    return columns


def generate_schema_hint(filepath: str) -> dict:
    df = pd.read_csv(filepath, sep="\t", encoding="utf-8")
    return {
        "file_type": "tsv",
        "separator": "\t",
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": _build_columns(df),
    }


if __name__ == "__main__":
    import sys, json
    path = sys.argv[1] if len(sys.argv) > 1 else input("Путь к файлу: ")
    try:
        print(json.dumps(generate_schema_hint(path), ensure_ascii=False, indent=4))
    except Exception as e:
        print(f"Ошибка: {e}")