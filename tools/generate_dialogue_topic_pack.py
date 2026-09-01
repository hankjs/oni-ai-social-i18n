#!/usr/bin/env python3
"""Generate the reviewed six-locale Topic matrix from authored phrase banks.

The phrase banks are combined only at build time. Runtime files contain complete,
materialized turns and identical candidate/selection metadata in every locale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ["zh", "en", "ko", "ru", "ja", "vi"]
TARGET_LOCALES = LOCALES[1:]
PERSONALITIES = [
    "hothead", "crybaby", "loud", "eater", "nervous", "jumpy", "gentle",
    "curious", "slow", "early", "night", "sleepy", "athlete",
]
MOODS = ["buoyant", "settled", "discouraged", "strained", "overwhelmed"]
TOPICS = {
    "amount.satiety.appraise_negative": ("amount_state", "satiety", "dissatisfaction", "negative"),
    "amount.stamina.appraise_negative": ("amount_state", "stamina", "dissatisfaction", "negative"),
    "amount.stress.appraise_stressed": ("amount_state", "stress", "stressing", "stressed"),
    "amount.morale.appraise_negative": ("amount_state", "morale", "dissatisfaction", "negative"),
    "amount.health.appraise_negative": ("amount_state", "health", "dissatisfaction", "negative"),
    "current_job.appraise_stressed": ("current_job", "current_job", "stressing", "stressed"),
}


TEXT = {
    "zh": {
        "personality": {
            "hothead": "我直说，", "crybaby": "我不想哭，可是", "loud": "大家听我说！",
            "eater": "我一直在留意补给，", "nervous": "我有点担心，", "jumpy": "先别突然靠近；",
            "gentle": "慢慢说，", "curious": "我想把原因弄清楚：", "slow": "不急，我慢慢讲，",
            "early": "趁班次还早，", "night": "夜班让我看得很清楚：", "sleepy": "我可能说得有点迷糊，",
            "athlete": "从体力分配看，",
        },
        "mood": {
            "buoyant": ("心情还不错，可这项信号不能忽略：", "还来得及处理。"),
            "settled": ("先按事实说，", "按正常步骤处理就好。"),
            "discouraged": ("本来就提不起劲，现在", "别一个人闷着，我们先解决眼前这件事。"),
            "strained": ("我已经绷得很紧，而且", "先把负担降下来，别再硬撑。"),
            "overwhelmed": ("事情全挤在一起，我连这点都快扛不住了：", "先停下，我陪你处理最急的一项。"),
        },
        "topics": {
            "amount.satiety.appraise_negative": (["胃里的空响已经盖过机器声了。", "得先找点能补充卡路里的东西。", "今天的配餐量恐怕撑不到下一班。", "再这么耗下去，手脚都会慢下来。", "你那边还有没分配的口粮吗？"], ["我也听见了，先确认你的卡路里储备。", "走，先补充热量，别拿意志力硬顶。", "我帮你查配额；这是吃不够，不是挑食。", "先暂停高强度工作，低卡路里会拖慢动作。", "有一份备用的，我们按配额分，不碰紧急储备。"]),
            "amount.stamina.appraise_negative": (["手臂和眼皮都开始发沉了。", "体力量表掉得比我预想的快。", "这班还没结束，我的动作已经慢了半拍。", "我需要短暂停一下，不然下一步容易出错。", "能和我换一段轻一点的工作吗？"], ["我看出来了，这是疲劳信号，不是对床铺的评价。", "先降下节奏，体力恢复后再接重活。", "我来接这一段，你先缓一缓。", "可以，先休息和补氧，别在疲劳时操作机器。", "我们换班，我守着进度，不让任务漏掉。"]),
            "amount.stress.appraise_stressed": (["压力读数一直往红区爬。", "噪声和待办一起挤进脑子里了。", "每个任务都像在同时催我。", "我得先慢下来，不然会把小问题弄大。", "能帮我重排一下眼前的优先级吗？"], ["我看见读数了，先离开刺激源。", "我们找个安静处，一次只处理一件事。", "先把非紧急任务撤掉，别让清单围住你。", "好，呼吸放慢；暂停不是失败。", "我来排：安全第一，其余往后放。"]),
            "amount.morale.appraise_negative": (["生活质量的缺口开始磨掉我的耐心。", "每天只有工作，恢复感远远不够。", "休息和娱乐的需求都没被满足。", "这不是一件装饰品就能掩盖的问题。", "能一起看看哪项生活需求一直落空吗？"], ["明白，这是整体士气，不只是一格装饰度。", "我们给休息留出真实时间。", "我帮你核对日程和娱乐条件。", "对，先找持续缺口，不拿摆设充答案。", "可以，从食物、休息、娱乐和环境逐项查。"]),
            "amount.health.appraise_negative": (["生命值下降后，伤处一直在提醒我。", "这次损伤不像能靠硬撑过去。", "动作一大，伤口就又疼起来。", "我需要一次正式的医疗检查。", "能先替我接手危险工位吗？"], ["先看伤势和生命值，别继续冒险。", "我陪你去医疗站，别赌它自己好。", "减少活动，我来拿急救物资。", "好，现在登记检查，不把疼痛当小事。", "我来接手，你先离开危险区域。"]),
            "current_job.appraise_stressed": (["这个岗位的要求已经超过我能稳妥处理的量。", "任务优先级互相打架，我不知道先听谁的。", "我刚接下角色，却没有完成它需要的时间。", "再塞一项工作，我会漏掉关键步骤。", "能重新分配这一班的职责吗？"], ["先明确岗位边界，别让所有任务都落到你身上。", "我们按安全和时限重排，不靠嗓门决定。", "我帮你保护完成核心职责的时间。", "那就冻结新任务，先收尾当前步骤。", "可以，我接走一项，并把变更写进排班。"]),
        },
    },
    "en": {
        "personality": {"hothead": "I'll say it straight:", "crybaby": "I'm trying not to tear up, but", "loud": "Everyone, listen up!", "eater": "I've been watching our supplies, and", "nervous": "I'm a little worried:", "jumpy": "Don't sneak up on me—", "gentle": "Let me put this gently:", "curious": "I want to understand the cause:", "slow": "No rush; let me explain.", "early": "While the shift is still young,", "night": "Night shift makes this obvious:", "sleepy": "I may sound foggy, but", "athlete": "Looking at how I'm spending energy,"},
        "mood": {"buoyant": ("I'm in good spirits, yet this signal matters:", "We still have time to handle it."), "settled": ("Sticking to the facts,", "We'll follow the normal steps."), "discouraged": ("I was already running low, and now", "Don't sit with it alone; we'll handle the immediate issue."), "strained": ("I'm stretched tight, and", "Let's reduce the load before you push any harder."), "overwhelmed": ("Everything has piled up, and I can barely carry this too:", "Stop for a moment; I'll help with the most urgent part.")},
        "topics": {
            "amount.satiety.appraise_negative": (["my empty stomach is louder than the machinery.", "I need something that restores calories.", "today's meal allowance will not last through the next shift.", "if I keep burning energy, my hands will slow down.", "is there any unassigned ration left?"], ["I hear it too; let's check your calorie reserve.", "Come on, refuel instead of forcing yourself through it.", "I'll check the allowance; this is too little food, not fussiness.", "Pause the heavy work; low calories will slow your movements.", "There is a spare portion; we'll divide it without touching emergency stock."]),
            "amount.stamina.appraise_negative": (["my arms and eyelids are getting heavy.", "my stamina gauge fell faster than expected.", "the shift is not over, but I'm already half a beat slow.", "I need a short pause before the next step becomes a mistake.", "can you trade me for a lighter stretch of work?"], ["I can see it; that is fatigue, not a verdict on your bed.", "Lower the pace and return to heavy work after you recover.", "I'll take this section while you catch your breath.", "Yes; rest and get oxygen before operating machinery.", "We'll swap; I'll guard the schedule so nothing is missed."]),
            "amount.stress.appraise_stressed": (["my stress reading keeps climbing toward the red.", "the noise and task list are crowding my head.", "every assignment feels like it is calling at once.", "I need to slow down before a small problem becomes a large one.", "can you help reorder what matters right now?"], ["I see the reading; first step away from the stimulus.", "Let's find a quiet spot and handle one thing at a time.", "We'll remove nonurgent work so the list stops surrounding you.", "Good; slow your breathing—pausing is not failure.", "I'll sort it: safety first, everything else later."]),
            "amount.morale.appraise_negative": (["the gaps in my quality of life are wearing down my patience.", "each day is all work with nowhere near enough recovery.", "my needs for rest and recreation are going unmet.", "one decorative object cannot cover this problem.", "can we find which daily need keeps being missed?"], ["Understood; this is overall morale, not one decor score.", "We'll reserve real time for recovery.", "I'll help check the schedule and recreation access.", "Right; we'll find the lasting gap instead of offering an ornament.", "Yes; we'll review food, rest, recreation, and surroundings in turn."]),
            "amount.health.appraise_negative": (["the injury keeps reminding me that my health dropped.", "this damage does not feel like something I can push through.", "the wound hurts again whenever I make a large movement.", "I need a proper medical examination.", "can you cover the hazardous station for me?"], ["Let's check the injury and health level before you take another risk.", "I'll walk you to the medical station; don't gamble on it healing alone.", "Limit movement; I'll fetch first-aid supplies.", "Yes, we'll register an examination now and take the pain seriously.", "I'll cover it; you leave the hazardous area first."]),
            "current_job.appraise_stressed": (["this role is demanding more than I can handle safely.", "the task priorities conflict, and I do not know which order to obey.", "I accepted the role without enough time for its core work.", "one more assignment will make me miss a critical step.", "can we redistribute this shift's responsibilities?"], ["Let's define the role boundary so every task does not land on you.", "We'll order work by safety and deadline, not by who shouts loudest.", "I'll protect time for your core responsibility.", "Then freeze new tasks and finish the current step first.", "Yes; I'll take one duty and record the change in the schedule."]),
        },
    },
    "ko": {
        "personality": {"hothead": "솔직히 말할게.", "crybaby": "울고 싶진 않지만,", "loud": "다들 잘 들어!", "eater": "보급량을 계속 살펴봤는데,", "nervous": "조금 걱정돼.", "jumpy": "갑자기 다가오진 마.", "gentle": "천천히 말해 볼게.", "curious": "원인을 정확히 알고 싶어.", "slow": "서두르지 말고 설명할게.", "early": "교대가 아직 이른 지금,", "night": "야간 근무를 하니 분명히 보이네.", "sleepy": "조금 멍하게 들릴 수 있지만,", "athlete": "체력 배분으로 보면,"},
        "mood": {"buoyant": ("기분은 괜찮지만 이 신호는 무시 못 해.", "아직 처리할 시간은 있어."), "settled": ("사실대로 말하면,", "정상 절차대로 해결하자."), "discouraged": ("원래도 힘이 빠져 있었는데 이제", "혼자 참지 마. 당장 문제부터 같이 풀자."), "strained": ("이미 팽팽하게 긴장했는데", "더 버티기 전에 부담부터 줄이자."), "overwhelmed": ("모든 일이 한꺼번에 몰려 이것까지 감당하기 어려워.", "잠깐 멈춰. 가장 급한 것부터 내가 도울게.")},
        "topics": {
            "amount.satiety.appraise_negative": (["빈속 소리가 기계음보다 크게 들려.", "칼로리를 채울 음식이 먼저 필요해.", "오늘 배식량으로는 다음 교대까지 못 버티겠어.", "계속 소모하면 손발이 느려질 거야.", "아직 배정하지 않은 식량이 남았어?"], ["나도 들었어. 칼로리 잔량부터 확인하자.", "의지로 버티지 말고 먼저 열량을 보충하자.", "배급을 확인할게. 입맛 문제가 아니라 양이 부족한 거야.", "고강도 작업을 멈춰. 낮은 칼로리는 동작을 늦춰.", "예비 한 끼가 있어. 비상 식량은 건드리지 말고 나누자."]),
            "amount.stamina.appraise_negative": (["팔과 눈꺼풀이 무거워지고 있어.", "체력 수치가 예상보다 빨리 떨어졌어.", "교대는 안 끝났는데 동작이 벌써 반 박자 느려.", "다음 단계에서 실수하기 전에 잠깐 쉬어야 해.", "조금 가벼운 작업과 바꿔 줄래?"], ["보여. 침대 평가가 아니라 피로 신호야.", "속도를 낮추고 회복한 뒤 힘든 일을 하자.", "이 구간은 내가 맡을 테니 숨을 돌려.", "그래. 기계를 다루기 전에 쉬고 산소도 보충해.", "교대하자. 일정은 내가 지켜서 빠지는 일이 없게 할게."]),
            "amount.stress.appraise_stressed": (["스트레스 수치가 계속 위험 구간으로 올라가.", "소음과 할 일 목록이 머릿속을 꽉 채웠어.", "모든 임무가 동시에 재촉하는 것 같아.", "작은 문제를 키우기 전에 속도를 늦춰야 해.", "지금 우선순위를 다시 정해 줄래?"], ["수치가 보여. 먼저 자극에서 벗어나자.", "조용한 곳에서 한 번에 하나씩 처리하자.", "급하지 않은 일은 빼서 목록의 압박을 줄이자.", "좋아. 호흡을 늦춰. 멈추는 건 실패가 아니야.", "내가 정리할게. 안전이 먼저고 나머지는 뒤야."]),
            "amount.morale.appraise_negative": (["생활의 질이 부족해 인내심까지 닳고 있어.", "매일 일뿐이고 회복할 여유가 너무 적어.", "휴식과 오락 욕구가 계속 충족되지 않아.", "장식 하나로 가릴 수 있는 문제가 아니야.", "어떤 생활 욕구가 계속 빠지는지 같이 볼래?"], ["알겠어. 장식 수치 하나가 아니라 전체 사기 문제야.", "실제로 회복할 시간을 일정에 넣자.", "일정과 오락 시설 이용을 같이 확인할게.", "맞아. 장식품으로 때우지 말고 지속되는 결핍을 찾자.", "좋아. 음식, 휴식, 오락, 환경을 차례로 살펴보자."]),
            "amount.health.appraise_negative": (["체력이 떨어진 뒤 상처가 계속 신호를 보내.", "이번 손상은 참고 넘길 수준이 아닌 것 같아.", "크게 움직일 때마다 상처가 다시 아파.", "정식 의료 검사가 필요해.", "위험한 작업대를 잠시 맡아 줄래?"], ["더 위험해지기 전에 상처와 체력부터 확인하자.", "의료실까지 같이 갈게. 저절로 낫길 기대하지 마.", "움직임을 줄여. 내가 응급 물품을 가져올게.", "좋아. 지금 검사 등록하고 통증을 가볍게 보지 말자.", "내가 맡을게. 너는 위험 구역부터 벗어나."]),
            "current_job.appraise_stressed": (["이 역할은 내가 안전하게 감당할 양을 넘었어.", "작업 우선순위가 충돌해서 무엇부터 해야 할지 모르겠어.", "역할은 맡았지만 핵심 업무를 끝낼 시간이 없어.", "일이 하나 더 오면 중요한 단계를 놓칠 거야.", "이번 교대의 책임을 다시 나눌 수 있을까?"], ["역할 경계를 정해서 모든 일이 네게 몰리지 않게 하자.", "목소리 크기가 아니라 안전과 기한 순으로 정하자.", "핵심 책임을 끝낼 시간을 내가 지켜 줄게.", "그럼 새 작업을 멈추고 현재 단계부터 마쳐.", "좋아. 내가 하나 맡고 변경 사항을 일정에 기록할게."]),
        },
    },
    "ru": {
        "personality": {"hothead": "Скажу прямо:", "crybaby": "Не хочу плакать, но", "loud": "Все меня слушайте!", "eater": "Я слежу за запасами, и", "nervous": "Я немного тревожусь:", "jumpy": "Только не подкрадывайся —", "gentle": "Скажу спокойно:", "curious": "Хочу понять причину:", "slow": "Не спешу, объясню по порядку.", "early": "Пока смена только началась,", "night": "В ночную смену особенно ясно:", "sleepy": "Я могу говорить сонно, но", "athlete": "Если смотреть на расход сил,"},
        "mood": {"buoyant": ("Настроение хорошее, но этот сигнал важен:", "Мы ещё успеем всё исправить."), "settled": ("Если говорить по фактам,", "Действуем по обычному порядку."), "discouraged": ("Сил и так было мало, а теперь", "Не оставайся с этим один; начнём с ближайшей проблемы."), "strained": ("Я уже на пределе, и", "Сначала уменьшим нагрузку, не надо терпеть дальше."), "overwhelmed": ("Всё навалилось сразу, и это я уже едва выдерживаю:", "Остановись; я помогу с самым срочным.")},
        "topics": {
            "amount.satiety.appraise_negative": (["урчание в пустом животе громче машин.", "сначала нужна еда, которая восстановит калории.", "сегодняшней порции не хватит до следующей смены.", "если продолжу тратить энергию, движения замедлятся.", "остался нераспределённый паёк?"], ["Я тоже слышу; проверим запас калорий.", "Сначала подкрепись, не пытайся выехать на одной воле.", "Проверю норму: еды мало, дело не в капризах.", "Приостанови тяжёлую работу; нехватка калорий замедляет движения.", "Есть запасная порция; разделим её, не трогая аварийный резерв."]),
            "amount.stamina.appraise_negative": (["руки и веки становятся тяжёлыми.", "запас сил упал быстрее, чем я ожидал.", "смена не закончилась, а движения уже запаздывают.", "нужна короткая пауза, иначе следующий шаг станет ошибкой.", "поменяешься со мной на более лёгкий участок?"], ["Это видно: сигнал усталости, а не оценка кровати.", "Снизь темп и возвращайся к тяжёлой работе после восстановления.", "Я возьму этот участок, а ты переведи дух.", "Да; отдохни и восстанови кислород перед работой с машиной.", "Поменяемся; я прослежу, чтобы график не пострадал."]),
            "amount.stress.appraise_stressed": (["уровень стресса всё ближе к красной зоне.", "шум и список дел забили всю голову.", "кажется, каждое задание требует меня одновременно.", "надо замедлиться, пока малая проблема не стала большой.", "поможешь заново расставить приоритеты?"], ["Вижу показатель; сначала уйдём от раздражителя.", "Найдём тихое место и будем делать по одному делу.", "Снимем несрочные задачи, чтобы список перестал давить.", "Хорошо; дыши медленнее — пауза не означает поражение.", "Я расставлю: сначала безопасность, остальное потом."]),
            "amount.morale.appraise_negative": (["пробелы в качестве жизни уже подтачивают терпение.", "каждый день состоит из работы, а восстановления почти нет.", "потребности в отдыхе и развлечениях не удовлетворены.", "одним украшением эту проблему не скрыть.", "проверим, какая ежедневная потребность постоянно выпадает?"], ["Понимаю: речь об общем духе, а не об одном показателе декора.", "Выделим настоящее время на восстановление.", "Я помогу проверить расписание и доступ к развлечениям.", "Верно; найдём постоянный дефицит, а не предложим безделушку.", "Давай по очереди проверим еду, отдых, досуг и окружение."]),
            "amount.health.appraise_negative": (["после падения здоровья рана всё время напоминает о себе.", "эту травму не получится просто перетерпеть.", "при каждом резком движении рана снова болит.", "мне нужен полноценный медицинский осмотр.", "подменишь меня на опасном участке?"], ["Сначала проверим рану и здоровье, не рискуй снова.", "Я провожу тебя в медпункт; не надейся, что пройдёт само.", "Меньше двигайся, я принесу средства первой помощи.", "Да, запишем тебя на осмотр прямо сейчас и не станем терпеть боль.", "Я подменю; ты сначала уйди из опасной зоны."]),
            "current_job.appraise_stressed": (["эта роль требует больше, чем я могу безопасно выполнить.", "приоритеты конфликтуют, и непонятно, за что браться первым.", "роль уже назначена, но на основную работу времени нет.", "ещё одно задание — и я пропущу важный шаг.", "можем перераспределить обязанности этой смены?"], ["Определим границы роли, чтобы все задачи не падали на тебя.", "Расставим по безопасности и срокам, а не по громкости требований.", "Я помогу сохранить время для основной обязанности.", "Тогда не берём новые задачи и завершаем текущий этап.", "Да; я возьму одну обязанность и отмечу замену в графике."]),
        },
    },
    "ja": {
        "personality": {"hothead": "はっきり言うよ。", "crybaby": "泣きたくはないけど、", "loud": "みんな、聞いて！", "eater": "補給をずっと見ていたけど、", "nervous": "少し心配なんだ。", "jumpy": "急に近づかないでね。", "gentle": "落ち着いて話すね。", "curious": "原因をきちんと知りたい。", "slow": "急がず、順番に話すよ。", "early": "シフトが始まったばかりのうちに、", "night": "夜勤だとはっきり分かる。", "sleepy": "少しぼんやりした言い方になるけど、", "athlete": "体力の配分から見ると、"},
        "mood": {"buoyant": ("気分はいいけど、この信号は無視できない。", "まだ対処する時間はあるよ。"), "settled": ("事実に沿って言うと、", "いつもの手順で対処しよう。"), "discouraged": ("もともと元気が出ないところに、", "一人で抱えないで。まず目の前の問題を片づけよう。"), "strained": ("もう張り詰めているのに、", "これ以上無理をせず、先に負担を減らそう。"), "overwhelmed": ("全部が重なって、これまで抱えるのはもう難しい。", "いったん止まって。一番急ぐことを手伝うよ。")},
        "topics": {
            "amount.satiety.appraise_negative": (["空腹の音が機械音より大きく聞こえる。", "まずカロリーを補える食べ物が必要だ。", "今日の配給量では次のシフトまでもたない。", "このまま消耗すると手足の動きが鈍る。", "まだ割り当てられていない食料はある？"], ["私にも聞こえた。まずカロリー残量を確認しよう。", "気力だけで耐えず、先にエネルギーを補おう。", "配給を調べるよ。好き嫌いではなく量の不足だ。", "重作業を止めよう。低カロリーでは動きが遅くなる。", "予備が一食ある。非常食には触れず分けよう。"]),
            "amount.stamina.appraise_negative": (["腕とまぶたが重くなってきた。", "体力ゲージが予想より速く落ちている。", "シフトは途中なのに、もう動きが半拍遅い。", "次の手順で失敗する前に少し休みたい。", "しばらく軽い作業と交代してくれる？"], ["分かるよ。ベッドの評価ではなく疲労の信号だ。", "ペースを落とし、回復してから重作業に戻ろう。", "ここは私が引き受けるから、ひと息ついて。", "うん。機械を扱う前に休息と酸素を取ろう。", "交代しよう。予定に抜けが出ないよう私が見ておく。"]),
            "amount.stress.appraise_stressed": (["ストレス値が危険域へ上がり続けている。", "騒音と作業一覧で頭がいっぱいだ。", "全ての仕事が同時に急かしてくる。", "小さな問題を大きくする前に速度を落としたい。", "今の優先順位を組み直してくれる？"], ["数値を見たよ。まず刺激源から離れよう。", "静かな所で一つずつ片づけよう。", "急がない仕事を外し、一覧の圧力を減らそう。", "そうしよう。呼吸を遅くして。止まることは失敗じゃない。", "私が並べる。安全を最優先にして、残りは後だ。"]),
            "amount.morale.appraise_negative": (["生活の質の不足で、我慢する力まで削られている。", "毎日仕事ばかりで、回復する余裕が足りない。", "休息と娯楽の欲求が満たされていない。", "飾りを一つ置いて隠せる問題ではない。", "どの生活上の必要が欠け続けているか一緒に見ない？"], ["分かった。装飾値一つではなく全体の士気の話だ。", "本当に回復できる時間を予定に入れよう。", "日程と娯楽設備を一緒に確認するよ。", "そうだね。置物で済ませず、続いている不足を探そう。", "食事、休息、娯楽、環境を順番に調べよう。"]),
            "amount.health.appraise_negative": (["体力が落ちてから、傷がずっと痛む。", "今回の負傷は我慢だけで越えられそうにない。", "大きく動くたびに傷がまた痛む。", "きちんと医療検査を受けたい。", "危険な持ち場を代わってくれる？"], ["次の危険を冒す前に、傷と体力を確認しよう。", "医務室まで付き添うよ。自然に治る方へ賭けないで。", "動きを減らして。救急用品を取ってくる。", "うん。今すぐ検査を登録して、痛みを軽く扱わないようにしよう。", "私が代わる。まず危険区域から離れて。"]),
            "current_job.appraise_stressed": (["この役割は、安全にこなせる量を超えている。", "作業の優先順位が衝突して、何から従えばいいか分からない。", "役割を引き受けたのに、中核作業を終える時間がない。", "もう一件増えたら重要な手順を落としてしまう。", "このシフトの担当を分け直せる？"], ["役割の境界を決め、全てが君に集まらないようにしよう。", "声の大きさではなく、安全と期限で並べよう。", "中核の責任を終える時間を私が守るよ。", "では新しい作業を止め、今の手順を先に終えよう。", "いいよ。一件引き受けて、変更を予定表に記録する。"]),
        },
    },
    "vi": {
        "personality": {"hothead": "Tôi nói thẳng nhé:", "crybaby": "Tôi không muốn khóc, nhưng", "loud": "Mọi người nghe đây!", "eater": "Tôi vẫn theo dõi nguồn tiếp tế, và", "nervous": "Tôi hơi lo:", "jumpy": "Đừng bất ngờ tiến lại gần—", "gentle": "Để tôi nói nhẹ nhàng:", "curious": "Tôi muốn hiểu rõ nguyên nhân:", "slow": "Không cần vội, để tôi nói từng bước.", "early": "Khi ca làm còn mới bắt đầu,", "night": "Ca đêm khiến điều này rất rõ:", "sleepy": "Có thể tôi nói hơi lơ mơ, nhưng", "athlete": "Xét theo cách phân phối thể lực,"},
        "mood": {"buoyant": ("Tinh thần tôi vẫn tốt, nhưng tín hiệu này đáng chú ý:", "Ta vẫn còn thời gian xử lý."), "settled": ("Nếu chỉ nói theo sự thật,", "Ta cứ làm theo quy trình bình thường."), "discouraged": ("Tôi vốn đã xuống tinh thần, giờ lại", "Đừng chịu một mình; ta giải quyết việc trước mắt trước."), "strained": ("Tôi đã căng như dây đàn, lại còn", "Hãy giảm tải trước khi cố thêm."), "overwhelmed": ("Mọi thứ dồn cùng lúc, tôi gần như không gánh nổi cả việc này:", "Dừng lại một chút; tôi sẽ giúp phần khẩn cấp nhất.")},
        "topics": {
            "amount.satiety.appraise_negative": (["bụng rỗng kêu còn to hơn tiếng máy.", "tôi cần thức ăn bổ sung calo trước.", "khẩu phần hôm nay không đủ đến ca sau.", "nếu tiếp tục tiêu hao, tay chân tôi sẽ chậm lại.", "còn phần lương thực nào chưa phân không?"], ["Tôi cũng nghe thấy; hãy kiểm tra lượng calo dự trữ.", "Đi bổ sung năng lượng trước, đừng chỉ cố bằng ý chí.", "Tôi sẽ kiểm tra khẩu phần; đây là thiếu thức ăn, không phải kén ăn.", "Tạm dừng việc nặng; thiếu calo sẽ làm động tác chậm đi.", "Còn một phần dự phòng; ta chia nó mà không đụng kho khẩn cấp."]),
            "amount.stamina.appraise_negative": (["tay và mí mắt tôi bắt đầu nặng trĩu.", "thể lực tụt nhanh hơn tôi dự tính.", "ca chưa hết mà động tác của tôi đã chậm nửa nhịp.", "tôi cần nghỉ ngắn trước khi bước tiếp theo thành sai sót.", "bạn đổi cho tôi một đoạn việc nhẹ hơn được không?"], ["Tôi thấy rồi; đó là dấu hiệu mệt mỏi, không phải đánh giá chiếc giường.", "Hạ nhịp độ và chỉ làm việc nặng sau khi hồi phục.", "Để tôi nhận đoạn này, bạn nghỉ lấy hơi đi.", "Được; hãy nghỉ và lấy đủ ôxy trước khi vận hành máy.", "Ta đổi ca; tôi sẽ giữ tiến độ để không sót việc."]),
            "amount.stress.appraise_stressed": (["chỉ số căng thẳng cứ tiến về vùng đỏ.", "tiếng ồn và danh sách việc đang chen kín đầu tôi.", "mọi nhiệm vụ như cùng lúc thúc giục tôi.", "tôi phải chậm lại trước khi vấn đề nhỏ thành lớn.", "bạn giúp tôi sắp lại ưu tiên trước mắt nhé?"], ["Tôi thấy chỉ số rồi; trước hết hãy rời nguồn kích thích.", "Ta tìm chỗ yên và xử lý từng việc một.", "Bỏ việc chưa gấp để danh sách không còn vây lấy bạn.", "Đúng rồi; thở chậm lại—tạm dừng không phải thất bại.", "Tôi sẽ xếp: an toàn trước, mọi việc khác để sau."]),
            "amount.morale.appraise_negative": (["những thiếu hụt về chất lượng sống đang bào mòn kiên nhẫn của tôi.", "ngày nào cũng chỉ có việc, gần như không đủ hồi phục.", "nhu cầu nghỉ ngơi và giải trí đều chưa được đáp ứng.", "một món trang trí không thể che lấp vấn đề này.", "ta cùng xem nhu cầu sinh hoạt nào cứ bị bỏ quên nhé?"], ["Hiểu rồi; đây là tinh thần chung, không chỉ một chỉ số trang trí.", "Ta sẽ dành thời gian thực sự cho hồi phục.", "Tôi giúp kiểm tra lịch và quyền dùng khu giải trí.", "Đúng; hãy tìm thiếu hụt kéo dài thay vì đưa một món đồ trang trí.", "Được; ta lần lượt xét thức ăn, nghỉ ngơi, giải trí và môi trường."]),
            "amount.health.appraise_negative": (["sau khi sức khỏe giảm, vết thương cứ nhắc tôi mãi.", "tổn thương này không giống thứ có thể cố chịu qua.", "mỗi lần cử động mạnh, vết thương lại đau.", "tôi cần được khám y tế đúng cách.", "bạn tạm nhận vị trí nguy hiểm giúp tôi nhé?"], ["Kiểm tra vết thương và sức khỏe trước khi mạo hiểm thêm.", "Tôi sẽ đi cùng tới trạm y tế; đừng cược rằng nó tự khỏi.", "Hạn chế cử động; tôi sẽ lấy đồ sơ cứu.", "Được, đăng ký khám ngay và đừng xem nhẹ cơn đau.", "Tôi sẽ nhận việc; bạn rời khu nguy hiểm trước."]),
            "current_job.appraise_stressed": (["vai trò này đòi hỏi nhiều hơn mức tôi có thể xử lý an toàn.", "các ưu tiên xung đột nên tôi không biết phải nghe thứ tự nào.", "tôi nhận vai trò nhưng không có đủ thời gian cho việc cốt lõi.", "thêm một nhiệm vụ nữa là tôi sẽ bỏ sót bước quan trọng.", "ta phân lại trách nhiệm của ca này được không?"], ["Hãy xác định ranh giới vai trò để mọi việc không dồn lên bạn.", "Ta xếp theo an toàn và thời hạn, không theo ai nói to hơn.", "Tôi sẽ giữ thời gian cho trách nhiệm cốt lõi của bạn.", "Vậy hãy ngừng nhận việc mới và hoàn tất bước hiện tại trước.", "Được; tôi nhận một việc và ghi thay đổi vào lịch."]),
        },
    },
}


def build(locale: str) -> dict:
    authored = TEXT[locale]
    joiner = "" if locale in {"zh", "ja"} else " "
    candidates = []
    ordinal = 10_000
    for topic, (kind, domain, mode, appraisal) in TOPICS.items():
        speakers, listeners = authored["topics"][topic]
        for personality in PERSONALITIES:
            for mood in MOODS:
                mood_lead, mood_reply = authored["mood"][mood]
                for angle, (speaker, listener) in enumerate(zip(speakers, listeners, strict=True), 1):
                    candidate_id = (f"topic.{topic.replace('_', '-')}.{personality}."
                                    f"{mood}.angle-{angle}")
                    candidates.append({
                        "candidateId": candidate_id,
                        "diversityKey": candidate_id,
                        "storyletId": "Casual",
                        "contractRevision": 1,
                        "status": "reviewed",
                        "selection": {
                            "actors": [{"slot": 0, "personalities": [personality],
                                        "moods": [mood]}],
                            "resolvedTopics": [topic],
                            "conversationKinds": [kind],
                            "topicDomains": [domain],
                            "utteranceModes": [mode],
                            "appraisals": [appraisal],
                        },
                        "weight": 1,
                        "ordinal": ordinal,
                        "turns": [
                            {"turnId": "speaker", "speakerSlot": 0,
                             "text": joiner.join((authored["personality"][personality],
                                                  mood_lead, speaker))},
                            {"turnId": "listener", "speakerSlot": 1,
                             "text": joiner.join((mood_reply, listener))},
                        ],
                    })
                    ordinal += 1
    return {"locale": locale, "family": "casual-topic-pack", "candidates": candidates}


def rendered_payload(locale: str) -> str:
    return json.dumps(build(locale), ensure_ascii=False, indent=2) + "\n"


def content_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def update_provenance(locale: str, check: bool) -> None:
    source = ROOT / "locales" / "zh" / "dialogue" / "topic-pilot.json"
    target = ROOT / "locales" / locale / "dialogue" / "topic-pilot.json"
    row = {"path": "dialogue/topic-pilot.json", "sourceHash": content_hash(source),
           "targetHash": content_hash(target), "reviewStatus": "reviewed"}
    path = ROOT / "provenance" / f"{locale}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    index = next((i for i, item in enumerate(payload["files"])
                  if item.get("path") == row["path"]), None)
    if index is None:
        index = max((i for i, item in enumerate(payload["files"])
                     if item.get("path", "").startswith("dialogue/")), default=-1) + 1
        payload["files"].insert(index, row)
    else:
        payload["files"][index] = row
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if check:
        if path.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"Topic provenance is stale: {path}")
    else:
        path.write_text(rendered, encoding="utf-8")


def generate(locales: list[str], check: bool) -> None:
    # The source file must exist before translated provenance hashes are calculated.
    ordered = sorted(locales, key=lambda locale: locale != "zh")
    for locale in ordered:
        target = ROOT / "locales" / locale / "dialogue" / "topic-pilot.json"
        rendered = rendered_payload(locale)
        if check:
            if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"generated Topic pack is stale: {target}")
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
    print(f"Topic pack {'clean' if args.check else 'written'}: "
          f"{len(build(locales[0])['candidates'])} candidates × {len(locales)} locale(s)")


if __name__ == "__main__":
    main()
