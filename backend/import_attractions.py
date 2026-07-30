"""Импорт достопримечательностей в таблицу attractions из JSON-файла.

Формат файла — см. `data/attractions_tashkent.json`: объект с ключом `items`,
внутри записи с name/city/lat/lng/description. Координаты берутся из OSM и
проверяются заранее — скрипт их не выдумывает и не геокодирует.

Запуск (внутри контейнера на VPS):
    docker cp data/attractions_tashkent.json guide-backend:/tmp/attr.json
    docker exec guide-backend python import_attractions.py /tmp/attr.json

Идемпотентно по паре (name, city): существующие записи обновляются, новые
добавляются, ничего не удаляется. Поэтому файл можно заливать повторно после
правки описаний — дубликатов не будет.

`hours` и `ticket_info` скрипт НЕ трогает: по модели туда вносят только
проверенные данные, а часы работы и цены меняются. Их заполняют через админку.
"""

import argparse
import json

from app.database import SessionLocal
from app.models import Attraction

REQUIRED = ("name", "city", "lat", "lng")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="путь к JSON-файлу с достопримечательностями")
    ap.add_argument("--dry-run", action="store_true", help="только показать, что будет сделано")
    args = ap.parse_args()

    with open(args.file, encoding="utf-8") as f:
        payload = json.load(f)
    items = payload["items"] if isinstance(payload, dict) else payload

    # Проверяем файл целиком до первой записи в базу: лучше упасть на разборе,
    # чем залить половину.
    for i, it in enumerate(items):
        missing = [k for k in REQUIRED if it.get(k) in (None, "")]
        if missing:
            raise SystemExit(f"запись #{i} ({it.get('name')!r}): нет полей {missing}")

    db = SessionLocal()
    added = updated = 0
    try:
        for it in items:
            row = (
                db.query(Attraction)
                .filter(Attraction.name == it["name"], Attraction.city == it["city"])
                .first()
            )
            if row:
                row.lat = it["lat"]
                row.lng = it["lng"]
                row.description = it.get("description") or row.description
                updated += 1
            else:
                db.add(
                    Attraction(
                        name=it["name"],
                        city=it["city"],
                        lat=it["lat"],
                        lng=it["lng"],
                        description=it.get("description"),
                        is_active=True,
                    )
                )
                added += 1
        if args.dry_run:
            db.rollback()
            print(f"[dry-run] добавилось бы: {added}, обновилось бы: {updated}")
        else:
            db.commit()
            print(f"добавлено: {added}, обновлено: {updated}")
        print(f"всего в таблице: {db.query(Attraction).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
