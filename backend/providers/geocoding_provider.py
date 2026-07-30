"""Геокодинг — поиск места по названию → координаты. За слоем провайдера.

Сейчас Nominatim (OpenStreetMap, бесплатно, без ключа). Ограничиваем поиск
Узбекистаном. Позже адаптер можно заменить на 2GIS/self-hosted, не трогая
приложение (см. maps-data-stack). Использует и карта (строка поиска), и
ИИ-гид (инструмент find_place)."""

import aiohttp

from .config import settings

# Nominatim просит осмысленный User-Agent (стоковые заголовки http-библиотек
# он блокирует) — иначе может отдавать 403.
_HEADERS = {"User-Agent": "uzbekistan-ai-guide/1.0"}


class GeocodeError(Exception):
    pass


async def search(q: str, limit: int = 6) -> list[dict]:
    params = {
        "q": q,
        "format": "json",
        "limit": str(limit),
        "accept-language": "ru",
        "countrycodes": "uz",  # только Узбекистан — это гид для туристов в UZ
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                settings.nominatim_url,
                params=params,
                headers=_HEADERS,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise GeocodeError(f"Nominatim вернул {resp.status}")
                data = await resp.json(content_type=None)
    except aiohttp.ClientError as e:
        raise GeocodeError(str(e))

    results = []
    for row in data:
        display = row.get("display_name", "")
        # Короткое имя — первая часть до запятой; полный адрес — как label.
        name = display.split(",")[0].strip() if display else row.get("name", "")
        try:
            lat = float(row["lat"])
            lng = float(row["lon"])
        except (KeyError, ValueError):
            continue
        results.append({"name": name, "label": display, "lat": lat, "lng": lng})
    return results


async def _reverse_raw(lat: float, lng: float, zoom: int, lang: str = "ru") -> dict | None:
    """Сырой ответ Nominatim /reverse. Zoom задаёт уровень детализации:
    16 — до улицы, 10 — до города. Lang — язык названий (accept-language)."""
    reverse_url = settings.nominatim_url.rsplit("/", 1)[0] + "/reverse"
    params = {
        "lat": str(lat),
        "lon": str(lng),
        "format": "json",
        "accept-language": lang,
        "zoom": str(zoom),
        "addressdetails": "1",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                reverse_url, params=params, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
    except aiohttp.ClientError:
        return None


# Кириллица → латиница по русской схеме романизации. Нужна как запасной
# вариант: у части объектов OSM по Узбекистану заполнено только `name` (по-русски),
# без `name:en`/`name:uz`/`name:zh` — тогда Nominatim на любом языке отдаёт
# кириллицу. Для китайского или европейского туриста это нечитаемо, а латиница
# хотя бы узнаваема: «Шахрисабз» → «Shakhrisabz» (совпадает с общепринятым
# английским написанием города).
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    # Узбекские буквы кириллицы — встречаются в местных названиях.
    "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
}


def _has_cyrillic(text: str) -> bool:
    return any("а" <= c.lower() <= "я" or c.lower() in "ёўқғҳ" for c in text)


def _translit(text: str) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        rep = _TRANSLIT.get(low)
        if rep is None:
            out.append(ch)
        elif ch.isupper() and rep:
            out.append(rep[0].upper() + rep[1:])
        else:
            out.append(rep)
    return "".join(out)


def _localize(name: str | None, lang: str) -> str | None:
    """Латинизируем название, если язык интерфейса не русский, а OSM отдал
    кириллицу (перевода у объекта просто нет)."""
    if not name or lang == "ru" or not _has_cyrillic(name):
        return name
    return _translit(name)


def _is_mahalla(v: str | None) -> bool:
    """В OSM по Узбекистану часть махаллей размечена как населённый пункт, и
    Nominatim кладёт их в поле city вместо города. Для подписи это мусор.

    Проверяем на всех языках, на которых просим названия: при `accept-language`
    отличном от русского то же место приезжает как «MFY», «mahallasi» и т.п.
    """
    if not v:
        return False
    low = v.lower()
    return any(m in low for m in ("махалл", "mahalla", "mahallasi", "mfy", "махаллинск"))


def _pick_city(addr: dict) -> str | None:
    name = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or addr.get("county")
        or addr.get("state")
    )
    return None if _is_mahalla(name) else name


async def reverse_city(lat: float, lng: float, lang: str = "ru") -> str | None:
    """Координаты → только название города/посёлка: подпись к погоде «где я».

    zoom=12 подобран по замерам: он отдаёт именно город («Хива», «Ташкент»), а
    не район области. Но в центре Ташкента на этом уровне вместо города
    приходит махалля — тогда переспрашиваем шире (zoom=8), там город есть.

    Lang — язык интерфейса приложения: подпись должна читаться китайским или
    европейским туристом, а не только русскоязычным. Если у OSM перевода нет,
    Nominatim сам вернёт местное название — это всё равно лучше кириллицы.
    """
    data = await _reverse_raw(lat, lng, zoom=12, lang=lang)
    name = _pick_city((data or {}).get("address") or {})
    if not name:
        data = await _reverse_raw(lat, lng, zoom=8, lang=lang)
        name = _pick_city((data or {}).get("address") or {})
    return _localize(name, lang)


async def reverse(lat: float, lng: float, lang: str = "ru") -> str | None:
    """Координаты → человекочитаемое место — «где сейчас юзер».

    Собираем адрес сами из структурных полей, а не берём `display_name`: тот
    отдаёт всё подряд, включая индекс, страну и сразу два района. У границы
    города это давало «Сергелийский район … Зангиатинский район» в одной строке —
    второй относится к Ташкентской области, и гид честно пересказывал эту путаницу.
    """
    data = await _reverse_raw(lat, lng, zoom=16, lang=lang)
    if not data:
        return None

    addr = data.get("address") or {}
    # По одному значению на уровень, от точного к общему. Район города берём
    # раньше районов области — иначе у границы вылезает соседний.
    specific = addr.get("road") or addr.get("pedestrian") or addr.get("neighbourhood")
    district = (
        addr.get("city_district")
        or addr.get("suburb")
        or addr.get("district")
        or addr.get("county")
    )
    city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("state")

    # В OSM по Ташкенту часть махаллей размечена как населённый пункт, и тогда
    # Nominatim кладёт её в поле city, а сам город не отдаёт вовсе. Махалля —
    # это самый точный уровень, а не город: переставляем, чтобы адрес читался
    # от точного к общему, а не «район, махалля».
    if _is_mahalla(city):
        specific = specific or city
        city = None

    parts: list[str] = []
    for p in (specific, district, city):
        if p and p not in parts:
            parts.append(p)
    result = ", ".join(parts) if parts else (data.get("display_name") or None)
    return _localize(result, lang)
