"""Инструменты ИИ-гида (function-calling): гид дёргает наши провайдеры за
живыми данными. Пока только «read»-инструменты (Tier-1) — без действий в
приложении. Действия (показать на карте, вызвать такси) — отдельным шагом."""

import math

from sqlalchemy.orm import Session

from .attractions import search_attractions
from .currency_provider import get_rates
from .geocoding_provider import reverse as geocode_reverse
from .geocoding_provider import search as geocode_search
from .models import InfoItem, SavedPlace, User
from .poi_provider import PoiError
from .poi_provider import find_nearby as poi_find_nearby
from .weather_provider import get_weather

# Координаты крупных городов — чтобы get_weather не геокодил каждый раз.
CITY_COORDS = {
    "ташкент": (41.2995, 69.2401), "tashkent": (41.2995, 69.2401),
    "самарканд": (39.627, 66.975), "samarkand": (39.627, 66.975),
    "бухара": (39.7747, 64.4286), "bukhara": (39.7747, 64.4286),
    "хива": (41.3775, 60.3639), "khiva": (41.3775, 60.3639),
    "фергана": (40.3864, 71.7864), "fergana": (40.3864, 71.7864),
    "наманган": (40.9983, 71.6726), "namangan": (40.9983, 71.6726),
    "нукус": (42.4531, 59.6103), "nukus": (42.4531, 59.6103),
    "термез": (37.2242, 67.2783), "termez": (37.2242, 67.2783),
}

# Объявления инструментов для Gemini (function_declarations).
GUIDE_TOOLS = [
    {
        "name": "find_place",
        "description": (
            "Найти место в Узбекистане по названию (достопримечательность, отель, "
            "адрес) и получить его координаты и полный адрес."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "название места, напр. 'Регистан Самарканд'"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_weather",
        "description": "Узнать текущую погоду и краткий прогноз в городе Узбекистана.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "название города, напр. 'Самарканд'"}
            },
            "required": ["city"],
        },
    },
    {
        "name": "get_currency",
        "description": (
            "Актуальный курс валют (доллар USD, евро EUR, рубль RUB, юань CNY) к "
            "узбекскому суму по ЦБ Узбекистана."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_emergency_numbers",
        "description": "Экстренные телефонные номера Узбекистана (полиция, скорая, пожарные и т.п.).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_my_location",
        "description": (
            "Узнать, где сейчас находится пользователь (город/место и координаты). "
            "Вызывай, когда нужно понять его местоположение для советов «рядом» или маршрутов."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "find_nearby",
        "description": "Найти места нужной категории рядом с пользователем (по его текущему местоположению).",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "категория мест",
                    "enum": ["atm", "bank", "cafe", "restaurant", "pharmacy", "hotel"],
                }
            },
            "required": ["category"],
        },
    },
    {
        "name": "get_saved_places",
        "description": "Личные сохранённые места пользователя («Мои места»).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "search_attractions",
        "description": (
            "Достопримечательности Узбекистана из нашей курируемой базы (название, "
            "описание, город, координаты, а если заполнены — часы работы и билет). "
            "Используй для «что посмотреть в <городе>» (передай city) и когда спрашивают "
            "про конкретный объект — «расскажи про Регистан» (передай query)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "город, напр. 'Самарканд' (необязательно)"},
                "query": {
                    "type": "string",
                    "description": "название объекта, напр. 'Регистан' (необязательно)",
                },
            },
        },
    },
    # --- ДЕЙСТВИЯ: гид просит приложение что-то сделать. Координаты передавай,
    # если уже получил их из другого инструмента (find_place/search_attractions/
    # get_saved_places/find_nearby) — иначе место найдётся по названию. ---
    {
        "name": "show_on_map",
        "description": "Показать место на карте в приложении (открывает карту с меткой на этом месте).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "название места для показа"},
                "lat": {"type": "number", "description": "широта, если известна"},
                "lng": {"type": "number", "description": "долгота, если известна"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "build_route",
        "description": "Построить маршрут от пользователя до места (открывает карту и рисует путь).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "название пункта назначения"},
                "lat": {"type": "number", "description": "широта, если известна"},
                "lng": {"type": "number", "description": "долгота, если известна"},
                "mode": {
                    "type": "string",
                    "description": "способ передвижения",
                    "enum": ["walking", "driving"],
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "call_taxi",
        "description": "Вызвать такси до места (открывает приложение такси с готовым адресом назначения).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "название пункта назначения"},
                "lat": {"type": "number", "description": "широта, если известна"},
                "lng": {"type": "number", "description": "долгота, если известна"},
            },
            "required": ["name"],
        },
    },
]


async def _coords_for_city(city: str):
    key = (city or "").strip().lower()
    if key in CITY_COORDS:
        return CITY_COORDS[key]
    hits = await geocode_search(city, limit=1)
    if hits:
        return (hits[0]["lat"], hits[0]["lng"])
    return None


