import datetime
import logging
import re

import requests

logger = logging.getLogger(__name__)

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
                "description": f"`{result.get('resultMsg', 'Unknown Error')}`",
                "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
            })
            return

        lines = []
        for line in result.get("arrGameChoiceNum", []):
            parts = line[:-1].split("|")
            nums = [int(n) for n in parts[1:]]
            lines.append(f"`{parts[0]}`  " + " ".join(ball(n) for n in nums))

        self._send({
            "title": f"🎱 로또 6/45 · {result.get('buyRound', '?')}회 구매 완료",
            "color": _COLOR_OK,
            "description": "\n".join(lines),
            "fields": [
                {"name": "추첨", "value": _when(next_weekday(5, 20, 35)), "inline": True},
                {"name": "잔액", "value": str(balance), "inline": True},
                {"name": "번호 선택", "value": body.get("strategy_note", "🎲 자동"), "inline": False},
            ],
        })

    def send_win720_buying_message(self, body: dict) -> None:
        balance = body.get("balance", "확인불가")

        if body.get("resultCode") != '100':
            self._send({
                "title": "🎟️ 연금복권 720+ 구매 실패",
                "color": _COLOR_ERROR,
                "description": f"`{body.get('resultMsg', 'Unknown Error')}`",
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
        if not tickets:
            description = "번호 정보 없음"
        elif len(numbers) == 1:
            groups = sorted(t[0] for t in tickets)
            description = f"{keycaps(numbers.pop())}\n`{groups[0]}~{groups[-1]}조` 모든 조 구매"
        else:
            description = "\n".join(f"`{t[0]}조`  {keycaps(t[1:])}" for t in tickets)

        self._send({
            "title": f"🎟️ 연금복권 720+ · {win720_round}회 구매 완료",
            "color": _COLOR_OK,
            "description": description,
            "fields": [
                {"name": "추첨", "value": _when(next_weekday(3, 19, 5)), "inline": True},
                {"name": "잔액", "value": str(balance), "inline": True},
            ],
        })

    # ── 당첨 확인 ────────────────────────────────────────

    def send_lotto_winning_message(self, winning: dict) -> None:
        balance = winning.get("balance", "확인불가")
        if "round" not in winning:
            self._send({
                "title": "🎱 로또 6/45 결과",
                "color": _COLOR_NONE,
                "description": "이번 주 구매 내역이 없습니다.",
                "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
            })
            return

        draw = winning.get("draw")
        win_num = set(draw["numbers"] if draw else winning.get("win_num", []))
        bonus = draw["bonus"] if draw else None

        if not win_num:
            lines = [
                f"`{line['label']}`  " + " ".join(ball(n) for n in line["numbers"])
                for line in winning.get("lotto_details", [])
            ]
            self._send({
                "title": f"🎱 로또 6/45 · {winning['round']}회 — 추첨 전 ⏳",
                "color": _COLOR_INFO,
                "description": "\n".join(lines) or "상세 정보를 불러오지 못했습니다.",
                "fields": [
                    {"name": "추첨", "value": _when(next_weekday(5, 20, 35)), "inline": True},
                    {"name": "잔액", "value": str(balance), "inline": True},
                ],
            })
            return

        description = []
        if draw:
            description.append(
                "**당첨번호**  " + " ".join(ball(n) for n in draw["numbers"]) + f"  ➕ {ball(bonus)}"
            )
        elif win_num:
            description.append("**당첨번호**  " + " ".join(ball(n) for n in sorted(win_num)))
        description.append("")

        best_rank = 0
        for line in winning.get("lotto_details", []):
            rank = _rank_of(line["status"])
            if rank and (best_rank == 0 or rank < best_rank):
                best_rank = rank
            nums = []
            for n in line["numbers"]:
                if n in win_num:
                    nums.append(ball(n))
                elif n == bonus and rank == 2:
                    nums.append(f"➕`{n:02d}`")
                else:
                    nums.append(f"{_DIM}`{n:02d}`")
            status = f"**{line['status']}**" if rank else line["status"]
            description.append(f"`{line['label']}`  " + " ".join(nums) + f"  {status}")

        if not winning.get("lotto_details"):
            description.append("상세 정보를 불러오지 못했습니다.")

        fields = [{"name": "당첨금", "value": winning.get("money", "-"), "inline": True}]
        if draw and draw["first_winners"]:
            fields.append({
                "name": "이번 회차 1등",
                "value": f"{draw['first_winners']}명 · {won_short(draw['first_prize'])}원",
                "inline": True,
            })
        fields.append({"name": "잔액", "value": str(balance), "inline": True})

        title = f"🎱 로또 6/45 · {winning['round']}회 결과"
        title += " 🎉" if best_rank else " — 다음 기회에 🫠"
        self._send({
            "title": title,
            "color": _rank_color(best_rank, small=4, mid=3),
            "description": "\n".join(description),
            "fields": fields,
        })

    def send_win720_winning_message(self, winning: dict) -> None:
        balance = winning.get("balance", "확인불가")
        if "round" not in winning:
            self._send({
                "title": "🎟️ 연금복권 720+ 결과",
                "color": _COLOR_NONE,
                "description": "이번 주 구매 내역이 없습니다.",
                "fields": [{"name": "잔액", "value": str(balance), "inline": True}],
            })
            return

        draw = winning.get("draw")
        description = []
        if draw:
            description.append(f"**1등**  `{draw['group']}조` {keycaps(draw['number'])}")
            if draw.get("bonus"):
                description.append(f"**보너스**  `각조` {keycaps(draw['bonus'])}")
            description.append("")

        best_rank = 0
        for line in winning.get("win720_details", []):
            rank = line["rank"]
            if rank and (best_rank == 0 or rank < best_rank):
                best_rank = rank
            number = line["number"]
            if draw:
                matched = 0
                for mine, drawn in zip(reversed(number), reversed(draw["number"])):
                    if mine != drawn:
                        break
                    matched += 1
                if draw.get("bonus") == number:
                    matched = len(number)
            else:
                matched = _WIN720_TAIL_MATCH.get(rank, len(number) if rank == 8 else 0)
            split = len(number) - matched
            digits = " ".join(f"`{d}`" for d in number[:split]) + " " + keycaps(number[split:])
            status = "보너스" if rank == 8 else line["status"]
            status = f"**{status}**" if rank else status
            description.append(f"`{line['group']}조`  {digits.strip()}  {status}")

        if not winning.get("win720_details"):
            description.append("상세 정보를 불러오지 못했습니다.")

        title = f"🎟️ 연금복권 720+ · {winning['round']}회 결과"
        title += " 🎉" if best_rank else " — 다음 기회에 🫠"
        self._send({
            "title": title,
            "color": _rank_color(best_rank, small=5, mid=3),
            "description": "\n".join(description),
            "fields": [
                {"name": "당첨금", "value": winning.get("money", "-"), "inline": True},
                {"name": "잔액", "value": str(balance), "inline": True},
            ],
        })

    # ── 오류 ────────────────────────────────────────────

    def send_error_message(self, title: str, error: Exception) -> None:
        self._send({
            "title": f"⚠️ {title}",
            "color": _COLOR_ERROR,
            "description": f"```\n{type(error).__name__}: {str(error)[:1500]}\n```",
        })

    # ── 전송 ────────────────────────────────────────────

    def _send(self, embed: dict) -> None:
        embed.setdefault("footer", {"text": "lottery-bot"})
        embed.setdefault("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())

        if not self.webhook_urls:
            print(f"[Info] Webhook URL not found. Message: {self._to_text(embed)}")
            return

        for url in self.webhook_urls:
            if "hooks.slack.com" in url:
                payload = {"text": self._to_text(embed).replace("**", "*")}
            else:
                payload = {"embeds": [embed]}
            try:
                res = requests.post(url, json=payload, timeout=10)
                res.raise_for_status()
            except requests.RequestException as e:
                self.failed = True
                logger.error(f"[Error] Webhook send failed: {e}")

    @staticmethod
    def _to_text(embed: dict) -> str:
        lines = [f"**{embed['title']}**", embed.get("description", "")]
        lines += [f"{f['name']}: {f['value']}" for f in embed.get("fields", [])]
        return "\n".join(line for line in lines if line)
