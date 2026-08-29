#!/usr/bin/env python3
"""Generate materialized listener responses for the independent P4 composer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from generate_dialogue_topic_pack import LOCALES, PERSONALITIES, TEXT


ROOT = Path(__file__).resolve().parents[1]
RELATIONSHIPS = ["Strangers", "Acquainted", "Friends", "Crush", "Couple",
                 "ColdWar", "BrokenUp", "Grieving", "Mourning", "Rival"]
AVAILABILITIES = ["receptive", "reserved", "unavailable"]
ACTS = ["acknowledge", "reassure", "practical_help", "gentle_boundary", "defer"]

COPY = {
    "zh": {
        "relationship": {"Strangers": "虽然我们还不熟，", "Acquainted": "以我们现在的交情，", "Friends": "作为朋友，", "Crush": "因为我很在意你，", "Couple": "作为你的伴侣，", "ColdWar": "即使我们正在冷战，", "BrokenUp": "虽然我们已经分开，", "Grieving": "在这段失去伴侣的悲痛里，", "Mourning": "在这段悼念里，", "Rival": "即使我们是对手，"},
        "availability": {"receptive": "我现在能认真听你说完。", "reserved": "我现在只能留出一点注意力，我们先说重点。", "unavailable": "我现在无法好好回应，等状态允许时再继续。"},
        "act": {"acknowledge": "我听见你在说什么了。", "reassure": "这件事不用由你一个人扛。", "practical_help": "我们先定一个具体、能完成的下一步。", "gentle_boundary": "我会尊重地回应，也需要把彼此的边界说清楚。", "defer": "这值得一次不敷衍的回应。"},
    },
    "en": {
        "relationship": {"Strangers": "We do not know each other well, but", "Acquainted": "Given where we are as acquaintances,", "Friends": "As your friend,", "Crush": "Because I care deeply about you,", "Couple": "As your partner,", "ColdWar": "Even while we are in a cold war,", "BrokenUp": "Although we are no longer together,", "Grieving": "In the grief of losing a partner,", "Mourning": "While we are mourning,", "Rival": "Even as rivals,"},
        "availability": {"receptive": "I can give this my full attention now.", "reserved": "I only have room for a short exchange, so let us focus.", "unavailable": "I cannot respond properly now; let us return when I can."},
        "act": {"acknowledge": "I hear what you are saying.", "reassure": "You do not have to carry this alone.", "practical_help": "Let us choose one concrete next step.", "gentle_boundary": "I will answer respectfully, and I need our boundaries to stay clear.", "defer": "This deserves a response that is not rushed."},
    },
    "ko": {
        "relationship": {"Strangers": "아직 서로 잘 모르지만,", "Acquainted": "지금 우리 사이에서는,", "Friends": "친구로서,", "Crush": "너를 많이 아끼니까,", "Couple": "네 연인으로서,", "ColdWar": "우리가 냉전 중이어도,", "BrokenUp": "이미 헤어졌지만,", "Grieving": "연인을 잃은 슬픔 속에서도,", "Mourning": "함께 애도하는 동안,", "Rival": "우리가 경쟁자라 해도,"},
        "availability": {"receptive": "지금은 끝까지 집중해서 들을 수 있어.", "reserved": "지금은 짧게만 이야기할 수 있으니 핵심부터 말하자.", "unavailable": "지금은 제대로 답하기 어려워. 여유가 생기면 다시 이야기하자."},
        "act": {"acknowledge": "네가 무슨 말을 하는지 들었어.", "reassure": "이 일을 혼자 짊어질 필요는 없어.", "practical_help": "지금 할 수 있는 구체적인 다음 단계 하나를 정하자.", "gentle_boundary": "존중하며 답하되, 서로의 경계는 분명히 하고 싶어.", "defer": "이건 서두르지 않은 제대로 된 답을 받을 이야기야."},
    },
    "ru": {
        "relationship": {"Strangers": "Мы ещё плохо знакомы, но", "Acquainted": "При наших нынешних отношениях,", "Friends": "Как друг,", "Crush": "Потому что ты мне очень дорог,", "Couple": "Как твой партнёр,", "ColdWar": "Даже пока между нами холодная война,", "BrokenUp": "Хотя мы уже не вместе,", "Grieving": "В скорби после потери партнёра,", "Mourning": "Пока мы переживаем утрату,", "Rival": "Даже если мы соперники,"},
        "availability": {"receptive": "Сейчас я могу выслушать тебя внимательно до конца.", "reserved": "Сейчас у меня есть силы только на короткий разговор, поэтому начнём с главного.", "unavailable": "Сейчас я не смогу ответить как следует; вернёмся к этому позже."},
        "act": {"acknowledge": "Я слышу, что ты говоришь.", "reassure": "Тебе не нужно нести это в одиночку.", "practical_help": "Давай выберем один конкретный следующий шаг.", "gentle_boundary": "Я отвечу уважительно, но хочу сохранить ясные границы.", "defer": "Эта тема заслуживает неторопливого ответа."},
    },
    "ja": {
        "relationship": {"Strangers": "まだよく知らない間柄だけど、", "Acquainted": "今の知り合いとしての関係なら、", "Friends": "友達として、", "Crush": "君をとても大切に思うから、", "Couple": "パートナーとして、", "ColdWar": "冷戦中であっても、", "BrokenUp": "もう別れた二人だけど、", "Grieving": "伴侶を失った悲しみの中でも、", "Mourning": "悼んでいる間も、", "Rival": "ライバル同士でも、"},
        "availability": {"receptive": "今なら最後まできちんと聞けるよ。", "reserved": "今は短い話しか受け止められないから、要点から話そう。", "unavailable": "今は十分に答えられない。余裕が戻ったら続けよう。"},
        "act": {"acknowledge": "言いたいことは受け止めたよ。", "reassure": "一人で抱える必要はないよ。", "practical_help": "まず実行できる次の一歩を一つ決めよう。", "gentle_boundary": "敬意を持って答えるけれど、お互いの境界は明確にしたい。", "defer": "これは急がず、きちんと答えるべき話だ。"},
    },
    "vi": {
        "relationship": {"Strangers": "Dù ta chưa biết nhau rõ,", "Acquainted": "Với quan hệ quen biết hiện tại,", "Friends": "Với tư cách bạn bè,", "Crush": "Vì tôi thật sự quan tâm đến bạn,", "Couple": "Với tư cách người đồng hành của bạn,", "ColdWar": "Ngay cả khi ta đang lạnh nhạt,", "BrokenUp": "Dù ta không còn ở bên nhau,", "Grieving": "Trong nỗi đau mất người bạn đời,", "Mourning": "Trong thời gian tưởng niệm,", "Rival": "Ngay cả khi ta là đối thủ,"},
        "availability": {"receptive": "Bây giờ tôi có thể chú ý và nghe bạn nói hết.", "reserved": "Lúc này tôi chỉ đủ sức cho một cuộc trao đổi ngắn, nên hãy tập trung vào điều chính.", "unavailable": "Bây giờ tôi chưa thể đáp lại tử tế; ta sẽ nói tiếp khi tôi sẵn sàng."},
        "act": {"acknowledge": "Tôi đã nghe và hiểu điều bạn đang nói.", "reassure": "Bạn không phải gánh chuyện này một mình.", "practical_help": "Ta hãy chọn một bước tiếp theo thật cụ thể.", "gentle_boundary": "Tôi sẽ trả lời với sự tôn trọng, đồng thời cần giữ ranh giới rõ ràng.", "defer": "Chuyện này xứng đáng có một lời đáp không vội vàng."},
    },
}


def build(locale: str) -> dict:
    copy = COPY[locale]
    joiner = "" if locale in {"zh", "ja"} else " "
    candidates = []
    ordinal = 1
    for act_index, act in enumerate(ACTS):
        for relationship_index, relationship in enumerate(RELATIONSHIPS):
            for availability_index, availability in enumerate(AVAILABILITIES):
                personality = PERSONALITIES[(act_index * 30 + relationship_index * 3 +
                                             availability_index) % len(PERSONALITIES)]
                base = joiner.join((copy["relationship"][relationship], copy["act"][act],
                                    copy["availability"][availability]))
                for style in ("generic", personality):
                    candidate_id = (f"response.{act}.{relationship.lower()}."
                                    f"{availability}.{style}")
                    actors = [] if style == "generic" else [
                        {"slot": 1, "personalities": [personality]}]
                    text = base if style == "generic" else joiner.join(
                        (TEXT[locale]["personality"][personality], base))
                    candidates.append({
                        "candidateId": candidate_id,
                        "diversityKey": candidate_id,
                        "storyletId": "ListenerResponse",
                        "contractRevision": 1,
                        "status": "reviewed",
                        "selection": {"actors": actors,
                                      "relationshipStates": [relationship],
                                      "responseActs": [act],
                                      "listenerAvailabilities": [availability]},
                        "weight": 1,
                        "ordinal": ordinal,
                        "turns": [{"turnId": "listener", "speakerSlot": 1, "text": text}],
                    })
                    ordinal += 1
    return {"locale": locale, "family": "listener-response-pack", "candidates": candidates}


def content_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def update_provenance(locale: str, check: bool) -> None:
    relative = "dialogue/listener-responses.json"
    source = ROOT / "locales" / "zh" / relative
    target = ROOT / "locales" / locale / relative
    row = {"path": relative, "sourceHash": content_hash(source),
           "targetHash": content_hash(target), "reviewStatus": "reviewed"}
    path = ROOT / "provenance" / f"{locale}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    index = next((i for i, item in enumerate(payload["files"])
                  if item.get("path") == relative), None)
    if index is None:
        index = max((i for i, item in enumerate(payload["files"])
                     if item.get("path", "").startswith("dialogue/")), default=-1) + 1
        payload["files"].insert(index, row)
    else:
        payload["files"][index] = row
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if check:
        if path.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"listener response provenance is stale: {path}")
    else:
        path.write_text(rendered, encoding="utf-8")


def generate(locales: list[str], check: bool) -> None:
    for locale in sorted(locales, key=lambda value: value != "zh"):
        path = ROOT / "locales" / locale / "dialogue" / "listener-responses.json"
        rendered = json.dumps(build(locale), ensure_ascii=False, indent=2) + "\n"
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"listener response pack is stale: {path}")
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
    print(f"listener response pack {'clean' if args.check else 'written'}: "
          f"{len(build(locales[0])['candidates'])} candidates × {len(locales)} locale(s)")


if __name__ == "__main__":
    main()
