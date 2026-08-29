#!/usr/bin/env python3
"""Generate reviewed topic-generic dialogue for leaves observed in the 2026-08-29 run.

These are complete materialized turns, not runtime fragments. They deliberately remain
topic-generic fallback instead of pretending to satisfy the 13 personality x 5 mood Ready gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ["zh", "en", "ko", "ru", "ja", "vi"]
TARGET_LOCALES = LOCALES[1:]

TOPICS = [
    "current_job.query",
    "amount.health.appraise_positive", "amount.health.query", "amount.health.agreement",
    "amount.morale.appraise_positive", "amount.morale.query", "amount.morale.agreement",
    "amount.immunity.appraise_positive", "amount.immunity.query", "amount.immunity.agreement",
    "amount.stress.appraise_positive", "amount.stress.query", "amount.stress.agreement",
    "amount.satiety.appraise_neutral", "amount.satiety.query",
    "amount.satiety.appraise_positive", "amount.satiety.reflect", "amount.satiety.agreement",
    "amount.stamina.appraise_positive", "amount.stamina.query", "amount.stamina.agreement",
    "amount.stamina.appraise_neutral", "amount.stamina.reflect",
    "recent.building.query", "recent.building.assertion", "recent.building.reflect",
    "recent.building.agreement", "recent.building.disagreement",
    "recent.building.appraise_negative", "recent.building.appraise_positive",
    "recent.food.assertion", "recent.food.query", "recent.food.reflect",
    "recent.food.agreement", "recent.food.appraise_positive", "recent.food.disagreement",
    "recent.food.appraise_negative",
    "recent.bed.query", "recent.bed.reflect", "recent.bed.agreement",
    "recent.bed.appraise_positive", "recent.bed.assertion", "recent.bed.disagreement",
    "recent.bed.appraise_negative",
    "recent.item.query", "recent.item.assertion", "recent.item.agreement",
    "recent.item.reflect", "recent.item.appraise_positive", "recent.item.disagreement",
    "recent.item.appraise_negative",
]

MODE = {
    "query": ("query", "unspecified"),
    "assertion": ("statement", "unspecified"),
    "agreement": ("agreement", "unspecified"),
    "disagreement": ("disagreement", "unspecified"),
    "reflect": ("musing", "unspecified"),
    "appraise_positive": ("satisfaction", "positive"),
    "appraise_neutral": ("nominal", "neutral"),
    "appraise_negative": ("dissatisfaction", "negative"),
}

SUBJECTS = {
    "zh": {"health": "当前健康", "morale": "当前士气", "immunity": "当前免疫状态",
           "stress": "当前压力", "satiety": "当前饱腹状态", "stamina": "当前体力",
           "building": "刚提到的建筑", "food": "刚提到的食物", "bed": "刚提到的床铺",
           "item": "刚提到的物品", "current_job": "当前工作"},
    "en": {"health": "current health", "morale": "current morale",
           "immunity": "current immunity", "stress": "current stress",
           "satiety": "current calorie reserve", "stamina": "current stamina",
           "building": "that building", "food": "that food", "bed": "that bed",
           "item": "that item", "current_job": "the current job"},
    "ko": {"health": "현재 건강", "morale": "현재 사기", "immunity": "현재 면역 상태",
           "stress": "현재 스트레스", "satiety": "현재 칼로리 상태", "stamina": "현재 체력",
           "building": "방금 말한 건물", "food": "방금 말한 음식", "bed": "방금 말한 침대",
           "item": "방금 말한 물건", "current_job": "현재 작업"},
    "ru": {"health": "текущее здоровье", "morale": "текущий моральный дух",
           "immunity": "текущий иммунитет", "stress": "текущий стресс",
           "satiety": "текущий запас калорий", "stamina": "текущая выносливость",
           "building": "это здание", "food": "эта еда", "bed": "эта кровать",
           "item": "этот предмет", "current_job": "текущая работа"},
    "ja": {"health": "現在の健康", "morale": "現在の士気", "immunity": "現在の免疫状態",
           "stress": "現在のストレス", "satiety": "現在のカロリー残量", "stamina": "現在の体力",
           "building": "さっきの建物", "food": "さっきの食べ物", "bed": "さっきのベッド",
           "item": "さっきの物", "current_job": "現在の仕事"},
    "vi": {"health": "sức khỏe hiện tại", "morale": "tinh thần hiện tại",
           "immunity": "miễn dịch hiện tại", "stress": "mức căng thẳng hiện tại",
           "satiety": "lượng calo hiện tại", "stamina": "thể lực hiện tại",
           "building": "công trình vừa nhắc", "food": "món ăn vừa nhắc",
           "bed": "chiếc giường vừa nhắc", "item": "vật phẩm vừa nhắc",
           "current_job": "công việc hiện tại"},
}

LINES = {
    "zh": {
        "query": ["你怎么看{subject}？", "{subject}这方面，你发现了什么？", "能说说{subject}现在的情况吗？", "关于{subject}，你最在意哪一点？", "我们要不要再核对一下{subject}？"],
        "assertion": ["我刚注意到{subject}有些新情况。", "说到{subject}，有一点值得记下来。", "我对{subject}有个明确观察。", "{subject}刚才给了我们一个信号。", "先把{subject}的现状说清楚。"],
        "agreement": ["关于{subject}，我同意你的看法。", "对，{subject}确实和你说的一样。", "这一点我赞成；{subject}值得留意。", "没错，我们对{subject}的判断一致。", "你说服我了，{subject}就按这个结论看。"],
        "disagreement": ["关于{subject}，我有不同看法。", "等等，{subject}可能不是你说的那样。", "这一点我不同意，我们得重看{subject}。", "我理解你的意思，但对{subject}的判断相反。", "先别下结论；{subject}还有另一种解释。"],
        "reflect": ["我一直在想{subject}意味着什么。", "{subject}这件事越想越值得琢磨。", "回头看，{subject}透露了不少信息。", "也许我们该换个角度理解{subject}。", "{subject}让我想到接下来该怎么做。"],
        "appraise_positive": ["{subject}现在的情况挺不错。", "说到{subject}，这次结果让我满意。", "{subject}终于出现了好转。", "我喜欢{subject}目前的状态。", "{subject}这方面值得肯定。"],
        "appraise_neutral": ["{subject}目前算是正常。", "{subject}没有明显好坏变化。", "按现状看，{subject}处在普通水平。", "{subject}现在没什么特别的。", "先记作稳定：{subject}没有偏离常态。"],
        "appraise_negative": ["{subject}现在的情况不太好。", "说到{subject}，这次结果让我不满意。", "{subject}已经出现了需要处理的问题。", "我不喜欢{subject}目前的状态。", "{subject}这方面得尽快改善。"],
    },
    "en": {
        "query": ["What do you think about {subject}?", "What have you noticed about {subject}?", "Can you describe how {subject} stands now?", "What matters most to you about {subject}?", "Should we check {subject} once more?"],
        "assertion": ["I just noticed a change in {subject}.", "There is something worth recording about {subject}.", "I have a clear observation about {subject}.", "{subject} just gave us a useful signal.", "Let me state the situation with {subject} clearly."],
        "agreement": ["I agree with you about {subject}.", "Yes, {subject} is just as you described.", "I agree; {subject} deserves attention.", "Right, our conclusions about {subject} match.", "You convinced me; that reading of {subject} holds."],
        "disagreement": ["I see {subject} differently.", "Wait, {subject} may not be as you described.", "I disagree; we should reassess {subject}.", "I understand you, but I reached the opposite view of {subject}.", "Let's not conclude yet; {subject} has another explanation."],
        "reflect": ["I keep wondering what {subject} means.", "The more I consider {subject}, the more there is to unpack.", "Looking back, {subject} tells us quite a lot.", "Maybe we should understand {subject} from another angle.", "{subject} has me thinking about our next step."],
        "appraise_positive": ["{subject} is looking good right now.", "This result for {subject} satisfies me.", "{subject} has finally improved.", "I like the current state of {subject}.", "{subject} deserves a positive note."],
        "appraise_neutral": ["{subject} is normal for now.", "{subject} shows no strong change either way.", "At present, {subject} sits at an ordinary level.", "There is nothing unusual about {subject} right now.", "Mark {subject} as stable and within the usual range."],
        "appraise_negative": ["{subject} is not looking good right now.", "This result for {subject} disappoints me.", "{subject} now has a problem that needs attention.", "I dislike the current state of {subject}.", "{subject} needs improvement soon."],
    },
    "ko": {
        "query": ["{subject}, 어떻게 생각해?", "{subject}에서 뭘 발견했어?", "{subject}의 지금 상태를 말해 줄래?", "{subject}에서 가장 신경 쓰이는 점은 뭐야?", "{subject}를 한 번 더 확인할까?"],
        "assertion": ["{subject}에 새 변화가 보여.", "{subject}에는 기록할 만한 점이 있어.", "{subject}에 관해 분명히 관찰한 게 있어.", "{subject}에서 방금 신호가 나왔어.", "{subject}의 현황부터 분명히 말할게."],
        "agreement": ["{subject}에 대한 네 말에 동의해.", "그래, {subject}는 네 설명과 같아.", "동의해. {subject}는 주의해서 볼 만해.", "맞아, {subject}에 대한 판단이 같네.", "네 말이 맞아. {subject}는 그렇게 보자."],
        "disagreement": ["{subject}에 대해서는 생각이 달라.", "잠깐, {subject}는 네 설명과 다를 수 있어.", "동의 못 해. {subject}를 다시 보자.", "뜻은 알겠지만 {subject}에 대한 결론은 반대야.", "아직 결론 내리지 마. {subject}에는 다른 설명도 있어."],
        "reflect": ["{subject}가 무슨 뜻인지 계속 생각 중이야.", "{subject}는 생각할수록 따져 볼 게 많아.", "돌이켜 보면 {subject}가 많은 걸 알려 줘.", "{subject}를 다른 각도에서 볼 필요가 있겠어.", "{subject}를 보니 다음 단계가 떠올라."],
        "appraise_positive": ["{subject}의 지금 상태가 좋아.", "{subject}의 이번 결과는 만족스러워.", "{subject}가 드디어 나아졌어.", "{subject}의 현재 상태가 마음에 들어.", "{subject}는 긍정적으로 평가할 만해."],
        "appraise_neutral": ["{subject}는 지금 정상 수준이야.", "{subject}에는 뚜렷한 좋고 나쁨이 없어.", "현재 {subject}는 평범한 수준이야.", "지금 {subject}에는 특별한 점이 없어.", "{subject}는 안정적이고 평소 범위야."],
        "appraise_negative": ["{subject}의 지금 상태가 좋지 않아.", "{subject}의 이번 결과는 실망스러워.", "{subject}에 처리해야 할 문제가 생겼어.", "{subject}의 현재 상태가 마음에 안 들어.", "{subject}는 빨리 개선해야 해."],
    },
    "ru": {
        "query": ["Что ты думаешь про «{subject}»?", "Что ты заметил в теме «{subject}»?", "Опишешь нынешнее состояние: {subject}?", "Что важнее всего в теме «{subject}»?", "Проверим ещё раз: {subject}?"],
        "assertion": ["Я заметил новое изменение: {subject}.", "Стоит записать одно наблюдение: {subject}.", "У меня есть ясное наблюдение по теме «{subject}».", "Мы только что получили сигнал: {subject}.", "Сначала ясно опишу положение: {subject}."],
        "agreement": ["Я согласен с тобой насчёт темы «{subject}».", "Да, всё именно так: {subject}.", "Согласен; за темой «{subject}» стоит следить.", "Верно, наши выводы совпадают: {subject}.", "Ты убедил меня; принимаю этот вывод: {subject}."],
        "disagreement": ["Я иначе смотрю на тему «{subject}».", "Постой, всё может быть иначе: {subject}.", "Не согласен; надо заново оценить: {subject}.", "Я понял тебя, но мой вывод противоположен: {subject}.", "Не будем спешить; у темы «{subject}» есть другое объяснение."],
        "reflect": ["Я всё думаю, что означает тема «{subject}».", "Чем дольше думаю про «{subject}», тем больше вопросов.", "Если оглянуться, тема «{subject}» многое объясняет.", "Может, стоит взглянуть иначе: {subject}.", "Тема «{subject}» заставляет задуматься о следующем шаге."],
        "appraise_positive": ["Сейчас всё выглядит хорошо: {subject}.", "Этот результат меня радует: {subject}.", "Наконец заметно улучшение: {subject}.", "Мне нравится нынешнее состояние: {subject}.", "Здесь есть за что похвалить: {subject}."],
        "appraise_neutral": ["Пока всё в норме: {subject}.", "Нет явного изменения в любую сторону: {subject}.", "Сейчас это обычный уровень: {subject}.", "Пока ничего особенного: {subject}.", "Отметим стабильность в обычном диапазоне: {subject}."],
        "appraise_negative": ["Сейчас всё выглядит плохо: {subject}.", "Этот результат меня разочаровывает: {subject}.", "Появилась проблема, требующая внимания: {subject}.", "Мне не нравится нынешнее состояние: {subject}.", "Это нужно скорее улучшить: {subject}."],
    },
    "ja": {
        "query": ["{subject}について、どう思う？", "{subject}で何か気づいた？", "{subject}の今の状態を教えてくれる？", "{subject}で一番気になる点は何？", "{subject}をもう一度確かめようか？"],
        "assertion": ["{subject}に新しい変化があった。", "{subject}には記録する価値のある点がある。", "{subject}について、はっきりした観察がある。", "{subject}から今、信号が出た。", "まず{subject}の現状を明確にするよ。"],
        "agreement": ["{subject}については同意するよ。", "うん、{subject}は説明どおりだ。", "賛成だ。{subject}は注目する価値がある。", "その通り。{subject}についての結論は同じだ。", "納得した。{subject}はその見方で合っている。"],
        "disagreement": ["{subject}については違う考えだ。", "待って。{subject}は説明と違うかもしれない。", "同意できない。{subject}を見直そう。", "言いたいことは分かるけど、{subject}への結論は逆だ。", "まだ決めないで。{subject}には別の説明もある。"],
        "reflect": ["{subject}が何を意味するのか考え続けている。", "{subject}は考えるほど掘り下げる点が増える。", "振り返ると、{subject}はいろいろ教えてくれる。", "{subject}を別の角度から理解すべきかもしれない。", "{subject}を見ると次の手を考えたくなる。"],
        "appraise_positive": ["{subject}は今、いい状態だ。", "{subject}の今回の結果には満足している。", "{subject}がようやく良くなった。", "{subject}の今の状態が気に入った。", "{subject}は良い評価に値する。"],
        "appraise_neutral": ["{subject}は今のところ正常だ。", "{subject}には良くも悪くも大きな変化がない。", "現在の{subject}は普通の水準だ。", "今の{subject}に特別な点はない。", "{subject}は安定し、通常範囲にある。"],
        "appraise_negative": ["{subject}は今、よくない状態だ。", "{subject}の今回の結果には不満がある。", "{subject}に対処が必要な問題が出た。", "{subject}の今の状態は気に入らない。", "{subject}は早めに改善が必要だ。"],
    },
    "vi": {
        "query": ["Bạn nghĩ gì về {subject}?", "Bạn nhận thấy gì ở {subject}?", "Bạn mô tả tình trạng của {subject} được không?", "Điều gì ở {subject} khiến bạn quan tâm nhất?", "Ta kiểm tra lại {subject} nhé?"],
        "assertion": ["Tôi vừa nhận thấy thay đổi ở {subject}.", "Có một điểm đáng ghi lại về {subject}.", "Tôi có một quan sát rõ ràng về {subject}.", "{subject} vừa cho ta một tín hiệu hữu ích.", "Để tôi nói rõ tình hình của {subject}."],
        "agreement": ["Tôi đồng ý với bạn về {subject}.", "Đúng, {subject} y như bạn mô tả.", "Tôi đồng ý; {subject} đáng được chú ý.", "Phải, kết luận của ta về {subject} giống nhau.", "Bạn thuyết phục được tôi; cách hiểu đó về {subject} hợp lý."],
        "disagreement": ["Tôi nhìn {subject} theo cách khác.", "Khoan, {subject} có thể không như bạn nói.", "Tôi không đồng ý; ta nên đánh giá lại {subject}.", "Tôi hiểu ý bạn, nhưng kết luận của tôi về {subject} ngược lại.", "Đừng kết luận vội; {subject} còn một cách giải thích khác."],
        "reflect": ["Tôi cứ nghĩ mãi {subject} có ý nghĩa gì.", "Càng nghĩ về {subject}, tôi càng thấy nhiều điều cần xét.", "Nhìn lại, {subject} cho ta biết khá nhiều.", "Có lẽ ta nên hiểu {subject} từ góc khác.", "{subject} khiến tôi nghĩ đến bước tiếp theo."],
        "appraise_positive": ["{subject} hiện đang ở tình trạng tốt.", "Kết quả này của {subject} làm tôi hài lòng.", "{subject} cuối cùng đã tốt lên.", "Tôi thích trạng thái hiện tại của {subject}.", "{subject} xứng đáng được đánh giá tích cực."],
        "appraise_neutral": ["{subject} hiện vẫn bình thường.", "{subject} không thay đổi rõ theo hướng tốt hay xấu.", "Hiện tại, {subject} ở mức thông thường.", "Lúc này {subject} không có gì đặc biệt.", "Ghi nhận {subject} ổn định trong phạm vi thường."],
        "appraise_negative": ["{subject} hiện không ở tình trạng tốt.", "Kết quả này của {subject} làm tôi thất vọng.", "{subject} đã có vấn đề cần xử lý.", "Tôi không thích trạng thái hiện tại của {subject}.", "{subject} cần sớm được cải thiện."],
    },
}

LISTENERS = {
    "zh": ["我听见了，我们按这个线索继续。", "明白，我会把这点记住。", "好，我们先核对证据再行动。", "我在听；这件事值得认真处理。", "收到，我们一步一步来。"],
    "en": ["I hear you; we'll follow that lead.", "Understood; I'll remember that point.", "All right, we'll check the evidence before acting.", "I'm listening; this deserves proper attention.", "Got it; we'll take it one step at a time."],
    "ko": ["들었어. 그 단서를 따라가자.", "알겠어. 그 점을 기억할게.", "좋아. 행동하기 전에 근거부터 확인하자.", "듣고 있어. 제대로 살펴볼 일이야.", "확인했어. 한 단계씩 하자."],
    "ru": ["Я услышал; пойдём по этой подсказке.", "Понятно; я запомню этот момент.", "Хорошо, сначала проверим факты.", "Я слушаю; это заслуживает внимания.", "Принято; будем действовать по шагам."],
    "ja": ["聞いたよ。その手がかりを追おう。", "分かった。その点を覚えておく。", "よし、動く前に根拠を確かめよう。", "聞いているよ。きちんと扱うべきことだ。", "了解。一段ずつ進めよう。"],
    "vi": ["Tôi nghe rồi; ta sẽ theo đầu mối đó.", "Hiểu; tôi sẽ nhớ điểm này.", "Được, ta kiểm tra bằng chứng trước khi hành động.", "Tôi đang nghe; việc này đáng được xem xét nghiêm túc.", "Rõ rồi; ta làm từng bước một."],
}


def metadata(topic: str) -> tuple[str, str, str, str]:
    if topic.startswith("current_job."):
        kind, domain, suffix = "current_job", "current_job", topic.removeprefix("current_job.")
    else:
        family, domain, suffix = topic.split(".", 2)
        kind = "amount_state" if family == "amount" else "recent_thing"
    mode, appraisal = MODE[suffix]
    return kind, domain, mode, appraisal


def build(locale: str) -> dict:
    candidates = []
    for offset, topic in enumerate(TOPICS):
        kind, domain, mode, appraisal = metadata(topic)
        suffix = topic.split(".", 2)[-1] if not topic.startswith("current_job.") else "query"
        subject = SUBJECTS[locale][domain]
        for angle, template in enumerate(LINES[locale][suffix], 1):
            candidate_id = f"topic-fallback.{topic.replace('_', '-')}.angle-{angle}"
            candidates.append({
                "candidateId": candidate_id,
                "diversityKey": candidate_id,
                "storyletId": "Casual",
                "contractRevision": 1,
                "status": "reviewed",
                "selection": {
                    "resolvedTopics": [topic], "conversationKinds": [kind],
                    "topicDomains": [domain], "utteranceModes": [mode],
                    "appraisals": [appraisal],
                },
                "weight": 1,
                "ordinal": 20_000 + offset * 5 + angle,
                "turns": [
                    {"turnId": "speaker", "speakerSlot": 0,
                     "text": template.format(subject=subject)},
                    {"turnId": "listener", "speakerSlot": 1,
                     "text": LISTENERS[locale][angle - 1]},
                ],
            })
    return {"locale": locale, "family": "casual-topic-fallback-pack",
            "candidates": candidates}


def content_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def update_provenance(locale: str, check: bool) -> None:
    relative = "dialogue/topic-fallback.json"
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
            raise SystemExit(f"Topic fallback provenance is stale: {path}")
    else:
        path.write_text(rendered, encoding="utf-8")


def generate(locales: list[str], check: bool) -> None:
    for locale in sorted(locales, key=lambda value: value != "zh"):
        target = ROOT / "locales" / locale / "dialogue" / "topic-fallback.json"
        rendered = json.dumps(build(locale), ensure_ascii=False, indent=2) + "\n"
        if check:
            if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"generated Topic fallback pack is stale: {target}")
        else:
            target.write_text(rendered, encoding="utf-8")
    for locale in TARGET_LOCALES:
        if locale in locales:
            update_provenance(locale, check)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", choices=[*LOCALES, "all"], default="all")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    locales = LOCALES if args.locale == "all" else [args.locale]
    generate(locales, args.check)
    print(f"Topic fallback pack {'clean' if args.check else 'written'}: "
          f"{len(build(locales[0])['candidates'])} candidates × {len(locales)} locale(s)")


if __name__ == "__main__":
    main()
