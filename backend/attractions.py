"""Достопримечательности: засев стартовых записей + поиск для ИИ-гида.

Засеваем НЕСКОЛЬКО флагманских объектов с проверяемыми фактами (название,
город, описание, координаты). Часы работы и цену билета НЕ выдумываем — их
позже заполняет админ проверенными данными (иначе смысл курируемого контента
теряется). Дальше база расширяется через админку."""

import math

from sqlalchemy.orm import Session

from .models import Attraction

# Флагманские достопримечательности — общеизвестные факты, координаты
# приблизительные, но указывают на нужный памятник. hours/ticket — пусто.
DEFAULT_ATTRACTIONS = [
    {
        "name": "Регистан",
        "city": "Самарканд",
        "lat": 39.6547,
        "lng": 66.9758,
        "description": "Главная площадь Самарканда — ансамбль из трёх медресе (Улугбека, "
        "Шердор и Тилля-Кари) XV–XVII вв., символ Узбекистана.",
    },
    {
        "name": "Шахи-Зинда",
        "city": "Самарканд",
        "lat": 39.6626,
        "lng": 66.9835,
        "description": "Некрополь и ансамбль мавзолеев XI–XV вв. с изразцовой облицовкой, "
        "одно из самых почитаемых мест города.",
    },
    {
        "name": "Мечеть Биби-Ханым",
        "city": "Самарканд",
        "lat": 39.6558,
        "lng": 66.9799,
        "description": "Грандиозная соборная мечеть начала XV века, построенная при Тамерлане.",
    },
    {
        "name": "Мавзолей Гур-Эмир",
        "city": "Самарканд",
        "lat": 39.6486,
        "lng": 66.9690,
        "description": "Усыпальница Тамерлана и его потомков с узнаваемым ребристым голубым куполом.",
    },
    {
        "name": "Пои-Калян",
        "city": "Бухара",
        "lat": 39.7756,
        "lng": 64.4143,
        "description": "Ансамбль с минаретом Калян (XII в.), мечетью Калян и действующим "
        "медресе Мири-Араб.",
    },
    {
        "name": "Крепость Арк",
        "city": "Бухара",
        "lat": 39.7758,
        "lng": 64.4098,
        "description": "Древняя цитадель и резиденция бухарских эмиров, старейшее сооружение города.",
    },
    {
        "name": "Ляби-Хауз",
        "city": "Бухара",
        "lat": 39.7745,
        "lng": 64.4200,
        "description": "Ансамбль вокруг старинного пруда (хауза) XVI–XVII вв. в центре старого города.",
    },
    {
        "name": "Ичан-Кала",
        "city": "Хива",
        "lat": 41.3781,
        "lng": 60.3597,
        "description": "Внутренний город-крепость Хивы, объект ЮНЕСКО — цельный музей под "
        "открытым небом с медресе, минаретами и дворцами.",
    },
]


def seed_attractions(db: Session) -> None:
    """Засеваем стартовые записи, только если таблица пуста (не перетираем правки админа)."""
    if db.query(Attraction).first():
        return
    for a in DEFAULT_ATTRACTIONS:
        db.add(Attraction(**a))
    db.commit()


def _dict(r: Attraction, distance_km: float | None = None) -> dict:
    d = {"name": r.name, "city": r.city, "description": r.description, "lat": r.lat, "lng": r.lng}
    if r.hours:
        d["hours"] = r.hours
    if r.ticket_info:
        d["ticket_info"] = r.ticket_info
    if distance_km is not None:
        d["distance_km"] = round(distance_km, 2)
        # Готовая формулировка, а не только число. Числа модель округляет
        # по-своему: на объекте в тридцати метрах она уверенно говорила
        # «около 0 км». Пусть берёт фразу как есть.
        d["distance_text"] = _distance_text(distance_km)
    return d


