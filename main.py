# -*- coding: utf-8 -*-
"""
========================================================================
메인 프로그램 (main.py)
------------------------------------------------------------------------
하는 일 (순서대로):
  1) Amadeus API에 로그인해서 출입증(토큰)을 받는다
  2) 정해진 날짜 범위 x (2박3일 / 3박4일) 조합으로 왕복 직항 최저가 검색
  3) 결과를 price_history.csv 에 계속 쌓는다
  4) 역대 최저가(2박3일 / 3박4일 각각)와 비교
       - 더 싸지면 → 알림 메일 발송 + 최저가 갱신
  5) 하루 1번은 "오늘의 최저가 요약" 메일 발송
  6) 웹 대시보드(index.html) 자동 생성

※ API 키와 Gmail 비밀번호는 코드에 쓰지 않고 "환경변수"에서 읽어옵니다.
  (GitHub Secrets 또는 내 컴퓨터 환경변수)
========================================================================
"""

import os
import csv
import json
import time
import smtplib
import datetime as dt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import re  # 가격 문자열("₩2171200")에서 숫자만 뽑을 때 사용

# fast-flights: 구글 항공권 데이터를 가져오는 라이브러리
from fast_flights import get_flights_from_filter, TFSData, FlightData, Passengers

import config
from dashboard import build_dashboard  # 대시보드 생성 함수


# ────────────────────────────────────────────────────────────────
# 환경변수(비밀 값) 읽어오기
#   os.environ.get("이름") = "이름"이라는 환경변수의 값을 가져온다
#   (GitHub Secrets 에 등록한 값이 여기로 들어옵니다)
# ────────────────────────────────────────────────────────────────
GMAIL_USER = os.environ.get("GMAIL_USER", "")           # 보내는 gmail 주소
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")  # gmail 앱 비밀번호
GMAIL_TO = os.environ.get("GMAIL_TO", GMAIL_USER)       # 받는 주소(비우면 본인에게)


# 한국 시간(KST)을 계산하기 위한 시간대 (UTC+9)
KST = dt.timezone(dt.timedelta(hours=9))


def now_kst():
    """지금 시각을 한국 시간으로 돌려준다."""
    return dt.datetime.now(KST)


# ================================================================
# 1. 항공권 검색 (한 조합 = 출국일+귀국일 한 쌍)
# ================================================================
def parse_price(price_text):
    """'₩2171200' 같은 문자열에서 숫자만 뽑아 정수로 만든다. 없으면 None."""
    digits = re.sub(r"[^0-9]", "", price_text or "")
    return int(digits) if digits else None


def search_one(origin, departure_date, return_date):
    """
    한 개의 (출발지, 출국일, 귀국일) 조합에 대해
    왕복 직항 최저가 항공권을 검색해서
    가장 싼 항공편 1개의 정보를 돌려준다.
    결과가 없거나 오류면 None 을 돌려준다.
    """
    # 직항만 보려면 경유 횟수 최대값을 0으로 (config.NON_STOP=True 이면 0)
    max_stops = 0 if config.NON_STOP else None

    # 검색 조건표(필터) 만들기: 갈 때(origin→NRT), 올 때(NRT→origin)
    tfs = TFSData.from_interface(
        flight_data=[
            FlightData(date=departure_date, from_airport=origin,
                       to_airport=config.DESTINATION, max_stops=max_stops),
            FlightData(date=return_date, from_airport=config.DESTINATION,
                       to_airport=origin, max_stops=max_stops),
        ],
        trip="round-trip",
        passengers=Passengers(adults=config.ADULTS),
        seat=config.SEAT,
        max_stops=max_stops,
    )

    # 통화를 KRW(원화)로 고정해서 가져온다 (서버 위치와 무관하게 원화로)
    try:
        result = get_flights_from_filter(
            tfs, currency=config.CURRENCY, mode=config.FETCH_MODE
        )
    except Exception as e:
        print(f"  [주의] {origin} {departure_date}~{return_date} 검색 실패: {e}")
        return None

    # 후보들 중 직항이면서 가격이 있는 것만 모아 최저가 찾기
    best = None  # (가격, 항공사) 형태
    for f in result.flights:
        if config.NON_STOP and f.stops != 0:  # 혹시 섞여 나온 경유편 제외
            continue
        price = parse_price(f.price)
        if price is None:
            continue
        if best is None or price < best[0]:
            best = (price, f.name)

    if best is None:
        return None

    total_price = best[0]                             # 성인 전체 총액(KRW)
    per_person = round(total_price / config.ADULTS)    # 1인당 가격
    airline = best[1] or "?"

    return {
        "origin": origin,
        "departure_date": departure_date,
        "return_date": return_date,
        "airline": airline,
        "total_price": total_price,
        "per_person": per_person,
    }


