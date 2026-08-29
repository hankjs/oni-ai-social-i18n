#!/usr/bin/env python3
"""Generate reviewed, fully materialized Topic matrix candidates from authored phrase banks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_LOCALES = ["en", "ko", "ru", "ja", "vi"]
PERSONALITIES = [
    "hothead", "crybaby", "loud", "eater", "nervous", "jumpy", "gentle",
    "curious", "slow", "early", "night", "sleepy", "athlete",
]
MOODS = ["buoyant", "settled", "discouraged", "strained", "overwhelmed"]

ZH_PERSONALITY = {
    "hothead": "我直说，",
    "crybaby": "我不想哭，可是",
    "loud": "大家听我说！",
    "eater": "我一直在留意补给，",
    "nervous": "我有点担心，",
    "jumpy": "先别突然靠近；",
    "gentle": "慢慢说，",
    "curious": "我想把原因弄清楚：",
    "slow": "不急，我慢慢讲，",
    "early": "趁班次还早，",
    "night": "夜班让我看得很清楚：",
    "sleepy": "我可能说得有点迷糊，",
    "athlete": "从体力分配看，",
}

ZH_MOOD = {
    "buoyant": ("心情还不错，可这项身体信号不能忽略：", "还来得及处理。"),
    "settled": ("先按事实说，", "按正常步骤处理就好。"),
    "discouraged": ("本来就提不起劲，现在", "别一个人闷着，我们先解决眼前这件事。"),
    "strained": ("我已经绷得很紧，而且", "先把负担降下来，别再硬撑。"),
    "overwhelmed": ("事情全挤在一起，我连这点都快扛不住了：", "先停下，我陪你把最急的一项处理掉。"),
}

ZH_TOPICS = {
    "amount.satiety.appraise_negative": {
        "domain": "satiety",
        "speaker": [
            "胃里的空响已经盖过机器声了。",
            "得先找点能补充卡路里的东西。",
            "今天的配餐量恐怕撑不到下一班。",
            "再这么耗下去，手脚都会慢下来。",
            "你那边还有没分配的口粮吗？",
        ],
        "listener": [
            "我也听见了，先去确认你的卡路里储备。",
            "走，先补充热量，别拿意志力硬顶。",
            "我帮你查配额；这是吃不够，不是挑食。",
            "先暂停高强度工作，低卡路里状态会拖慢动作。",
            "有一份备用的，我们按配额分，不碰紧急储备。",
        ],
    },
    "amount.stamina.appraise_negative": {
        "domain": "stamina",
        "speaker": [
            "手臂和眼皮都开始发沉了。",
            "体力量表掉得比我预想的快。",
            "这班工作还没结束，我的动作已经慢了半拍。",
            "我需要短暂停一下，不然下一步容易出错。",
            "能和我换一段轻一点的工作吗？",
        ],
        "listener": [
            "我看出来了，这是疲劳信号，不是对床铺的评价。",
            "先把节奏降下来，体力恢复后再接重活。",
            "我来接这一段，你先缓一缓。",
            "可以，先休息和补氧，别在疲劳时操作机器。",
            "我们换班，我守着进度，不让任务漏掉。",
        ],
    },
}


def build_zh() -> dict:
    candidates = []
    ordinal = 10_000
    for topic, authored in ZH_TOPICS.items():
        slug = topic.replace("_", "-")
        for personality in PERSONALITIES:
            for mood in MOODS:
                mood_lead, mood_reply = ZH_MOOD[mood]
                for angle, (speaker, listener) in enumerate(zip(
                    authored["speaker"], authored["listener"], strict=True), 1
                ):
                    candidate_id = f"topic.{slug}.{personality}.{mood}.angle-{angle}"
                    candidates.append({
                        "candidateId": candidate_id,
                        "diversityKey": candidate_id,
                        "storyletId": "Casual",
                        "contractRevision": 1,
                        "status": "reviewed",
                        "selection": {
                            "actors": [{
                                "slot": 0,
                                "personalities": [personality],
                                "moods": [mood],
                            }],
                            "resolvedTopics": [topic],
                            "conversationKinds": ["amount_state"],
                            "topicDomains": [authored["domain"]],
                            "utteranceModes": ["dissatisfaction"],
                            "appraisals": ["negative"],
                        },
                        "weight": 1,
                        "ordinal": ordinal,
                        "turns": [
                            {"turnId": "speaker", "speakerSlot": 0,
                             "text": ZH_PERSONALITY[personality] + mood_lead + speaker},
                            {"turnId": "listener", "speakerSlot": 1,
                             "text": mood_reply + listener},
                        ],
                    })
                    ordinal += 1
    return {"locale": "zh", "family": "casual-topic-pilot", "candidates": candidates}


def content_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def scaffold_unreleased_locales(check: bool) -> None:
    source = ROOT / "locales" / "zh" / "dialogue" / "topic-pilot.json"
    source_hash = content_hash(source)
    for locale in TARGET_LOCALES:
        target = ROOT / "locales" / locale / "dialogue" / "topic-pilot.json"
        rendered = json.dumps({"locale": locale, "family": "casual-topic-pilot",
                               "candidates": []}, ensure_ascii=False, indent=2) + "\n"
        if check:
            if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"unreleased Topic scaffold is stale: {target}")
        else:
            target.write_text(rendered, encoding="utf-8")
        provenance_path = ROOT / "provenance" / f"{locale}.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        row = {
            "path": "dialogue/topic-pilot.json",
            "sourceHash": source_hash,
            "targetHash": content_hash(target),
            "reviewStatus": "reviewed",
        }
        rows = [item for item in provenance["files"]
                if item.get("path") != row["path"]] + [row]
        provenance["files"] = sorted(rows, key=lambda item: item["path"])
        provenance_rendered = json.dumps(provenance, ensure_ascii=False, indent=2) + "\n"
        if check:
            if provenance_path.read_text(encoding="utf-8") != provenance_rendered:
                raise SystemExit(f"Topic provenance is stale: {provenance_path}")
        else:
            provenance_path.write_text(provenance_rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", choices=["zh"], default="zh")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_zh()
    target = ROOT / "locales" / args.locale / "dialogue" / "topic-pilot.json"
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"generated Topic pack is stale: {target}")
        scaffold_unreleased_locales(True)
        print(f"Topic pack clean: {len(payload['candidates'])} candidates")
        return
    target.write_text(rendered, encoding="utf-8")
    scaffold_unreleased_locales(False)
    print(f"wrote {target}: {len(payload['candidates'])} candidates")


if __name__ == "__main__":
    main()