def _distance_text(km: float) -> str:
    if km < 0.1:
        return "вы прямо здесь"
    if km < 1:
        metres = int(round(km * 1000 / 50.0) * 50)
        return f"{metres} м от вас"
    return f"{km:.1f} км от вас".replace(".", ",")


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Грубое расстояние в километрах. В пределах одной страны точности хватает,
    а тригонометрию по каждой строке в базе гонять незачем."""
    dlat = (lat1 - lat2) * 111.0
    dlng = (lng1 - lng2) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlng)


# Города наша база хранит по-русски, а спрашивают о них как попало: турист пишет
# по-английски, модель подставляет «Tashkent», приложение может прислать название
# из геокодера на латинице. Раньше такой запрос не находил НИЧЕГО — фильтр сравнивал
# строки как есть, и «tashkent» не совпадало с «ташкент». Гид отвечал «не могу найти»
# про место, которое лежит в базе.
# Кириллица и латиница перестают быть двумя разными алфавитами: и запрос,
# и текст в базе приводятся к одной латинской форме, после чего сравниваются.
# Так «Регистан» находится по Registan, «Чорсу» по Chorsu, «Хива» по Khiva
# и Xiva — без списка синонимов на каждое название.
_CYR2LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "j",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "s",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
    # узбекская кириллица
    "ў": "u", "қ": "k", "ғ": "g", "ҳ": "h",
}

# Расхождения латинских написаний одного и того же звука: Khiva/Xiva/Хива,
# Samarqand/Samarkand, Chorsu/Чорсу, City/Сити. Порядок правил важен: «ch»
# прячем до замены «c», иначе Chorsu превратится в shorsu.
_LAT_FIXES = (
    ("ch", "\x00"), ("kh", "h"), ("sh", "\x01"),
    # Латинская «c» читается то как «к», то как «с» (Magic — Магик, City — Сити),
    # и по букве это не разрешается. Поэтому c и k сводятся к одному символу:
    # «магик» и «magic» становятся одной строкой. Ценой того, что «кала» и «сала»
    # тоже сольются — для поиска по сорока записям это безопаснее, чем не найти.
    ("x", "h"), ("q", "k"), ("gh", "g"), ("ts", "s"),
    ("c", "s"), ("k", "s"), ("y", "i"),
    ("\x00", "ch"), ("\x01", "sh"),
)


def _key(value: str | None) -> str:
    """Строка в форме, где написание алфавитом уже не имеет значения."""
    s = (value or "").strip().lower()
    s = "".join(_CYR2LAT.get(ch, ch) for ch in s)
    for a, b in _LAT_FIXES:
        s = s.replace(a, b)
    # Дефисы и апострофы узбекской латиницы (oʻ, gʻ) становятся пробелом, а не
    # исчезают: иначе «Шахи-Зинда» склеится в одно слово и перестанет совпадать
    # с «Shahi Zinda».
    s = "".join(ch if ch.isalnum() else " " for ch in s)
    return " ".join(s.split())


_CITY_ALIASES = {
    "ташкент": "ташкент", "tashkent": "ташкент", "toshkent": "ташкент",
    "самарканд": "самарканд", "samarkand": "самарканд", "samarqand": "самарканд",
    "бухара": "бухара", "bukhara": "бухара", "buxoro": "бухара", "buchara": "бухара",
    "хива": "хива", "khiva": "хива", "xiva": "хива",
    "нукус": "нукус", "nukus": "нукус",
    "фергана": "фергана", "fergana": "фергана", "farg'ona": "фергана", "fargona": "фергана",
    "андижан": "андижан", "andijan": "андижан", "andijon": "андижан",
    "наманган": "наманган", "namangan": "наманган",
    "термез": "термез", "termez": "термез", "termiz": "термез",
    "шахрисабз": "шахрисабз", "shakhrisabz": "шахрисабз", "shahrisabz": "шахрисабз",
}


def _skeleton(key: str) -> str:
    """Строка без гласных — «скелет» имени. Пробелы тоже убираем: они стоят
    в разных местах («Биби-Ханым» и Bibi Xonim)."""
    return "".join(ch for ch in key if ch not in "aeiou ")


def _norm_city(value: str | None) -> str:
    raw = (value or "").strip().lower()
    # Сначала точный синоним (он ловит случаи, где транслитерация расходится
    # сильнее обычного), потом общая нормализация.
    if raw in _CITY_ALIASES:
        return _key(_CITY_ALIASES[raw])
    return _key(raw)


def search_attractions(
    db: Session,
    city: str | None = None,
    query: str | None = None,
    limit: int = 10,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> list[dict]:
    """Поиск по нашей базе: по городу и/или по названию объекта.

    Фильтруем в Python, а не через SQL ilike: SQLite lower() не понимает кириллицу,
    поэтому «самарканд» не нашёл бы «Самарканд». Записей тут сотни — это дёшево.
    Совпадения по названию идут первыми: на запрос «Регистан» важнее сам Регистан,
    а не все объекты, где он лишь упомянут в описании.

    Если известны координаты туриста, внутри каждой группы объекты идут от
    ближних к дальним и получают поле distance_km. Порядок групп при этом не
    ломается: на запрос «Регистан» сам Регистан остаётся первым, даже если
    турист стоит у другого объекта из описания.
    """
    rows = (
        db.query(Attraction)
        .filter(Attraction.is_active == True)  # noqa: E712
        .order_by(Attraction.city, Attraction.id)
        .all()
    )
    city_key = _norm_city(city)
    q_key = _key(query)

    by_name: list[Attraction] = []
    by_text: list[Attraction] = []
    for r in rows:
        if city_key:
            row_city = _norm_city(r.city)
            # Точное совпадение по нормализованному имени либо подстрока —
            # второе оставлено для городов, которых нет в словаре синонимов.
            if city_key != row_city and city_key not in row_city:
                continue
        if not q_key:
            by_name.append(r)
        elif q_key in _key(r.name):
            by_name.append(r)
        elif q_key in _key(f"{r.description or ''} {r.city or ''}"):
            by_text.append(r)

    # Запасной проход: если не нашлось ничего, сравниваем без гласных.
    # Гласные — то, что расходится в разных передачах одного имени:
    # «Ханым» и Xonim, «Дрим» и Dream, «Ташкентленд» и Tashkentland.
    # Включается ТОЛЬКО при пустом результате и только для достаточно длинных
    # запросов: на коротких «парк» скелет из согласных совпадёт с чем угодно.
    if q_key and not by_name and not by_text:
        q_skel = _skeleton(q_key)
        if len(q_skel) >= 4:
            for r in rows:
                if city_key:
                    row_city = _norm_city(r.city)
                    if city_key != row_city and city_key not in row_city:
                        continue
                if q_skel in _skeleton(_key(r.name)):
                    by_name.append(r)
                elif q_skel in _skeleton(_key(f"{r.description or ''} {r.city or ''}")):
                    by_text.append(r)

    has_user = user_lat is not None and user_lng is not None
    if not has_user:
        return [_dict(r) for r in (by_name + by_text)[:limit]]

    def dist(r: Attraction) -> float | None:
        if r.lat is None or r.lng is None:
            return None
        return _km(user_lat, user_lng, r.lat, r.lng)

    def ordered(group: list[Attraction]) -> list[Attraction]:
        # Объекты без координат не выбрасываем, но отправляем в конец группы:
        # расстояние до них неизвестно, а не «ноль».
        return sorted(group, key=lambda r: (dist(r) is None, dist(r) or 0.0))

    result = ordered(by_name) + ordered(by_text)
    return [_dict(r, dist(r)) for r in result[:limit]]
