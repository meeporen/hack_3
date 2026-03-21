from langchain_core.prompts import ChatPromptTemplate

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

## Шаблон для CSV (если file_type = "csv")

export default function(base64file: string): TargetData[] {{
  const text = atob(base64file).replace(/^\\uFEFF/, '')
  const lines = text.split('\\n').filter((l: string) => l.trim())
  const headers = lines[0].split('{separator}')

  const parseLine = (line: string): string[] => {{
    const result: string[] = []
    let cur = '', inQ = false
    for (let i = 0; i < line.length; i++) {{
      const c = line[i]
      if (c === '"') {{
        if (inQ && line[i+1] === '"') {{ cur += '"'; i++ }}
        else inQ = !inQ
      }} else if (c === '{separator}' && !inQ) {{
        result.push(cur.trim()); cur = ''
      }} else cur += c
    }}
    result.push(cur.trim())
    return result
  }}

  const get = (cells: string[], name: string): string | null => {{
    const idx = headers.indexOf(name)
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
      // маппинг полей
    }}
  }})
}}

## Подсказки для неочевидных полей
- creator           ← "Сделка - Создал"
- deal              ← "Сделка"
- dealId            ← "Сделка - Идентификатор"
- dealIdentifier    ← "Сделка - Идентификатор"
- identifierRevenue ← "Идентификатор (Выручка)"
- revenue           ← "Выручка"
- lastUpdateDate    ← "Дата последнего обновления"
- stageTransitionTime ← "Время перехода на текущую стадию"
- dealStageFinal    ← get(cells, "Стадия (Сделка)") === "Закрыта"

## КРИТИЧНО — опечатка в переменной
- НИКОГДА не пиши ccells — только cells
- ВЕРНО:   siteLead: toBool(get(cells, 'Сделка - Лид с сайта'))
- НЕВЕРНО: siteLead: toBool(get(ccells, 'Сделка - Лид с сайта'))

## Правила маппинга
- Ключи результата берёшь СТРОГО из target_json — РОВНО столько полей, сколько в target_json, НЕ БОЛЬШЕ
- НИКОГДА не добавляй поля которых нет в target_json, даже если они есть в файле
- Названия колонок берёшь СТРОГО из поля name в схеме колонок
- dtype int64/float64 → toNum()
- sample ['Да','Нет'] → toBool()
- nullable: true → string | null
- НИКОГДА не используй cells[0], cells[1] и т.д.
- НИКОГДА не вызывай функции которые сам не определил
- НИКОГДА не пиши опечатки в переменных
- Верни ТОЛЬКО TypeScript код. Без markdown. Без пояснений.
"""),
    ("user", "Сгенерируй функцию"),
])