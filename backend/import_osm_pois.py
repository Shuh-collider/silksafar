"""Импорт точек OpenStreetMap в нашу базу из файла выгрузки (.osm.pbf).

Зачем: публичный Overpass даёт два слота на весь мир, и карта в приложении
пустела ровно тогда, когда её открывали. Свой снимок всегда на месте.

Файл выгрузки уже лежит на VPS: он же используется для сборки маршрутизатора
OSRM (`~/osrm/data/car/uzbekistan-latest.osm.pbf`). Скачивать ничего не нужно.

КАК ЗАПУСКАТЬ И ОБНОВЛЯТЬ. Одной командой на сервере, во временном контейнере —
на саму машину ничего не ставится, контейнер удаляется сам:

    docker run --rm --name osm-import \\
      --env-file /home/shuhratrasulev/guide-backend/.env \\
      -v guide_backend_data:/data \\
      -v /home/shuhratrasulev/osrm/data/car/uzbekistan-latest.osm.pbf:/tmp/uz.osm.pbf:ro \\
      guide-backend:latest \\
      sh -c 'apt-get update -qq && apt-get install -y -qq libexpat1 libbz2-1.0 zlib1g \\
             && pip install --no-cache-dir --quiet osmium \\
             && python import_osm_pois.py /tmp/uz.osm.pbf'

Библиотеки ставятся прямо в команде не от лени: osmium нужен раз в несколько
месяцев, и держать его в образе бэкенда ради этого незачем. `libexpat1` —
обязателен, без него `import osmium` падает с ImportError (в python-slim его
нет). Прогон занимает несколько минут и читает файл дважды.

Импорт идемпотентен: точки опознаются по osm_id, повторный запуск обновляет
существующие и добавляет новые. Чтобы обновить данные, сначала скачайте свежий
файл выгрузки с Geofabrik поверх старого.

Почему два прохода по файлу, а не один с кэшем координат: у osmium есть режим
`locations=True`, который держит в памяти координаты ВСЕХ узлов страны — это
сотни мегабайт на машине, где их и так впритык. Нам нужны координаты лишь тех
узлов, из которых состоят помеченные здания, а их тысячи. Поэтому: первый
проход собирает точки и списки узлов нужных зданий, второй — координаты только
этих узлов.
"""

import sys
import datetime as dt

import osmium

sys.path.insert(0, "/app")

from app.database import SessionLocal, Base, engine  # noqa: E402
from app.models import OsmPoi  # noqa: E402

# Те же категории, что и у Overpass-провайдера (app/poi_provider.py).
# Держать их синхронными обязательно: приложение просит категорию по имени.
CATEGORY_TAGS = {
    "atm": ("amenity", "atm"),
    "bank": ("amenity", "bank"),
    "cafe": ("amenity", "cafe"),
    "restaurant": ("amenity", "restaurant"),
    "pharmacy": ("amenity", "pharmacy"),
    "hotel": ("tourism", "hotel"),
}


def _category_of(tags) -> str | None:
    for category, (key, value) in CATEGORY_TAGS.items():
        if tags.get(key) == value:
            return category
    return None


def _name_of(tags) -> str:
    # Имя на русском и английском полезнее локального для иностранного туриста,
    # но если их нет — берём то, что есть.
    return tags.get("name") or tags.get("name:ru") or tags.get("name:en") or ""


class FirstPass(osmium.SimpleHandler):
    """Точки — сразу готовы. Здания — запоминаем, из каких узлов состоят."""

    def __init__(self):
        super().__init__()
        self.pois: list[dict] = []
        self.pending_ways: list[dict] = []
        self.needed_nodes: set[int] = set()

    def node(self, n):
        category = _category_of(n.tags)
        if category:
            self.pois.append(
                {
                    "osm_id": f"n{n.id}",
                    "name": _name_of(n.tags),
                    "category": category,
                    "lat": n.location.lat,
                    "lng": n.location.lon,
                }
            )

    def way(self, w):
        category = _category_of(w.tags)
        if not category:
            return
        node_ids = [nd.ref for nd in w.nodes]
        if not node_ids:
            return
        self.pending_ways.append(
            {"osm_id": f"w{w.id}", "name": _name_of(w.tags), "category": category, "nodes": node_ids}
        )
        self.needed_nodes.update(node_ids)


class SecondPass(osmium.SimpleHandler):
    """Координаты только тех узлов, что понадобились зданиям."""

    def __init__(self, needed: set[int]):
        super().__init__()
        self.needed = needed
        self.coords: dict[int, tuple[float, float]] = {}

    def node(self, n):
        if n.id in self.needed:
            self.coords[n.id] = (n.location.lat, n.location.lon)


def main(path: str) -> None:
    print(f"Читаю {path}")

    first = FirstPass()
    first.apply_file(path)
    print(f"  точек с нужными тегами: {len(first.pois)}")
    print(f"  зданий с нужными тегами: {len(first.pending_ways)}")

    if first.pending_ways:
        second = SecondPass(first.needed_nodes)
        second.apply_file(path)
        print(f"  координат узлов найдено: {len(second.coords)}")

        skipped = 0
        for way in first.pending_ways:
            points = [second.coords[i] for i in way["nodes"] if i in second.coords]
            if not points:
                skipped += 1
                continue
            # Центр здания — среднее по его узлам. Для метки на карте этого
            # достаточно; геометрически точный центроид тут не нужен.
            lat = sum(p[0] for p in points) / len(points)
            lng = sum(p[1] for p in points) / len(points)
            first.pois.append(
                {
                    "osm_id": way["osm_id"],
                    "name": way["name"],
                    "category": way["category"],
                    "lat": lat,
                    "lng": lng,
                }
            )
        if skipped:
            print(f"  зданий без координат (пропущено): {skipped}")

    by_category: dict[str, int] = {}
    for poi in first.pois:
        by_category[poi["category"]] = by_category.get(poi["category"], 0) + 1

    print("\nИтого к загрузке:")
    for category in sorted(by_category):
        print(f"  {category:11} {by_category[category]}")
    print(f"  {'всего':11} {len(first.pois)}")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = {row[0] for row in db.query(OsmPoi.osm_id).all()}
        print(f"\nВ базе уже: {len(existing)}")

        now = dt.datetime.utcnow()
        added = updated = 0
        for poi in first.pois:
            if poi["osm_id"] in existing:
                db.query(OsmPoi).filter(OsmPoi.osm_id == poi["osm_id"]).update(
                    {
                        "name": poi["name"],
                        "category": poi["category"],
                        "lat": poi["lat"],
                        "lng": poi["lng"],
                        "imported_at": now,
                    }
                )
                updated += 1
            else:
                db.add(OsmPoi(**poi, imported_at=now))
                added += 1
            if (added + updated) % 2000 == 0:
                db.commit()
        db.commit()
        print(f"Добавлено: {added}, обновлено: {updated}, всего в базе: {db.query(OsmPoi).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Укажите путь к .osm.pbf")
    main(sys.argv[1])
