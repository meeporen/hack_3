from langchain_core.prompts import ChatPromptTemplate

# ── Boilerplate templates (plain Python strings, not LangChain format) ──────

_BOILERPLATE_CSV = """\
export default function(base64file: string): TargetData[] {{
  const text = atob(base64file).replace(/^\\uFEFF/, '')
  const lines = text.split('\\n').filter((l: string) => l.trim())
  const headers = lines[0].split('{sep}').map((h: string) => h.trim())

  const parseLine = (line: string): string[] => {{
    const result: string[] = []
    let cur = '', inQ = false
    for (let i = 0; i < line.length; i++) {{
      const c = line[i]
      if (c === '"') {{
        if (inQ && line[i+1] === '"') {{ cur += '"'; i++ }}
        else inQ = !inQ
      }} else if (c === '{sep}' && !inQ) {{
        result.push(cur.trim()); cur = ''
      }} else cur += c
    }}
    result.push(cur.trim())
    return result
  }}

  const _norm = (s: string) => s.replace(/\s+/g, '').toLowerCase()
  const _normHeaders = headers.map(_norm)
  const get = (cells: string[], name: string): string | null => {{
    const idx = _normHeaders.indexOf(_norm(name))
    return idx === -1 ? null : (cells[idx]?.trim() || null)
  }}
  const toNum = (v: string | null): number | null =>
    v === null ? null : (isNaN(Number(v)) ? null : Number(v))
  const toStr = (v: string | null): string | null =>
    v === null || v === '' ? null : v
  const toBool = (v: string | null): boolean =>
    v === 'Да' || v === 'да'

  return lines.slice(1).map((line: string) => {{
    const cells = parseLine(line)
    return {{
      // маппинг полей — используй get(cells, 'ИмяКолонки')
    }}
  }})
}}"""

_BOILERPLATE_XLSX = """\
export default function(base64file: string): TargetData[] {
  const wb = XLSX.read(base64file, { type: 'base64' })
  const ws = wb.Sheets[wb.SheetNames[0]]
  const rows: any[] = XLSX.utils.sheet_to_json(ws, { defval: null })

  const get = (row: any, name: string): any => row[name] ?? null
  const toNum = (v: any): number | null =>
    v === null ? null : (isNaN(Number(v)) ? null : Number(v))
  const toStr = (v: any): string | null =>
    v === null || v === '' ? null : String(v)
  const toBool = (v: any): boolean =>
    v === 'Да' || v === 'да' || v === true

  return rows.map((row: any) => ({
    // маппинг полей — используй get(row, 'ИмяКолонки')
  }))
}"""

_BOILERPLATE_JSON = """\
export default function(base64file: string): TargetData[] {
  const rows: any[] = JSON.parse(atob(base64file))

  const get = (row: any, name: string): any => row[name] ?? null
  const toNum = (v: any): number | null =>
    v === null ? null : (isNaN(Number(v)) ? null : Number(v))
  const toStr = (v: any): string | null =>
    v === null || v === '' ? null : String(v)
  const toBool = (v: any): boolean =>
    v === 'Да' || v === 'да' || v === true

  return rows.map((row: any) => ({
    // маппинг полей — используй get(row, 'ИмяКолонки')
  }))
}"""

_BOILERPLATE_JSONL = """\
export default function(base64file: string): TargetData[] {
  const rows: any[] = atob(base64file).trim().split('\\n')
    .filter((l: string) => l.trim())
    .map((l: string) => JSON.parse(l))

  const get = (row: any, name: string): any => row[name] ?? null
  const toNum = (v: any): number | null =>
    v === null ? null : (isNaN(Number(v)) ? null : Number(v))
  const toStr = (v: any): string | null =>
    v === null || v === '' ? null : String(v)
  const toBool = (v: any): boolean =>
    v === 'Да' || v === 'да' || v === true

  return rows.map((row: any) => ({
    // маппинг полей — используй get(row, 'ИмяКолонки')
  }))
}"""


def get_boilerplate(file_type: str, separator: str = ";") -> str:
    if file_type in ("xlsx", "xls"):
        return _BOILERPLATE_XLSX
    elif file_type == "json":
        return _BOILERPLATE_JSON
    elif file_type == "jsonl":
        return _BOILERPLATE_JSONL
    else:
        return _BOILERPLATE_CSV.format(sep=separator)


# ── LangChain prompt ─────────────────────────────────────────────────────────

CODE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Ты генерируешь TypeScript функцию трансформации файла в JSON.

Сигнатура строго такая — не меняй:
export default function(base64file: string): TargetData[] {{ ... }}

## Входной файл
- Тип: {file_type}
- Разделитель: "{separator}"
- Строк: {row_count}, Колонок: {col_count}

## Схема колонок (name — точное название, dtype — тип, sample — примеры)
{columns}

## Целевой JSON (пример одного объекта — ключи которые нужно вернуть)
{target_json}

## Ошибки предыдущей попытки — ОБЯЗАТЕЛЬНО исправь их
{errors}

## ОБЯЗАТЕЛЬНО используй ЭТОТ скелет функции — не меняй структуру, заполни только маппинг:

{boilerplate}

## Подсказки для неочевидных полей
- creator           ← "Сделка - Создал"
- deal              ← "Сделка"
- dealId            ← "Сделка - Идентификатор"
- dealIdentifier    ← "Сделка - Идентификатор"
- identifierRevenue ← "Идентификатор (Выручка)"
- revenue           ← "Выручка"
- lastUpdateDate    ← "Дата последнего обновления"
- stageTransitionTime ← "Время перехода на текущую стадию"
- dealStageFinal    ← значение колонки "Стадия (Сделка)" === "Закрыта"

## Колонки с "format": "N-N" (значение вида "254-173" — два числа через дефис)
- Разбивай ТОЛЬКО через `.split('-')`, никогда не через `.split(' ')`
- Для CSV:   const _raw = get(cells, 'ИмяКолонки'); field1: toNum(_raw ? _raw.split('-')[0] : null)
- Для остальных: const _raw = get(row, 'ИмяКолонки'); field1: toNum(_raw ? String(_raw).split('-')[0] : null)

## Правила маппинга
- Ключи результата берёшь СТРОГО из target_json — РОВНО столько полей, сколько в target_json, НЕ БОЛЬШЕ
- НИКОГДА не добавляй поля которых нет в target_json, даже если они есть в файле
- Названия колонок берёшь СТРОГО из поля name в схеме колонок
- dtype int64/float64 → toNum()
- sample ['Да','Нет'] → toBool()
- nullable: true → string | null
- НИКОГДА не используй cells[0], cells[1], row[0], row[1] и т.д. — только через get()
- НИКОГДА не вызывай функции которые сам не определил
- НИКОГДА не пиши опечатки в переменных
- Верни ТОЛЬКО TypeScript код. Без markdown. Без пояснений.
"""),
    ("user", "Сгенерируй функцию"),
])
