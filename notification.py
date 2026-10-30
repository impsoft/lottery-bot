import datetime
import json
import logging
import re

import requests

logger = logging.getLogger(__name__)

try:
    import render
except ImportError:  # Pillow 가 없으면 이미지 없이 텍스트로만 보낸다
    render = None

KST = datetime.timezone(datetime.timedelta(hours=9))

# 동행복권 공 색상: 1-10 노랑, 11-20 파랑, 21-30 빨강, 31-40 회색, 41-45 초록
_BALLS = [(10, "🟡"), (20, "🔵"), (30, "🔴"), (40, "⚪"), (45, "🟢")]
_DIM = "▫️"
_KEYCAPS = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]

_COLOR_INFO = 0x2B7FFF
_COLOR_OK = 0x22C55E
_COLOR_NONE = 0x6B7280
_COLOR_SMALL = 0x3B82F6
_COLOR_MID = 0xA855F7
_COLOR_BIG = 0xF59E0B
_COLOR_ERROR = 0xEF4444

_WIN720_TAIL_MATCH = {1: 6, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1}
_IMAGE_NAME = "numbers.png"
_EMPTY_REASON_HINT = (
    "구매 페이지가 정상 응답하지 않았습니다.\n"
    "동행복권에 직접 로그인해서 **비밀번호 변경 안내** 같은 화면이 뜨는지 확인해 주세요. "
    "비밀번호를 바꿨다면 GitHub Secrets 의 `PASSWORD` 도 바꿔야 합니다."
)


def _failure_reason(msg) -> str:
    msg = (msg or "").strip()
    if not msg or msg == "Unknown Error":
        return _EMPTY_REASON_HINT
    return f"`{msg}`"


def ball(n: int) -> str:
    emoji = next(e for limit, e in _BALLS if n <= limit)
    return f"{emoji}`{n:02d}`"


def keycaps(digits: str) -> str:
    return "".join(_KEYCAPS[int(d)] if d.isdigit() else d for d in digits)


def won_short(amount: int) -> str:
    if amount >= 100_000_000:
        return f"{amount / 100_000_000:.1f}억"
    if amount >= 10_000:
        return f"{amount // 10_000:,}만"
    return f"{amount:,}"


def next_weekday(weekday: int, hour: int, minute: int) -> datetime.datetime:
    now = datetime.datetime.now(KST)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    target += datetime.timedelta(days=(weekday - now.weekday()) % 7)
    if target < now:
        target += datetime.timedelta(days=7)
    return target


def _when(dt: datetime.datetime) -> str:
    return f"{dt.month}/{dt.day}({'월화수목금토일'[dt.weekday()]}) {dt:%H:%M}"


def _rank_of(status: str) -> int:
    found = re.search(r"\d+", status or "")
    return int(found.group()) if found else 0


def _rank_color(best_rank: int, small: int, mid: int) -> int:
    if best_rank == 0:
        return _COLOR_NONE
    if best_rank <= mid:
        return _COLOR_BIG
    if best_rank <= small:
        return _COLOR_MID
    return _COLOR_SMALL


def _headline(best_rank: int, money: str) -> str:
    if best_rank:
        return f"## 🎉 {best_rank}등 당첨 · {money}"
    return "## 🫠 다음 기회에"


def _render(fn, *args, **kwargs):
    if render is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.warning(f"[Warning] Image render failed: {e}")
        return None


