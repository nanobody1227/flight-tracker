# -*- coding: utf-8 -*-
"""
========================================================================
메인 프로그램 (main.py)
------------------------------------------------------------------------
하는 일 (순서대로):
  1) 구글 항공권(fast-flights)에서 가는 편·오는 편을 각각 편도로 검색
     (2박3일 / 3박4일 조합) → 두 편의 최저가를 합쳐 왕복 최저가로 사용
  2) 결과를 price_history.csv 에 계속 쌓는다
  3) 역대 최저가(2박3일 / 3박4일 각각)와 비교
       - 더 싸지면 → 알림 메일 발송 + 최저가 갱신
  4) 하루 1번은 "오늘의 최저가 요약" 메일 발송
  5) 웹 대시보드(index.html) 자동 생성

※ Gmail 비밀번호는 코드에 쓰지 않고 "환경변수"에서 읽어옵니다.
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
from dashboard import build_dashboard, flight_link  # 대시보드 생성 + 예약 링크 함수


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


def clean_time(text):
    """'4:20 PM on Tue, Jan 26' → '16:20' (24시간 형식) 으로 바꾼다."""
    t = (text or "").split(" on ")[0].strip()  # 날짜 부분 떼고 시각만: "4:20 PM"
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", t)
    if not m:
        return t
    hour, minute, ap = int(m.group(1)), m.group(2), m.group(3)
    if ap == "PM" and hour != 12:
        hour += 12
    if ap == "AM" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute}"


def kor_duration(text):
    """'2 hr 30 min' → '2시간 30분' 으로 바꾼다."""
    return (text or "").replace(" hr", "시간").replace(" min", "분").strip()


def search_leg(from_airport, to_airport, date):
    """
    한 방향(편도) 직항 최저가를 검색한다.
      예) 가는 편 = PUS→NRT, 오는 편 = NRT→PUS
    가장 싼 직항 1편의 정보를 dict로 돌려준다. 없으면 None.
    """
    max_stops = 0 if config.NON_STOP else None

    tfs = TFSData.from_interface(
        flight_data=[
            FlightData(date=date, from_airport=from_airport,
                       to_airport=to_airport, max_stops=max_stops),
        ],
        trip="one-way",
        passengers=Passengers(adults=config.ADULTS),
        seat=config.SEAT,
        max_stops=max_stops,
    )

    try:
        result = get_flights_from_filter(
            tfs, currency=config.CURRENCY, mode=config.FETCH_MODE
        )
    except Exception as e:
        print(f"  [주의] {from_airport}→{to_airport} {date} 검색 실패: {e}")
        return None

    best_price = None
    best_flight = None
    for f in result.flights:
        if config.NON_STOP and f.stops != 0:
            continue
        price = parse_price(f.price)
        if price is None:
            continue
        if best_price is None or price < best_price:
            best_price = price
            best_flight = f

    if best_flight is None:
        return None

    return {
        "airline": best_flight.name or "?",
        "price": best_price,                       # 성인 전체 총액(KRW)
        "dep_time": clean_time(best_flight.departure),
        "arr_time": clean_time(best_flight.arrival),
        "duration": kor_duration(best_flight.duration),
    }


# ================================================================
# 3. 전체 검색 (모든 날짜 x 2박3일/3박4일)
#    가는 편·오는 편을 각각 편도로 검색해 합쳐서 왕복 결과를 만든다.
#    (같은 날짜는 한 번만 검색하도록 캐시해서 검색 횟수를 줄인다)
# ================================================================
def _combine(origin, dep_str, ret_str, out_leg, ret_leg):
    """가는 편 + 오는 편 정보를 하나의 왕복 결과 dict로 합친다."""
    total_price = out_leg["price"] + ret_leg["price"]
    return {
        "origin": origin,
        "departure_date": dep_str,
        "return_date": ret_str,
        "total_price": total_price,
        "per_person": round(total_price / config.ADULTS),
        # 가는 편 (origin → 도쿄)
        "out_airline": out_leg["airline"],
        "out_dep": out_leg["dep_time"],
        "out_arr": out_leg["arr_time"],
        "out_dur": out_leg["duration"],
        # 오는 편 (도쿄 → origin)
        "ret_airline": ret_leg["airline"],
        "ret_dep": ret_leg["dep_time"],
        "ret_arr": ret_leg["arr_time"],
        "ret_dur": ret_leg["duration"],
    }


def _search_origin(origin, start, end, search_time, results):
    """한 출발지(부산 또는 인천)에 대해 전체 날짜를 편도 2방향으로 검색."""
    out_cache = {}   # {출국일: 가는 편 최저 dict}  (같은 날 재검색 방지)
    ret_cache = {}   # {귀국일: 오는 편 최저 dict}

    def get_out(date_str):
        if date_str not in out_cache:
            out_cache[date_str] = search_leg(origin, config.DESTINATION, date_str)
            time.sleep(config.SLEEP_BETWEEN_CALLS)
        return out_cache[date_str]

    def get_ret(date_str):
        if date_str not in ret_cache:
            ret_cache[date_str] = search_leg(config.DESTINATION, origin, date_str)
            time.sleep(config.SLEEP_BETWEEN_CALLS)
        return ret_cache[date_str]

    day = start
    while day <= end:
        dep_str = day.isoformat()
        out_leg = get_out(dep_str)
        for nights in config.STAY_OPTIONS:
            ret_str = (day + dt.timedelta(days=nights)).isoformat()
            ret_leg = get_ret(ret_str)
            if out_leg is None or ret_leg is None:
                continue
            info = _combine(origin, dep_str, ret_str, out_leg, ret_leg)
            info["search_time"] = search_time
            info["stay_label"] = config.STAY_LABELS[nights]
            info["nights"] = nights
            results.append(info)
            print(f"  찾음: {info['stay_label']} {dep_str}~{ret_str} "
                  f"가는 편 {info['out_airline']}/오는 편 {info['ret_airline']} "
                  f"{info['total_price']:,}원")
        day += dt.timedelta(days=1)


def run_search():
    """
    출국일 범위 전체를 돌면서, 2박3일 / 3박4일 각각의
    (가는 편 최저 + 오는 편 최저) 합계를 모아 리스트로 돌려준다.
    """
    results = []
    start = dt.date.fromisoformat(config.DEPART_START)
    end = dt.date.fromisoformat(config.DEPART_END)
    search_time = now_kst().strftime("%Y-%m-%d %H:%M:%S")

    # 기본: 부산 출발
    _search_origin(config.ORIGIN, start, end, search_time, results)

    # 결과가 너무 적으면 인천(ICN) 출발도 추가 검색
    if config.INCLUDE_ICN_FALLBACK and len(results) < config.MIN_RESULTS_THRESHOLD:
        print(f"부산 결과가 {len(results)}개로 적어 인천(ICN) 출발도 검색합니다.")
        _search_origin(config.ICN_ORIGIN, start, end, search_time, results)

    return results, search_time


# ================================================================
# 4. CSV 저장
# ================================================================
CSV_HEADER = [
    "검색시각", "일정타입", "출발지", "출국일", "귀국일",
    "가는편항공사", "가는편출발", "가는편도착", "가는편소요",
    "오는편항공사", "오는편출발", "오는편도착", "오는편소요",
    "총가격KRW", "1인가격KRW",
]


def append_to_csv(results):
    """
    검색 결과를 price_history.csv 에 이어 붙인다.
    (예전 파일에는 시간 칸이 없으므로, 읽어서 새 제목줄로 통째로 다시 쓴다.
     이렇게 하면 옛 기록도 그대로 보존되고 칸이 어긋나지 않는다.)
    """
    # 1) 기존 기록 읽어두기 (있으면)
    old_rows = []
    if os.path.exists(config.CSV_FILE):
        with open(config.CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
            old_rows = list(csv.DictReader(f))

    # 2) 새 제목줄로 전체 다시 쓰기 (옛 기록 → 없는 칸은 빈칸으로)
    with open(config.CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER,
                                extrasaction="ignore", restval="")
        writer.writeheader()
        for row in old_rows:
            writer.writerow(row)
        for r in results:
            writer.writerow({
                "검색시각": r["search_time"], "일정타입": r["stay_label"],
                "출발지": r["origin"], "출국일": r["departure_date"],
                "귀국일": r["return_date"],
                "가는편항공사": r["out_airline"], "가는편출발": r["out_dep"],
                "가는편도착": r["out_arr"], "가는편소요": r["out_dur"],
                "오는편항공사": r["ret_airline"], "오는편출발": r["ret_dep"],
                "오는편도착": r["ret_arr"], "오는편소요": r["ret_dur"],
                "총가격KRW": r["total_price"], "1인가격KRW": r["per_person"],
            })


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


def _leg_line(tag, tag_color, airline, dep, arr, a_from, a_to, dur):
    """메일용 한 편(가는/오는) 한 줄 HTML."""
    dur_txt = f" · {dur}" if dur else ""
    return (
        f'<div style="padding:8px 0;border-bottom:1px solid #eee;">'
        f'<span style="display:inline-block;min-width:52px;padding:2px 8px;'
        f'background:{tag_color};color:#fff;border-radius:6px;font-size:12px;'
        f'font-weight:700;">{tag}</span> '
        f'<b>{dep}</b> {a_from} → <b>{arr}</b> {a_to} '
        f'<span style="color:#64748b;">({airline}{dur_txt})</span>'
        f'</div>'
    )


def format_flight_html(r):
    """항공편 한 건(왕복)을 메일용 HTML 조각으로 만든다."""
    link = flight_link(r["origin"], r["departure_date"], r["return_date"])
    origin, dest = r["origin"], config.DESTINATION
    out_line = _leg_line("가는 편", "#2563eb", r["out_airline"],
                         r["out_dep"], r["out_arr"], origin, dest, r["out_dur"])
    ret_line = _leg_line("오는 편", "#0891b2", r["ret_airline"],
                         r["ret_dep"], r["ret_arr"], dest, origin, r["ret_dur"])
    return (
        f'<div style="border:1px solid #e2e8f0;border-radius:10px;padding:14px;'
        f'margin:10px 0;">'
        f'<div style="font-size:13px;color:#64748b;">{r["stay_label"]} · '
        f'{r["departure_date"]} ~ {r["return_date"]}</div>'
        f'{out_line}{ret_line}'
        f'<div style="margin-top:10px;">'
        f'<span style="font-size:20px;font-weight:800;color:#dc2626;">'
        f'1인 {r["per_person"]:,}원</span> '
        f'<span style="color:#64748b;">(성인 {config.ADULTS}명 총 {r["total_price"]:,}원)</span>'
        f'</div>'
        f'<p style="margin:12px 0 0;"><a href="{link}" '
        f'style="display:inline-block;padding:10px 18px;background:#16a34a;'
        f'color:#fff;text-decoration:none;border-radius:8px;font-weight:700;">'
        f'✈️ 예약하러 가기 (네이버 항공)</a></p>'
        f'</div>'
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
                "out_airline": r["out_airline"],
                "ret_airline": r["ret_airline"],
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
