#!/usr/bin/env python3
"""Generate the locale-owned safe fallback names used by native Topic templates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ["zh", "en", "ko", "ru", "ja", "vi"]
SUBJECTS = {
    "zh": ["食物", "床铺", "装饰", "材料", "建筑", "生物", "植物", "装备", "设施", "物品", "压力", "士气", "健康", "饱腹状态", "体力", "免疫状态", "当前工作"],
    "en": ["food", "the bed", "the decor", "the material", "the building", "the creature", "the plant", "the equipment", "the facility", "the item", "stress", "morale", "health", "the calorie reserve", "stamina", "immunity", "the current job"],
    "ko": ["음식", "침대", "장식", "재료", "건물", "생물", "식물", "장비", "시설", "물건", "스트레스", "사기", "건강", "칼로리 상태", "체력", "면역 상태", "현재 작업"],
    "ru": ["еда", "кровать", "декор", "материал", "здание", "существо", "растение", "снаряжение", "устройство", "предмет", "стресс", "моральный дух", "здоровье", "запас калорий", "выносливость", "иммунитет", "текущая работа"],
    "ja": ["食べ物", "ベッド", "装飾", "素材", "建物", "生物", "植物", "装備", "施設", "物", "ストレス", "士気", "健康", "カロリー残量", "体力", "免疫状態", "現在の仕事"],
    "vi": ["thức ăn", "chiếc giường", "đồ trang trí", "vật liệu", "công trình", "sinh vật", "cây", "trang bị", "cơ sở", "vật phẩm", "mức căng thẳng", "tinh thần", "sức khỏe", "lượng calo", "thể lực", "miễn dịch", "công việc hiện tại"],
}
DOMAINS = ["FOOD", "BED", "DECOR", "ELEMENT", "BUILDING", "CREATURE", "PLANT",
           "EQUIPMENT", "FACILITY", "ITEM", "STRESS", "MORALE", "HEALTH", "SATIETY",
           "STAMINA", "IMMUNITY", "CURRENT_JOB"]
RELATIVE = "ui/social.dialogue_topic.json"


def build(locale: str) -> dict:
    entries = []
    for domain, text in zip(DOMAINS, SUBJECTS[locale]):
        entries.append({"key": f"STRINGS.SOCIAL.DIALOGUE_TOPIC.{domain}.NAME",
                        "text": text, "contractRevision": 1, "status": "reviewed"})
    return {"locale": locale, "namespace": "social.dialogue_topic", "entries": entries}


def content_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def update_provenance(locale: str, check: bool) -> None:
    source = ROOT / "locales" / "zh" / RELATIVE
    target = ROOT / "locales" / locale / RELATIVE
    row = {"path": RELATIVE, "sourceHash": content_hash(source),
           "targetHash": content_hash(target), "reviewStatus": "reviewed"}
    path = ROOT / "provenance" / f"{locale}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    index = next((i for i, item in enumerate(payload["files"])
                  if item.get("path") == RELATIVE), None)
    if index is None:
        index = max((i for i, item in enumerate(payload["files"])
                     if item.get("path", "").startswith("ui/")), default=len(payload["files"]) - 1) + 1
        payload["files"].insert(index, row)
    else:
        payload["files"][index] = row
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if check:
        if path.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"native subject provenance is stale: {path}")
    else:
        path.write_text(rendered, encoding="utf-8")


def generate(locales: list[str], check: bool) -> None:
    for locale in locales:
        path = ROOT / "locales" / locale / RELATIVE
        rendered = json.dumps(build(locale), ensure_ascii=False, indent=2) + "\n"
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"native subject pack is stale: {path}")
        else:
            path.write_text(rendered, encoding="utf-8")
    for locale in LOCALES[1:]:
        if locale in locales: update_provenance(locale, check)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", choices=[*LOCALES, "all"], default="all")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    locales = LOCALES if args.locale == "all" else [args.locale]
    generate(locales, args.check)
    print(f"Native Topic subject pack {'clean' if args.check else 'written'}: "
          f"{len(DOMAINS)} subjects × {len(locales)} locale(s)")


if __name__ == "__main__":
    main()