class Notification:
    def __init__(self, webhook_urls: list):
        self.webhook_urls = [url for url in webhook_urls if url]
        self.failed = False

    # ── 구매 ────────────────────────────────────────────

    def send_lotto_buying_message(self, body: dict) -> None:
        result = body.get("result", {})
        balance = body.get("balance", "확인불가")

        if result.get("resultMsg", "FAILURE").upper() != "SUCCESS":
            self._send({
                "title": "🎱 로또 6/45 구매 실패",
                "color": _COLOR_ERROR,
                "description": f"## ❌ 구매 실패\n{_failure_reason(result.get('resultMsg'))}",
                "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
            })
            return

        rows = []
        for line in result.get("arrGameChoiceNum", []):
            parts = line[:-1].split("|")
            rows.append((parts[0], [int(n) for n in parts[1:]]))

        image = _render(render.lotto, rows) if render else None
        description = [f"## ⏰ {_when(next_weekday(5, 20, 35))} 추첨"]
        if not image:
            description += [f"`{label}`  " + " ".join(ball(n) for n in nums) for label, nums in rows]

        self._send({
            "title": f"🎱 로또 6/45 · {result.get('buyRound', '?')}회 구매 완료",
            "color": _COLOR_OK,
            "description": "\n".join(description),
            "fields": [
                {"name": "잔액", "value": str(balance), "inline": True},
                {"name": "번호 선택", "value": body.get("strategy_note", "🎲 자동"), "inline": True},
            ],
        }, image)

    def send_win720_buying_message(self, body: dict) -> None:
        balance = body.get("balance", "확인불가")

        if body.get("resultCode") != '100':
            self._send({
                "title": "🎟️ 연금복권 720+ 구매 실패",
                "color": _COLOR_ERROR,
                "description": f"## ❌ 구매 실패\n{_failure_reason(body.get('resultMsg'))}",
                "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
            })
            return

        win720_round = body.get("round", "?")
        if win720_round == "?":
            try:
                win720_round = body.get("saleTicket", "").split("|")[-2]
            except (IndexError, AttributeError, TypeError):
                win720_round = "?"

        tickets = [t.strip() for t in (body.get("saleTicket") or "").split(",") if t.strip()]
        numbers = {t[1:] for t in tickets}
        description = [f"## ⏰ {_when(next_weekday(3, 19, 5))} 추첨"]
        image = None
        if not tickets:
            description.append("번호 정보 없음")
        elif len(numbers) == 1:
            groups = sorted(t[0] for t in tickets)
            number = numbers.pop()
            description.append(f"{groups[0]}~{groups[-1]}조 모든 조 구매")
            image = _render(render.win720, [(f"{groups[0]}-{groups[-1]}", number)]) if render else None
            if not image:
                description.append(keycaps(number))
        else:
            image = _render(render.win720, [(t[0], t[1:]) for t in tickets]) if render else None
            if not image:
                description += [f"`{t[0]}조`  {keycaps(t[1:])}" for t in tickets]

        self._send({
            "title": f"🎟️ 연금복권 720+ · {win720_round}회 구매 완료",
            "color": _COLOR_OK,
            "description": "\n".join(description),
            "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
        }, image)

    # ── 당첨 확인 ────────────────────────────────────────

    def send_lotto_winning_message(self, winning: dict) -> None:
        balance = winning.get("balance", "확인불가")
        if "round" not in winning:
            self._send({
                "title": "🎱 로또 6/45 결과",
                "color": _COLOR_NONE,
                "description": "## 📭 이번 주 구매 내역 없음",
                "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
            })
            return

        details = winning.get("lotto_details", [])
        rows = [(line["label"], line["numbers"]) for line in details]
        draw = winning.get("draw")
        win_num = draw["numbers"] if draw else sorted(winning.get("win_num", []))
        bonus = draw["bonus"] if draw else None

        if not win_num:
            image = _render(render.lotto, rows) if render else None
            description = [f"## ⏳ {_when(next_weekday(5, 20, 35))} 추첨 예정"]
            if not image:
                description += [f"`{label}`  " + " ".join(ball(n) for n in nums) for label, nums in rows]
            self._send({
                "title": f"🎱 로또 6/45 · {winning['round']}회 — 추첨 전",
                "color": _COLOR_INFO,
                "description": "\n".join(description),
                "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
            }, image)
            return

        ranks = [_rank_of(line["status"]) for line in details]
        best_rank = min((r for r in ranks if r), default=0)
        image = _render(render.lotto, rows, draw=win_num, bonus=bonus) if render else None

        description = [_headline(best_rank, winning.get("money", "-"))]
        description.append(" · ".join(
            f"{line['label']} **{line['status']}**" if rank else f"{line['label']} {line['status']}"
            for line, rank in zip(details, ranks)
        ) or "상세 정보를 불러오지 못했습니다.")
        if not image:
            description.append("")
            description.append("**당첨번호**  " + " ".join(ball(n) for n in win_num) + (f"  ➕ {ball(bonus)}" if bonus else ""))
            for label, nums in rows:
                description.append(f"`{label}`  " + " ".join(
                    ball(n) if n in win_num else f"{_DIM}`{n:02d}`" for n in nums
                ))

        fields = []
        if draw and draw["first_winners"]:
            fields.append({
                "name": "이번 회차 1등",
                "value": f"{draw['first_winners']}명 · {won_short(draw['first_prize'])}원",
                "inline": True,
            })
        fields.append({"name": "잔액", "value": str(balance), "inline": True})

        self._send({
            "title": f"🎱 로또 6/45 · {winning['round']}회 결과",
            "color": _rank_color(best_rank, small=4, mid=3),
            "description": "\n".join(description),
            "fields": fields,
        }, image)

    def send_win720_winning_message(self, winning: dict) -> None:
        balance = winning.get("balance", "확인불가")
        if "round" not in winning:
            self._send({
                "title": "🎟️ 연금복권 720+ 결과",
                "color": _COLOR_NONE,
                "description": "## 📭 이번 주 구매 내역 없음",
                "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
            })
            return

        details = winning.get("win720_details", [])
        draw = winning.get("draw")
        best_rank = min((line["rank"] for line in details if line["rank"]), default=0)
        image = None
        if draw:
            image = _render(render.win720, [(line["group"], line["number"]) for line in details],
                            draw_group=draw["group"], draw_number=draw["number"]) if render else None

        description = [_headline(best_rank, winning.get("money", "-"))]
        description.append(" · ".join(
            f"{line['group']}조 **{'보너스' if line['rank'] == 8 else line['status']}**" if line["rank"]
            else f"{line['group']}조 {line['status']}"
            for line in details
        ) or "상세 정보를 불러오지 못했습니다.")
        if draw and draw.get("bonus"):
            description.append(f"보너스 번호: 각조 **{draw['bonus']}**")

        if not image:
            description.append("")
            if draw:
                description.append(f"**1등**  `{draw['group']}조` {keycaps(draw['number'])}")
            for line in details:
                number = line["number"]
                matched = _WIN720_TAIL_MATCH.get(line["rank"], len(number) if line["rank"] == 8 else 0)
                split = len(number) - matched
                digits = " ".join(f"`{d}`" for d in number[:split]) + " " + keycaps(number[split:])
                description.append(f"`{line['group']}조`  {digits.strip()}")

        self._send({
            "title": f"🎟️ 연금복권 720+ · {winning['round']}회 결과",
            "color": _rank_color(best_rank, small=5, mid=3),
            "description": "\n".join(description),
            "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
        }, image)

    # ── 오류 ────────────────────────────────────────────

    def send_error_message(self, title: str, error: Exception) -> None:
        self._send({
            "title": f"⚠️ {title}",
            "color": _COLOR_ERROR,
            "description": f"## ❌ 실패\n```\n{type(error).__name__}: {str(error)[:1500]}\n```",
        })

    # ── 전송 ────────────────────────────────────────────

    def _send(self, embed: dict, image: bytes = None) -> None:
        embed.setdefault("footer", {"text": "lottery-bot"})
        embed.setdefault("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())

        if not self.webhook_urls:
            print(f"[Info] Webhook URL not found. Message: {self._to_text(embed)}")
            return

        for url in self.webhook_urls:
            try:
                if "hooks.slack.com" in url:
                    res = requests.post(url, json={"text": self._to_text(embed).replace("**", "*")}, timeout=10)
                elif image:
                    with_image = dict(embed, image={"url": f"attachment://{_IMAGE_NAME}"})
                    res = requests.post(
                        url,
                        data={"payload_json": json.dumps({"embeds": [with_image]})},
                        files={"files[0]": (_IMAGE_NAME, image, "image/png")},
                        timeout=20,
                    )
                else:
                    res = requests.post(url, json={"embeds": [embed]}, timeout=10)
                res.raise_for_status()
            except requests.RequestException as e:
                self.failed = True
                logger.error(f"[Error] Webhook send failed: {e}")

    @staticmethod
    def _to_text(embed: dict) -> str:
        lines = [f"**{embed['title']}**", embed.get("description", "").replace("## ", "")]
        lines += [f"{f['name']}: {f['value']}" for f in embed.get("fields", [])]
        return "\n".join(line for line in lines if line)