# ================================================================
# 3. 전체 검색 (모든 날짜 x 2박3일/3박4일)
# ================================================================
def run_search():
    """
    출국일 범위 전체를 하루씩 돌면서,
    2박3일 / 3박4일 각각의 최저가를 모아 리스트로 돌려준다.
    """
    results = []  # 여기에 검색 결과를 담는다

    start = dt.date.fromisoformat(config.DEPART_START)
    end = dt.date.fromisoformat(config.DEPART_END)
    search_time = now_kst().strftime("%Y-%m-%d %H:%M:%S")

    # 검색할 출발지 목록 정하기 (기본은 부산만)
    origins = [config.ORIGIN]

    day = start
    while day <= end:
        for nights in config.STAY_OPTIONS:
            return_day = day + dt.timedelta(days=nights)
            dep_str = day.isoformat()
            ret_str = return_day.isoformat()

            for origin in origins:
                info = search_one(origin, dep_str, ret_str)
                time.sleep(config.SLEEP_BETWEEN_CALLS)  # 서버 배려용 잠깐 쉬기
                if info is None:
                    continue
                info["search_time"] = search_time
                info["stay_label"] = config.STAY_LABELS[nights]
                info["nights"] = nights
                results.append(info)
                print(f"  찾음: {info['stay_label']} {dep_str}~{ret_str} "
                      f"{info['airline']} {info['total_price']:,}원")
        day += dt.timedelta(days=1)

    # ── 결과가 너무 적으면 인천(ICN) 출발도 추가 검색 ──
    busan_count = len(results)
    if config.INCLUDE_ICN_FALLBACK and busan_count < config.MIN_RESULTS_THRESHOLD:
        print(f"부산 결과가 {busan_count}개로 적어 인천(ICN) 출발도 검색합니다.")
        day = start
        while day <= end:
            for nights in config.STAY_OPTIONS:
                return_day = day + dt.timedelta(days=nights)
                info = search_one(config.ICN_ORIGIN,
                                  day.isoformat(), return_day.isoformat())
                time.sleep(config.SLEEP_BETWEEN_CALLS)
                if info is None:
                    continue
                info["search_time"] = search_time
                info["stay_label"] = config.STAY_LABELS[nights]
                info["nights"] = nights
                results.append(info)
            day += dt.timedelta(days=1)

    return results, search_time


# ================================================================
# 4. CSV 저장
# ================================================================
CSV_HEADER = [
    "검색시각", "일정타입", "출발지", "출국일", "귀국일",
    "항공사", "총가격KRW", "1인가격KRW",
]


