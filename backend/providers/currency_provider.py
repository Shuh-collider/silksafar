"""Курс валют — за слоем провайдера. Сейчас ЦБ Узбекистана (официальный,
бесплатно, без ключа). Позже можно добавить фолбэк (Frankfurter/OXR)."""

import aiohttp

# Валюты аудитории приложения: доллар как общий ориентир + евро/рубль/юань
# (туристы из Европы, России, Китая — см. product-vision).
TRACKED = ["USD", "EUR", "RUB", "CNY"]


class CurrencyError(Exception):
    pass


async def get_rates() -> list[dict]:
    url = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    raise CurrencyError(f"ЦБ РУз вернул {resp.status}")
                data = await resp.json()
    except aiohttp.ClientError as e:
        raise CurrencyError(str(e))

    by_code = {row["Ccy"]: row for row in data if row.get("Ccy") in TRACKED}
    result = []
    for code in TRACKED:
        row = by_code.get(code)
        if row:
            result.append(
                {
                    "code": code,
                    "rate": float(row["Rate"]),
                    "diff": float(row["Diff"]),
                    "date": row["Date"],
                }
            )
    return result
