import re
import pandas as pd

_NUM_DASH_NUM = re.compile(r'^\d+[-]\d+$')


def _generate_schema_hint(filepath: str, sample_size: int = 2) -> dict:
    separator = _detect_separator(filepath)

    df = pd.read_csv(filepath, sep=separator, encoding="utf-8-sig")

    columns = []
    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        non_null = series.dropna()

        dtype = _map_dtype(series)

        sample = []
        for val in non_null.head(sample_size):
            if hasattr(val, "item"):
                sample.append(val.item())
            else:
                sample.append(val)

        entry = {
            "name":     col,
            "dtype":    dtype,
            "sample":   sample,
            "nullable": null_count > 0,
        }
        if dtype == "str" and sample and all(
            _NUM_DASH_NUM.match(str(v).strip()) for v in sample
        ):
            entry["format"] = "N-N"
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


