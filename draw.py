"""
동행복권 공개 추첨 결과 조회 (로그인 불필요).
"""
import logging
import re
from typing import Optional

import requests

import auth
from HttpClient import HttpClientSingleton

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": auth.USER_AGENT,
    "Accept": "application/json, text/html;q=0.9",
    "Referer": "https://www.dhlottery.co.kr/",
}


def _ymd(raw) -> str:
    raw = str(raw or "")
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 else raw


def get_latest_lotto645_round() -> Optional[int]:
    try:
        res = HttpClientSingleton.get_instance().get(
            "https://www.dhlottery.co.kr/lt645/result", headers=_HEADERS
        )
        found = re.search(r'id="opt_val"[^>]*value="(\d+)"', res.text)
        return int(found.group(1)) if found else None
    except requests.RequestException as e:
        logger.warning(f"[Warning] Latest lotto round lookup failed: {e}")
        return None


def get_lotto645_draw(round_no: int) -> Optional[dict]:
    """
    {"round", "date", "numbers": [6], "bonus", "first_winners", "first_prize"}
    """
    try:
        res = HttpClientSingleton.get_instance().get(
            "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do",
            headers=_HEADERS,
            params={"srchDir": "center", "srchLtEpsd": round_no},
        )
        items = res.json().get("data", {}).get("list", [])
        item = next((x for x in items if int(x.get("ltEpsd", 0)) == int(round_no)), None)
        if not item:
            return None

        return {
            "round": int(item["ltEpsd"]),
            "date": _ymd(item.get("ltRflYmd")),
            "numbers": [int(item[f"tm{i}WnNo"]) for i in range(1, 7)],
            "bonus": int(item["bnsWnNo"]),
            "first_winners": int(item.get("rnk1WnNope") or 0),
            "first_prize": int(item.get("rnk1WnAmt") or 0),
        }
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        logger.warning(f"[Warning] Lotto draw lookup failed (round={round_no}): {e}")
        return None


def get_win720_draw(round_no: int) -> Optional[dict]:
    """
    {"round", "date", "group", "number", "bonus"}  (number/bonus 는 6자리 문자열)
    """
    try:
        res = HttpClientSingleton.get_instance().get(
            "https://www.dhlottery.co.kr/pt720/selectPstPt720Info.do",
            headers=_HEADERS,
            params={"srchPsltEpsd": round_no},
        )
        items = [
            x for x in res.json().get("data", {}).get("result", [])
            if int(x.get("psltEpsd", 0)) == int(round_no)
        ]
        first = next((x for x in items if int(x.get("psltSn", 0)) == 1), None)
        bonus = next((x for x in items if int(x.get("psltSn", 0)) == 8), None)
        if not first:
            return None

        return {
            "round": int(first["psltEpsd"]),
            "date": _ymd(first.get("psltRflYmd")),
            "group": str(first.get("wnBndNo") or ""),
            "number": str(first["wnRnkVl"]),
            "bonus": str(bonus["wnRnkVl"]) if bonus else None,
        }
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        logger.warning(f"[Warning] Win720 draw lookup failed (round={round_no}): {e}")
        return None