def _find_saved_place(
    db: Session | None, user: User | None, name: str, exact_only: bool = False
) -> dict | None:
    """Ищем среди «Моих мест» пользователя: сначала точное совпадение, потом вхождение.
    Нужно для «вызови такси до Зарядки» — это личное название, геокодер его не знает.
    Мест у пользователя единицы, поэтому сравниваем в Python (без возни с collation)."""
    if db is None or user is None:
        return None
    key = (name or "").strip().lower()
    if not key:
        return None
    rows = db.query(SavedPlace).filter(SavedPlace.user_id == user.id).all()
    for r in rows:
        if (r.name or "").strip().lower() == key:
            return {"name": r.name, "lat": r.lat, "lng": r.lng}
    if exact_only:
        return None
    for r in rows:
        rn = (r.name or "").strip().lower()
        if rn and (rn in key or key in rn):
            return {"name": r.name, "lat": r.lat, "lng": r.lng}
    return None


def _approx_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Грубое расстояние в км — хватает, чтобы понять «то же это место или другое»."""
    dlat = (lat1 - lat2) * 111.0
    dlng = (lng1 - lng2) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlng)


async def _resolve_place(args: dict, db: Session | None = None, user: User | None = None) -> dict | None:
    """Координаты для действия. «Мои места» — источник истины, а не слова модели:
    мы просим её передавать lat/lng, но длинные дроби она переносит с ошибками,
    и точка уезжает на сотни метров («рядом, но не туда»).

    Поэтому: точное совпадение имени с сохранённым местом бьёт координаты модели.
    Неточное — только если модель указала куда-то рядом (иначе она, возможно,
    имела в виду совсем другое место со схожим названием)."""
    lat, lng = args.get("lat"), args.get("lng")
    name = args.get("name") or args.get("query") or "Место"
    has_coords = lat is not None and lng is not None

    exact = _find_saved_place(db, user, name, exact_only=True)
    if exact:
        return exact

    saved = _find_saved_place(db, user, name)
    if saved and (not has_coords or _approx_km(lat, lng, saved["lat"], saved["lng"]) <= 2.0):
        return saved

    if has_coords:
        return {"name": name, "lat": lat, "lng": lng}

    hits = await geocode_search(name, limit=1)
    if hits:
        return {"name": name, "lat": hits[0]["lat"], "lng": hits[0]["lng"]}
    return None


async def execute_tool(
    name: str,
    args: dict,
    db: Session,
    user: User,
    user_lat: float | None = None,
    user_lng: float | None = None,
    actions: list | None = None,
) -> dict:
    if name == "find_place":
        return {"places": await geocode_search(args.get("query", ""), limit=5)}
    if name == "get_weather":
        coords = await _coords_for_city(args.get("city", ""))
        if not coords:
            return {"error": "город не найден"}
        w = await get_weather(coords[0], coords[1])
        # Укорачиваем прогноз до 3 дней, чтобы не раздувать контекст.
        return {**w, "forecast": w.get("forecast", [])[:3]}
    if name == "get_currency":
        return {"rates": await get_rates()}
    if name == "get_emergency_numbers":
        rows = (
            db.query(InfoItem)
            .filter(InfoItem.key == "emergency", InfoItem.is_active == True)  # noqa: E712
            .all()
        )
        return {"numbers": [{"title": r.title, "phone": r.phone or r.body} for r in rows]}
    if name == "get_my_location":
        if user_lat is None or user_lng is None:
            return {"error": "местоположение недоступно (пользователь не поделился геопозицией)"}
        place = await geocode_reverse(user_lat, user_lng)
        return {"lat": user_lat, "lng": user_lng, "place": place}
    if name == "find_nearby":
        if user_lat is None or user_lng is None:
            return {"error": "местоположение недоступно"}
        try:
            items = await poi_find_nearby(args.get("category", ""), user_lat, user_lng, 1500)
        except PoiError as e:
            return {"error": str(e)}
        return {"places": items[:10]}
    if name == "get_saved_places":
        rows = db.query(SavedPlace).filter(SavedPlace.user_id == user.id).all()
        return {"places": [{"name": r.name, "lat": r.lat, "lng": r.lng, "note": r.note} for r in rows]}
    if name == "search_attractions":
        return {
            "attractions": search_attractions(db, city=args.get("city"), query=args.get("query"))
        }

    # --- Действия: копим команду для приложения, а Gemini возвращаем подтверждение. ---
    if name in ("show_on_map", "build_route", "call_taxi"):
        place = await _resolve_place(args, db, user)
        if not place:
            return {"error": "место не найдено"}
        action = {"type": name, "name": place["name"], "lat": place["lat"], "lng": place["lng"]}
        if name == "build_route":
            mode = args.get("mode", "walking")
            action["mode"] = "driving" if mode == "driving" else "walking"
        if actions is not None:
            actions.append(action)
        return {"status": "ok", "place": place["name"]}

    return {"error": f"неизвестный инструмент: {name}"}
