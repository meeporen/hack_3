from io import BytesIO, StringIO

import pandas as pd

_ENCODINGS = ["utf-8-sig", "utf-8", "cp1251", "latin-1"]


def _decode(raw_bytes: bytes) -> str:
    for enc in _ENCODINGS:
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("latin-1")


def convert_to_csv(raw_bytes: bytes, file_type: str) -> tuple[bytes, str]:
    ft = file_type.lower()

    if ft == "csv":
        return raw_bytes, "csv"

    if ft in ("pdf", "docx"):
        return raw_bytes, ft

    if ft in ("xlsx", "xls"):
        engine = "openpyxl" if ft == "xlsx" else "xlrd"
        df = pd.read_excel(BytesIO(raw_bytes), engine=engine)
    elif ft == "tsv":
        df = pd.read_csv(StringIO(_decode(raw_bytes)), sep="\t")
    elif ft == "json":
        df = pd.read_json(StringIO(_decode(raw_bytes)))
    elif ft == "jsonl":
        df = pd.read_json(StringIO(_decode(raw_bytes)), lines=True)
    else:
        return raw_bytes, ft

    csv_bytes = df.to_csv(sep=";", index=False).encode("utf-8")
    return csv_bytes, "csv"
