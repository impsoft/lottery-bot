"""
로또 6/45 번호 생성 전략.

당첨 확률은 어떤 조합이든 1/8,145,060 으로 같다. 여기서 하는 일은 두 가지뿐이다.
  1. 사람들이 많이 고르는 조합(생일 번호, 연속 번호, 등차 패턴, 직전 회차 번호)을 피해서
     1~3등 당첨 시 당첨금을 나눠 가질 사람 수를 줄인다.
  2. 여러 장을 살 때 장끼리 번호가 겹치지 않게 분산해서 "적어도 한 장은 5등 이상" 확률을 높인다.
"""
import random
from itertools import combinations
from typing import List, Optional, Sequence

NUMBERS = range(1, 46)
HIGH_START = 32          # 32~45 는 생일(1~31)로 고를 수 없는 번호
MIN_HIGH = 2
MAX_SAME_LAST_DIGIT = 2
MAX_LAST_DRAW_OVERLAP = 2

_MAX_ATTEMPTS = 2000


def popular_reasons(nums: Sequence[int], last_draw: Optional[Sequence[int]] = None) -> List[str]:
    """조합이 '인기 조합'으로 보이는 이유 목록. 빈 리스트면 통과."""
    nums = sorted(nums)
    reasons = []

    if sum(n >= HIGH_START for n in nums) < MIN_HIGH:
        reasons.append("생일 번호 위주")

    if any(nums[i] + 2 == nums[i + 1] + 1 == nums[i + 2] for i in range(len(nums) - 2)):
        reasons.append("3연속 번호")

    last_digits = [n % 10 for n in nums]
    if max(last_digits.count(d) for d in set(last_digits)) > MAX_SAME_LAST_DIGIT:
        reasons.append("같은 끝자리 반복")

    if any(b - a == c - b == d - c for a, b, c, d in combinations(nums, 4)):
        reasons.append("등차 패턴")

    if last_draw and len(set(nums) & set(last_draw)) > MAX_LAST_DRAW_OVERLAP:
        reasons.append("직전 회차 번호 재사용")

    return reasons


def generate_tickets(
    count: int,
    last_draw: Optional[Sequence[int]] = None,
    rng: Optional[random.Random] = None,
) -> List[List[int]]:
    """
    인기 조합을 피하고 장끼리 번호가 겹치지 않는 티켓 `count` 장을 만든다.
    5장이면 45개 중 30개 번호를 쓴다.
    """
    assert 1 <= count <= 7, "45개 번호로 겹치지 않게 만들 수 있는 최대 장수는 7장"
    rng = rng or random.SystemRandom()

    for _ in range(_MAX_ATTEMPTS):
        pool = list(NUMBERS)
        tickets = []
        for _ in range(count):
            ticket = _pick_ticket(pool, last_draw, rng)
            if ticket is None:
                break
            tickets.append(ticket)
            pool = [n for n in pool if n not in ticket]
        if len(tickets) == count:
            return tickets

    raise RuntimeError("조건을 만족하는 번호 조합을 만들지 못했습니다.")


def coverage(tickets: Sequence[Sequence[int]]) -> int:
    return len({n for t in tickets for n in t})


def _pick_ticket(pool, last_draw, rng) -> Optional[List[int]]:
    for _ in range(200):
        ticket = sorted(rng.sample(pool, 6))
        if not popular_reasons(ticket, last_draw):
            return ticket
    return None
