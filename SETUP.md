# 부산 ↔ 도쿄 항공권 최저가 추적기 — 설치 안내서

> 개발 경험이 전혀 없어도 **순서대로 따라 하면** 완성됩니다.
> 각 단계는 대부분 "복사 → 붙여넣기 → 저장" 이면 끝납니다.
> 막히면 그 단계 번호를 저에게 알려주세요.

---

## 전체 그림 (무엇을 하게 되나요?)

이 프로그램은 **구글 항공권(Google Flights) 데이터**를 사용합니다.
그래서 **별도의 가입이나 API 열쇠가 필요 없습니다.** (예전에 쓰려던
Amadeus는 2026년 7월 서비스가 종료되어 사용하지 않습니다.)

준비할 것은 딱 두 가지입니다:

1. **Gmail** 에서 프로그램 전용 비밀번호(앱 비밀번호)를 만든다 → 알림 메일용
2. **GitHub** 에 코드를 올리고, 자동 실행 + 웹 대시보드를 켠다

준비물: 이메일 주소, 웹 브라우저(크롬 등). 돈은 들지 않습니다.

---

## 1단계. Gmail 앱 비밀번호 만들기 (약 5분)

프로그램이 알림 메일을 보낼 때 쓰는 **전용 비밀번호**입니다.
(내 진짜 Gmail 비밀번호는 절대 쓰지 않습니다 → 더 안전)

> ⚠️ 먼저 **2단계 인증(2-Step Verification)** 이 켜져 있어야
> 앱 비밀번호를 만들 수 있습니다.

1. **2단계 인증 켜기**
   - https://myaccount.google.com/security 접속
   - "2단계 인증"(2-Step Verification) 을 찾아 **켜기** (안내 따라 휴대폰 인증)
2. **앱 비밀번호 만들기**
   - https://myaccount.google.com/apppasswords 접속
   - "앱 이름" 칸에 아무 이름 입력 (예: `flight tracker`) → **만들기**
   - **16자리 비밀번호**(예: `abcd efgh ijkl mnop`)가 나옵니다.
     **공백 없이 붙여서** 메모장에 복사하세요 → `abcdefghijklmnop`
   - 이 값이 `GMAIL_APP_PASSWORD` 입니다.
3. 내 Gmail 주소(예: `mymail@gmail.com`)가 `GMAIL_USER` 입니다.
   알림을 받을 주소도 보통 같은 주소면 됩니다 (`GMAIL_TO`).

> 앱 비밀번호 메뉴가 안 보이면 2단계 인증이 아직 안 켜진 것입니다.
> 1번을 먼저 완료하세요.

---

## 2단계. GitHub 계정 만들기 (약 3분)

코드를 올려두고 자동 실행시키는 곳입니다. (무료)

1. **https://github.com** 접속 → **Sign up**(가입)
2. 이메일/비밀번호/아이디(username) 정하고 가입
3. 이메일 인증까지 마치면 끝. **내 username을 기억해 두세요**
   (대시보드 주소에 들어갑니다)

---

## 3단계. 새 저장소(repository) 만들기 (약 2분)

"저장소"는 코드가 들어가는 폴더라고 생각하면 됩니다.

1. 로그인 상태에서 오른쪽 위 **+** → **New repository** 클릭
2. **Repository name**: `flight-tracker` (원하는 이름)
3. **Public**(공개) 선택 — GitHub Pages 무료 사용을 위해 공개로 두세요
   > 코드에는 비밀번호가 들어있지 않으니 공개해도 안전합니다.
   > (비밀 값은 5단계에서 따로 안전하게 넣습니다)
4. 나머지는 그대로 두고 **Create repository** 클릭

---

## 4단계. 코드 올리기 (파일 업로드, 약 5분)

가장 쉬운 방법인 **웹에서 드래그 업로드** 를 씁니다.

1. 방금 만든 저장소 화면에서
   **uploading an existing file**(기존 파일 업로드) 링크 클릭
   (또는 **Add file → Upload files**)
2. 내 컴퓨터의 `바탕화면/flight-tracker` 폴더를 엽니다.
3. 폴더 안의 **모든 파일**을 선택해 업로드 칸으로 드래그합니다.
   - `main.py`, `dashboard.py`, `config.py`,
     `requirements.txt`, `SETUP.md`, `.gitignore`
   > ⚠️ **`.github` 폴더도 꼭 함께 올려야** 자동 실행이 작동합니다.
   > 웹 드래그로 폴더가 안 올라가면, 아래 "폴더 업로드 팁"을 보세요.
4. 아래 **Commit changes**(초록 버튼) 클릭

### 폴더 업로드 팁 (`.github/workflows/run.yml`)
웹에서 숨은 폴더(`.github`)가 잘 안 올라갈 때:
1. 저장소에서 **Add file → Create new file** 클릭
2. 파일 이름 칸에 정확히 이렇게 입력:
   `.github/workflows/run.yml`
   (슬래시 `/` 를 치면 폴더가 자동으로 만들어집니다)
3. 내 컴퓨터의 `run.yml` 내용을 전부 복사해 붙여넣기
4. **Commit changes** 클릭

---

## 5단계. 비밀 값(Secrets) 등록하기 (약 3분)