def append_to_csv(results):
    """검색 결과를 price_history.csv 맨 아래에 계속 이어붙인다."""
    file_exists = os.path.exists(config.CSV_FILE)
    with open(config.CSV_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(CSV_HEADER)  # 파일이 처음이면 제목줄부터
        for r in results:
            writer.writerow([
                r["search_time"], r["stay_label"], r["origin"],
                r["departure_date"], r["return_date"], r["airline"],
                r["total_price"], r["per_person"],
            ])


# ================================================================
# 5. 역대 최저가 기록 관리 (records.json)
# ================================================================
def load_records():
    """저장된 역대 최저가를 불러온다. 없으면 빈 값."""
    if os.path.exists(config.RECORD_FILE):
        with open(config.RECORD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}  # 예: {"2박3일": {...}, "3박4일": {...}}


def save_records(records):
    with open(config.RECORD_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def find_cheapest_by_type(results):
    """
    이번 검색 결과에서 일정타입(2박3일/3박4일)별로 가장 싼 것을 찾는다.
    """
    best = {}
    for r in results:
        label = r["stay_label"]
        if label not in best or r["total_price"] < best[label]["total_price"]:
            best[label] = r
    return best


# ================================================================
# 6. 이메일 발송 (Gmail)
# ================================================================
def send_email(subject, html_body):
    """
    Gmail SMTP(SSL) 로 HTML 메일을 보낸다.
    보안을 위해 일반 비밀번호가 아니라 "앱 비밀번호"를 사용합니다.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("  [주의] Gmail 정보가 없어 메일을 건너뜁니다.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_TO
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, [GMAIL_TO], msg.as_string())
    print(f"  메일 발송 완료: {subject}")


def format_flight_html(r):
    """항공편 한 건을 메일용 HTML 조각으로 만든다."""
    return (
        f"<ul>"
        f"<li>일정: <b>{r['stay_label']}</b></li>"
        f"<li>출발지 → 도착지: {r['origin']} → {config.DESTINATION}</li>"
        f"<li>출국일: {r['departure_date']} / 귀국일: {r['return_date']}</li>"
        f"<li>항공사: {r['airline']}</li>"
        f"<li>총 가격(성인 {config.ADULTS}명): <b>{r['total_price']:,}원</b></li>"
        f"<li>1인당 가격: <b>{r['per_person']:,}원</b></li>"
        f"</ul>"
    )


def send_record_alert(r, old_price):
    """역대 최저가를 갱신했을 때 보내는 알림 메일."""
    diff = old_price - r["total_price"] if old_price else 0
    diff_text = (f"이전 최저가보다 <b>{diff:,}원</b> 저렴!"
                 if old_price else "첫 기록입니다.")
    subject = f"[항공권 최저가] {r['stay_label']} {r['total_price']:,}원 신기록!"
    body = f"""
    <h2>🎉 역대 최저가 갱신!</h2>
    {format_flight_html(r)}
    <p>{diff_text}</p>
    <p>검색 시각: {r['search_time']} (한국시간)</p>
    <p><a href="{config.DASHBOARD_URL}">📊 대시보드에서 자세히 보기</a></p>
    """
    send_email(subject, body)


def send_daily_summary(best):
    """하루 1회 보내는 오늘의 최저가 요약 메일 (두 일정 모두 포함)."""
    subject = "[항공권] 오늘의 최저가 요약"
    parts = ["<h2>📮 오늘의 최저가 요약</h2>"]
    for label in config.STAY_LABELS.values():
        if label in best:
            parts.append(f"<h3>{label}</h3>")
            parts.append(format_flight_html(best[label]))
        else:
            parts.append(f"<h3>{label}</h3><p>검색 결과 없음</p>")
    parts.append(f'<p><a href="{config.DASHBOARD_URL}">📊 대시보드 열기</a></p>')
    parts.append(f"<p>검색 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S')} (한국시간)</p>")
    send_email(subject, "".join(parts))


# ================================================================
# 7. 하루 1회 요약 여부 판단 (state.json)
# ================================================================
def load_state():
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ================================================================
# 8. 전체 실행 (main)
# ================================================================
def main():
    print("=" * 55)
    print("항공권 최저가 추적 시작:", now_kst().strftime("%Y-%m-%d %H:%M:%S"))
    print("출발:", config.ORIGIN, "→ 도착:", config.DESTINATION,
          "/ 좌석:", config.SEAT, "/ 성인:", config.ADULTS, "명")
    print("=" * 55)

    # (1) 검색
    results, search_time = run_search()
    print(f"검색 완료: 총 {len(results)}건")

    # (2) CSV 저장
    if results:
        append_to_csv(results)
        print(f"{config.CSV_FILE} 에 저장 완료")

    # (3) 역대 최저가 비교 & 알림
    records = load_records()
    best = find_cheapest_by_type(results)

    for label, r in best.items():
        old = records.get(label)
        old_price = old["total_price"] if old else None
        if old_price is None or r["total_price"] < old_price:
            # 신기록!
            send_record_alert(r, old_price)
            records[label] = {
                "total_price": r["total_price"],
                "per_person": r["per_person"],
                "airline": r["airline"],
                "origin": r["origin"],
                "departure_date": r["departure_date"],
                "return_date": r["return_date"],
                "search_time": r["search_time"],
            }
    save_records(records)

    # (4) 하루 1회 요약 메일
    state = load_state()
    today = now_kst().strftime("%Y-%m-%d")
    if state.get("last_summary_date") != today and best:
        send_daily_summary(best)
        state["last_summary_date"] = today
        save_state(state)
    else:
        print("오늘 요약 메일은 이미 보냈거나 결과가 없어 건너뜁니다.")

    # (5) 대시보드 생성
    build_dashboard()
    print("대시보드(index.html) 생성 완료")
    print("모든 작업 끝!")


if __name__ == "__main__":
    main()
