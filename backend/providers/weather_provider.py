"""Погода — за слоем провайдера. Сейчас Open-Meteo (бесплатно, без ключа).
Позже адаптер можно заменить на OpenWeatherMap, не трогая приложение."""

import aiohttp

WEATHER_CODE_TEXT = {
    0: "Ясно",
    1: "Преимущественно ясно",
    2: "Переменная облачность",
    3: "Пасмурно",
    45: "Туман",
    48: "Изморозь",
    51: "Морось слабая",
    53: "Морось",
    55: "Морось сильная",
    61: "Дождь слабый",
    63: "Дождь",
    65: "Дождь сильный",
    71: "Снег слабый",
    73: "Снег",
    75: "Снег сильный",
    80: "Ливень слабый",
    81: "Ливень",
    82: "Ливень сильный",
    95: "Гроза",
}


class WeatherError(Exception):
    pass


async def get_weather(lat: float, lng: float) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lng}"
        "&current=temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code"
        "&forecast_days=7"
        "&timezone=auto"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    raise WeatherError(f"Open-Meteo вернул {resp.status}")
                data = await resp.json()
    except aiohttp.ClientError as e:
        raise WeatherError(str(e))

    cur = data.get("current", {})
    code = cur.get("weather_code")

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    dcodes = daily.get("weather_code", [])
    forecast = [
        {
            "date": dates[i],
            "temp_max": tmax[i],
            "temp_min": tmin[i],
            # condition — русский текст как запасной вариант; weather_code (WMO)
            # приложение переводит само под выбранный язык интерфейса.
            "condition": WEATHER_CODE_TEXT.get(dcodes[i], "—"),
            "weather_code": dcodes[i],
        }
        for i in range(len(dates))
    ]

    return {
        "temp_c": cur.get("temperature_2m"),
        "condition": WEATHER_CODE_TEXT.get(code, "—"),
        "weather_code": code,
        "wind_kph": cur.get("wind_speed_10m"),
        "humidity": cur.get("relative_humidity_2m"),
        "updated_at": cur.get("time"),
        "forecast": forecast,
    }