Gmail 정보를 **암호화된 금고**에 넣는 단계입니다.

1. 저장소 화면 위쪽 **Settings**(설정) 탭 클릭
2. 왼쪽 메뉴에서 **Secrets and variables → Actions** 클릭
3. **New repository secret** 버튼으로 아래 **3개**를 하나씩 등록:

| Name (이름 — 정확히 그대로) | Secret (값) |
|------------------------------|-------------|
| `GMAIL_USER`         | 내 gmail 주소 (예: mymail@gmail.com) |
| `GMAIL_APP_PASSWORD` | 1단계의 16자리 앱 비밀번호 (공백 없이) |
| `GMAIL_TO`           | 알림 받을 주소 (보통 내 gmail 주소) |

> 이름(Name)은 **철자·대소문자까지 똑같이** 입력해야 합니다.
> 하나 등록할 때마다 **Add secret** 을 눌러 저장하세요.

---

## 6단계. 자동 실행(Actions) 켜기

1. 저장소 위쪽 **Actions** 탭 클릭
2. "Workflows aren't being run..." 같은 안내가 나오면
   **I understand my workflows, go ahead and enable them**
   (초록 버튼) 클릭
3. 왼쪽에서 **flight-price-tracker** 선택 →
   오른쪽 **Run workflow** 버튼으로 **지금 한 번 수동 실행** 해보세요
4. 잠시 뒤 실행 줄을 클릭하면 진행 로그를 볼 수 있습니다.
   초록 체크(✔) 가 뜨면 성공입니다.

> 이후에는 하루 3번(한국시간 오전 8시 / 오후 2시 / 밤 10시) 자동 실행됩니다.
> (GitHub 사정으로 몇 분 늦게 시작될 수 있는데 정상입니다)
>
> 검색량이 많아 한 번 실행에 몇 분 걸릴 수 있습니다. 정상입니다.

---

## 7단계. 웹 대시보드(GitHub Pages) 켜기

핸드폰에서 볼 수 있는 웹 주소를 만드는 단계입니다.
> **6단계 실행이 최소 1번 성공**해서 `index.html` 이 만들어진 뒤에 하세요.

1. 저장소 **Settings** → 왼쪽 메뉴 **Pages** 클릭
2. **Source** 를 **Deploy from a branch** 로 선택
3. **Branch** 를 **main** / 폴더는 **/ (root)** 로 선택 → **Save**
4. 1~2분 뒤 새로고침하면 위쪽에 주소가 나옵니다:
   `https://<내아이디>.github.io/flight-tracker/`
5. 이 주소를 핸드폰 즐겨찾기에 저장하세요. 그게 대시보드입니다!

---

## 8단계. 대시보드 링크를 메일에도 넣기 (선택)

알림 메일 속 "대시보드 열기" 링크가 정확히 열리도록:

1. 저장소에서 `config.py` 파일 클릭 → 오른쪽 **연필(✏️)** 아이콘
2. 아래 줄을 찾아
   ```python
   DASHBOARD_URL = "https://<username>.github.io/<repo>/"
   ```
   내 실제 주소로 바꿉니다. 예:
   ```python
   DASHBOARD_URL = "https://hong-gildong.github.io/flight-tracker/"
   ```
3. **Commit changes** 클릭

---

## 자주 쓰는 설정 바꾸기 (`config.py` 맨 위)

| 바꾸고 싶은 것 | 고칠 값 |
|----------------|---------|
| 출발/도착 공항 | `ORIGIN`, `DESTINATION` |
| 출국일 범위    | `DEPART_START`, `DEPART_END` |
| 체류 일정      | `STAY_OPTIONS` (예: `[2, 3]`) |
| 인원 수        | `ADULTS` |
| 좌석 등급      | `SEAT` (`"economy"` 등, 소문자) |
| 직항만/경유포함 | `NON_STOP` (`True`/`False`) |
| **결과가 적을 때 인천도 검색** | `INCLUDE_ICN_FALLBACK = True` |

`config.py` 를 GitHub에서 연필로 수정 → **Commit** 하면 바로 반영됩니다.

---

## 결과가 너무 적게 나올 때

1. `config.py` 에서 `INCLUDE_ICN_FALLBACK = True` 로 바꾸면
   **부산 결과가 부족할 때 인천(ICN) 출발도 함께 검색**합니다.
2. 구글 쪽에서 일시적으로 요청을 막아 결과가 빌 때가 있습니다. 이때는
   `config.py` 의 `FETCH_MODE` 를 `"common"` → `"fallback"` 으로
   바꾸면 예비 경로로 다시 시도합니다.

---

## 문제가 생기면 확인 순서

1. **Actions 탭** → 빨간 X 가 뜬 실행을 클릭 → 로그에서 빨간 글씨 확인
2. 가장 흔한 원인:
   - Secret 이름 오타 (대소문자까지 정확히)
   - Gmail 앱 비밀번호에 공백이 들어감 → 공백 없이 다시 등록
   - 2단계 인증이 안 켜진 상태에서 앱 비밀번호 사용
   - 구글이 잠깐 요청을 막음 → 위 "결과가 적게 나올 때" 2번 참고
3. 로그 내용을 저에게 그대로 복사해서 보여주시면 함께 봐드릴게요.
```
