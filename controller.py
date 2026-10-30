import os
import sys
import logging
from dotenv import load_dotenv

import auth
import draw
import lotto645
import win720
import notification
import strategy
import time
from HttpClient import HttpClientSingleton

logger = logging.getLogger(__name__)


def _env_url(name: str):
    url = os.environ.get(name)
    if not url or url.startswith("YOUR_"):
        return None
    return url


_LOGIN_ROUNDS = 3
_LOGIN_ROUND_WAIT = 60

_session = None


def _setup_and_login(fresh: bool = False):
    """
    로그인 세션을 재사용한다. fresh=True 면 쿠키를 지우고 새로 로그인한다 (연금복권 구매는 새 세션 필요).
    GitHub 러너에서 동행복권 접속이 자주 타임아웃 나므로, 로그인 실패 시 60초 쉬고 최대 3라운드 다시 시도한다.
    로그인은 구매 전 단계라 재시도해도 중복 구매 위험이 없다.
    """
    global _session
    if _session and not fresh:
        return _session

    load_dotenv(override=True)
    username = os.environ.get('USERNAME')
    password = os.environ.get('PASSWORD')

    for attempt in range(_LOGIN_ROUNDS):
        HttpClientSingleton.get_instance().session.cookies.clear()
        auth_ctrl = auth.AuthController()
        try:
            auth_ctrl.login(username, password)
            break
        except Exception as e:
            if attempt == _LOGIN_ROUNDS - 1:
                raise
            logger.warning(f"[Retry] Login round {attempt + 1}/{_LOGIN_ROUNDS} failed: {e}. Waiting {_LOGIN_ROUND_WAIT}s...")
            time.sleep(_LOGIN_ROUND_WAIT)

    _session = (auth_ctrl, username)
    return _session


def _notifier() -> notification.Notification:
    load_dotenv(override=True)
    return notification.Notification([_env_url('DISCORD_WEBHOOK_URL'), _env_url('SLACK_WEBHOOK_URL')])


def _smart_numbers(cnt: int):
    """인기 조합 회피 번호 생성. 직전 회차 번호를 못 가져오면 그 조건만 빼고 생성한다."""
    last_draw = None
    latest_round = draw.get_latest_lotto645_round()
    if latest_round:
        last = draw.get_lotto645_draw(latest_round)
        last_draw = last["numbers"] if last else None

    tickets = strategy.generate_tickets(cnt, last_draw=last_draw)
    note = f"🧠 인기 조합 회피 · {strategy.coverage(tickets)}/45개 번호 분산"
    if not last_draw:
        note += " (직전 회차 조회 실패)"
    return tickets, note


def buy_lotto645(authCtrl: auth.AuthController, cnt: int, mode: str):
    lotto = lotto645.Lotto645()

    if mode.upper() == "SMART":
        tickets, note = _smart_numbers(cnt)
        response = lotto.buy_lotto645(authCtrl, cnt, lotto645.Lotto645Mode.MANUAL, tickets)

        result = response.get("result", {})
        if result.get("resultMsg", "FAILURE").upper() == "SUCCESS":
            response['strategy_note'] = note
        else:
            # 명시적으로 거절된 경우에만 자동으로 다시 산다 (네트워크 오류는 중복 구매 위험이 있어 재시도하지 않음)
            reason = result.get('resultMsg', 'Unknown Error')
            logger.warning(f"[Warning] Manual purchase rejected ({reason}). Falling back to AUTO.")
            response = lotto.buy_lotto645(authCtrl, cnt, lotto645.Lotto645Mode.AUTO)
            response['strategy_note'] = f"🎲 자동 (수동 구매 거절: `{reason}`)"
    else:
        response = lotto.buy_lotto645(authCtrl, cnt, lotto645.Lotto645Mode.AUTO)
        response['strategy_note'] = "🎲 자동"

    response['balance'] = authCtrl.get_user_balance()
    return response

