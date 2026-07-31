"""Поиск POI рядом (банкоматы, кафе и т.п.) — за слоем провайдера.

Приложение получает всегда одинаковый формат: {name, lat, lng, category}.
Сейчас источник — Overpass API (OpenStreetMap, бесплатно, без ключа). Позже
адаптер можно заменить на 2GIS/Google, не трогая приложение (см. maps-data-stack).
"""

import aiohttp

from .config import settings

# Overpass отбивает запросы без внятного User-Agent — Apache отвечает 406, и на
# карте молча пропадают кафе и рестораны. aiohttp по умолчанию своего заголовка
# не ставит вовсе, поэтому задаём явно. В geocoding_provider та же история и
# такое же лечение — грабли общие для сервисов OpenStreetMap.
_HEADERS = {"User-Agent": "uzbekistan-ai-guide/1.0"}

# Категория -> OSM-фильтр для Overpass.
CATEGORY_OSM = {
    "atm": '["amenity"="atm"]',
    "bank": '["amenity"="bank"]',
    "cafe": '["amenity"="cafe"]',
    "restaurant": '["amenity"="restaurant"]',
    "pharmacy": '["amenity"="pharmacy"]',
    "hotel": '["tourism"="hotel"]',
}


class PoiError(Exception):
    pass


async def _overpass_find(category: str, lat: float, lng: float, radius: int, limit: int) -> list[dict]:
    osm = CATEGORY_OSM.get(category)
    if not osm:
        raise PoiError(f"Неизвестная категория: {category}")

    # Ищем и точки (node), и здания (way -> центр).
    query = (
        f"[out:json][timeout:25];"
        f"(node{osm}(around:{radius},{lat},{lng});"
        f"way{osm}(around:{radius},{lat},{lng}););"
        f"out center {limit};"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.overpass_url,
                data={"data": query},
                headers=_HEADERS,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    raise PoiError(f"Overpass вернул статус {resp.status}")
                data = await resp.json()
    except aiohttp.ClientError as e:
        raise PoiError(f"Не удалось связаться с Overpass: {e}") from e

    items: list[dict] = []
    for el in data.get("elements", []):
        if el.get("type") == "node":
            plat, plng = el.get("lat"), el.get("lon")
        else:
            center = el.get("center") or {}
            plat, plng = center.get("lat"), center.get("lon")
        if plat is None or plng is None:
            continue
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en") or tags.get("name:ru") or ""
        items.append({"name": name, "lat": plat, "lng": plng, "category": category, "source": "osm"})

    return items[:limit]


async def find_nearby(
    category: str, lat: float, lng: float, radius: int = 1500, limit: int = 40
) -> list[dict]:
    if settings.poi_provider == "overpass":
        return await _overpass_find(category, lat, lng, radius, limit)
    raise PoiError(f"POI-провайдер не настроен: {settings.poi_provider}")
