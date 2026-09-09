#!/usr/bin/env python3
"""Generate the reviewed two-kind common-topic dialogue pack for all stable locales."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ["zh", "en", "ko", "ru", "ja", "vi"]
RELATIVE = "dialogue/common-topics.json"
CATEGORIES = ["Mining", "Building", "Cooking", "Farming", "Ranching", "Research",
              "Technicals", "MedicalAid", "Hauling", "Art", "Suits", "Rocketry",
              "Basekeeping", "SwimmingSkills", "BionicSkills"]
LABELS = {
    "zh": ["挖掘", "建造", "烹饪", "耕作", "畜牧", "研究", "机械操作", "医疗",
           "搬运", "艺术", "太空服作业", "火箭", "基地维护", "游泳", "仿生技能"],
    "en": ["mining", "building", "cooking", "farming", "ranching", "research",
           "machine operation", "medical care", "hauling", "art", "suit work",
           "rocketry", "basekeeping", "swimming", "bionic skills"],
    "ko": ["채굴", "건설", "요리", "농사", "목축", "연구", "기계 조작", "의료",
           "운반", "예술", "슈트 작업", "로켓 공학", "기지 관리", "수영", "바이오닉 기술"],
    "ru": ["добыча", "строительство", "готовка", "земледелие", "животноводство",
           "исследования", "работа с техникой", "медицина", "переноска грузов",
           "искусство", "работа в скафандре", "ракетостроение", "обслуживание базы",
           "плавание", "бионические навыки"],
    "ja": ["採掘", "建築", "料理", "農業", "牧畜", "研究", "機械操作", "医療", "運搬",
           "芸術", "スーツ作業", "ロケット工学", "基地整備", "水泳", "バイオニックスキル"],
    "vi": ["đào mỏ", "xây dựng", "nấu ăn", "trồng trọt", "chăn nuôi", "nghiên cứu",
           "vận hành máy", "y tế", "vận chuyển", "nghệ thuật", "làm việc với bộ đồ",
           "kỹ thuật tên lửa", "bảo trì căn cứ", "bơi lội", "kỹ năng sinh học máy"],
}
LINES = {
    "zh": {
        "interest": ("原来你也喜欢{topic}。", "当然。聊这个总比聊氧气警报轻松。"),
        "work": ("今天的{topic}活儿，你也碰上了？", "碰上了。我们可以对对各自的办法。"),
    },
    "en": {
        "interest": ("So you're interested in {topic}, too.", "I am. It beats talking about oxygen alarms."),
        "work": ("Did you work on {topic} today, too?", "I did. Let's compare how we handled it."),
    },
    "ko": {
        "interest": ("너도 {topic}에 관심이 있었구나.", "응. 산소 경보 이야기보다 훨씬 즐겁지."),
        "work": ("오늘 {topic} 일을 너도 했어?", "응. 서로 어떻게 했는지 비교해 보자."),
    },
    "ru": {
        "interest": ("Тебе тоже интересна тема «{topic}»?", "Да. Это приятнее разговоров о тревоге из-за кислорода."),
        "work": ("Ты тоже сегодня занимался темой «{topic}»?", "Да. Давай сравним наши подходы."),
    },
    "ja": {
        "interest": ("君も{topic}が好きだったんだね。", "うん。酸素警報の話よりずっと楽しいよ。"),
        "work": ("今日、君も{topic}をやっていたの？", "うん。お互いのやり方を比べてみよう。"),
    },
    "vi": {
        "interest": ("Hóa ra bạn cũng thích {topic}.", "Đúng vậy. Nói chuyện này vui hơn báo động oxy nhiều."),
        "work": ("Hôm nay bạn cũng làm việc về {topic} à?", "Ừ. Hãy thử so sánh cách làm của chúng ta."),
    },
}


def build(locale: str) -> dict:
    candidates = []
    ordinal = 13001
    for kind in ("interest", "work"):
        first, second = LINES[locale][kind]
        for category, label in zip(CATEGORIES, LABELS[locale]):
            topic = f"common_{kind}.{category}"
            candidates.append({
                "candidateId": f"storylet.casual.common-{kind}.{category.lower()}.001",
                "diversityKey": topic,
                "storyletId": "Casual", "contractRevision": 1, "status": "reviewed",
                "selection": {"resolvedTopics": [topic]}, "weight": 1,
                "ordinal": ordinal,
                "turns": [
                    {"turnId": "a", "speakerSlot": 0, "text": first.format(topic=label)},
                    {"turnId": "b", "speakerSlot": 1, "text": second.format(topic=label)},
                ],
            })
            ordinal += 1
    return {"locale": locale, "family": "common-topics", "candidates": candidates}


def content_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render(path: Path, payload: dict, check: bool) -> None:
    value = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != value:
            raise SystemExit(f"common-topic pack is stale: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")


def update_contract(check: bool) -> None:
    path = ROOT / "contracts" / "dialogue" / "topic-coverage.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    ready = [f"common_{kind}.{category}" for kind in ("interest", "work")
             for category in CATEGORIES]
    for locale in LOCALES:
        payload["locales"][locale]["readyCommonTopics"] = ready
    render(path, payload, check)


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
                     if item.get("path", "").startswith("dialogue/")), default=-1) + 1
        payload["files"].insert(index, row)
    else:
        payload["files"][index] = row
    render(path, payload, check)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for locale in LOCALES:
        render(ROOT / "locales" / locale / RELATIVE, build(locale), args.check)
    update_contract(args.check)
    for locale in LOCALES[1:]:
        update_provenance(locale, args.check)
    print("Common-topic dialogue pack " + ("clean" if args.check else "written") +
          f": {len(CATEGORIES) * 2} topics × {len(LOCALES)} locales")


if __name__ == "__main__":
    main()