def check_winning_lotto645(authCtrl: auth.AuthController) -> dict:
    lotto = lotto645.Lotto645()
    item = lotto.check_winning(authCtrl)
    item['balance'] = authCtrl.get_user_balance()
    if item.get('round'):
        item['draw'] = draw.get_lotto645_draw(int(item['round']))
    return item

def buy_win720(authCtrl: auth.AuthController, username: str):
    pension = win720.Win720()
    response = pension.buy_Win720(authCtrl, username)
    response['balance'] = authCtrl.get_user_balance()
    return response

def check_winning_win720(authCtrl: auth.AuthController) -> dict:
    pension = win720.Win720()
    item = pension.check_winning(authCtrl)
    item['balance'] = authCtrl.get_user_balance()
    if item.get('round'):
        item['draw'] = draw.get_win720_draw(int(item['round']))
    return item

def _run(notify: notification.Notification, title: str, job) -> None:
    try:
        job()
    except Exception as e:
        logger.exception(f"[Error] {title}")
        notify.failed = True
        notify.send_error_message(title, e)

# Actions 로그는 public 이라 회차/장수/성공 여부만 남긴다 (잔액·당첨금·번호 제외)
def _lotto_buy(notify):
    count = int(os.environ.get('COUNT'))
    mode = os.environ.get('STRATEGY', 'smart')
    auth_ctrl, _ = _setup_and_login()
    response = buy_lotto645(auth_ctrl, count, mode)
    result = response.get('result', {})
    logger.info(f"[Result] 로또 구매: {result.get('resultMsg')} / {result.get('buyRound', '?')}회 {len(result.get('arrGameChoiceNum') or [])}게임")
    notify.send_lotto_buying_message(response)

def _win720_buy(notify):
    auth_ctrl, username = _setup_and_login(fresh=True)
    response = buy_win720(auth_ctrl, username)
    tickets = [t for t in (response.get('saleTicket') or '').split(',') if t.strip()]
    logger.info(f"[Result] 연금복권 구매: code={response.get('resultCode')} / {response.get('round', '?')}회 {len(tickets)}장")
    notify.send_win720_buying_message(response)

def _lotto_check(notify):
    auth_ctrl, _ = _setup_and_login()
    item = check_winning_lotto645(auth_ctrl)
    logger.info(f"[Result] 로또 내역: {item.get('round', '없음')}회 {len(item.get('lotto_details', []))}게임, 추첨 {'완료' if item.get('draw') else '전/조회실패'}")
    notify.send_lotto_winning_message(item)

def _win720_check(notify):
    auth_ctrl, _ = _setup_and_login()
    item = check_winning_win720(auth_ctrl)
    logger.info(f"[Result] 연금복권 내역: {item.get('round', '없음')}회 {len(item.get('win720_details', []))}장, 추첨 {'완료' if item.get('draw') else '전/조회실패'}")
    notify.send_win720_winning_message(item)

def run():
    if len(sys.argv) < 2:
        print("Usage: python controller.py [buy|check|buy_lotto|buy_win720|check_lotto|check_win720]")
        return

    logging.basicConfig(level=logging.INFO)
    notify = _notifier()

    jobs = {
        "buy_lotto": [("로또 구매 오류", _lotto_buy)],
        "buy_win720": [("연금복권 구매 오류", _win720_buy)],
        "check_lotto": [("로또 당첨 확인 오류", _lotto_check)],
        "check_win720": [("연금복권 당첨 확인 오류", _win720_check)],
    }
    jobs["buy"] = jobs["buy_lotto"] + jobs["buy_win720"]
    jobs["check"] = jobs["check_lotto"] + jobs["check_win720"]

    if sys.argv[1] not in jobs:
        print(f"Unknown command: {sys.argv[1]}")
        sys.exit(2)

    for i, (title, job) in enumerate(jobs[sys.argv[1]]):
        if i > 0:
            time.sleep(10)
        _run(notify, title, lambda: job(notify))

    if notify.failed:
        sys.exit(1)


if __name__ == "__main__":
    run()
