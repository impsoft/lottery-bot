# 소개 

동행복권 사이트내에 계정에 예치금만 넣어두시면 이후 매주 로또와 연금복권을 구입하고 당첨을 체크하여 알려드려요!  

# 사용법 

![](./.github/images/check.png)

- 레포지토리를 `fork`  합니다. 
- Settings - Secrets - Add a new secret 메뉴로 들어갑니다
- 환경 변수들을 만들어 줍니다 (.env.sample 참조) 
- 매주 로또 및 연금복권 구매 및 당첨 과정을 자동으로 알려드려요 🎉

# Reference 
- https://github.com/roeniss/dhlottery-api

# 로또 번호 선택 (`STRATEGY`)

Settings - Secrets and variables - Actions - **Variables** 에 `STRATEGY` 를 만들면 바꿀 수 있습니다. 없으면 `smart` 입니다.

- `smart` : 인기 조합(생일 번호 위주, 3연속, 같은 끝자리 반복, 등차 패턴, 직전 회차 번호 재사용)을 피하고, 5장끼리 번호가 겹치지 않게(30/45개) 수동으로 구매합니다. 수동 구매가 거절되면 자동으로 다시 구매합니다.
- `auto` : 기존처럼 서버 자동번호로 구매합니다.

> 당첨 확률은 어떤 조합이든 같습니다. `smart` 는 1~3등 당첨 시 나눠 가질 사람을 줄이고, 5장 중 한 장이라도 5등 이상일 확률을 조금(약 11.4% → 12.0%) 높이는 것이 목적입니다.

# 스케줄 자동 비활성화 방지

수동 실행(Actions → Run workflow) 시 `target` 으로 로또만(`buy_lotto`)/연금복권만(`buy_win720`) 고를 수 있습니다.

GitHub 는 public 저장소에 60일간 활동이 없으면 스케줄 워크플로를 끕니다. 두 워크플로는 실행이 끝날 때마다 `enable` API 를 호출해 서로를 다시 활성화합니다 (`permissions: actions: write`).
