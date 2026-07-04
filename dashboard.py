# -*- coding: utf-8 -*-
"""
========================================================================
대시보드 생성기 (dashboard.py)
------------------------------------------------------------------------
price_history.csv 를 읽어서 웹 페이지(index.html)를 만듭니다.
  · [2박3일] / [3박4일] 탭 2개
  · 각 탭: 역대 최저가(크게) + 날짜별 순위표 + 오름/내림 표시
  · 핸드폰에서 보기 좋게 만든 모바일 친화 디자인
========================================================================
"""

import os
import csv
import html
import datetime as dt
from collections import defaultdict
from urllib.parse import quote

from fast_flights import TFSData, FlightData, Passengers

import config

KST = dt.timezone(dt.timedelta(hours=9))


def flight_link(origin, departure_date, return_date):
    """
    출발지·출국일·귀국일로 '구글 항공권 예약 페이지' 주소를 만든다.
    (거기서 실제 항공사/여행사로 이어서 예약할 수 있습니다.)
    """
    max_stops = 0 if config.NON_STOP else None
    try:
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
        b64 = tfs.as_b64().decode("utf-8")
        return (f"https://www.google.com/travel/flights"
                f"?tfs={quote(b64)}&curr={config.CURRENCY}&hl=ko")
    except Exception:
        # 링크 생성이 실패해도 프로그램 전체는 계속 돌아가도록 일반 검색 주소로 대체
        return "https://www.google.com/travel/flights"


def read_rows():
    """CSV를 읽어 각 줄을 사전(dict) 목록으로 돌려준다."""
    if not os.path.exists(config.CSV_FILE):
        return []
    with open(config.CSV_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            # 숫자로 바꿔서 다루기 쉽게 정리
            try:
                row["총가격KRW"] = int(row["총가격KRW"])
                row["1인가격KRW"] = int(row["1인가격KRW"])
            except (ValueError, KeyError):
                continue
            # 시간 칸은 옛 기록엔 없을 수 있으니 없으면 빈칸으로
            row["가는편출발"] = row.get("가는편출발") or ""
            row["가는편도착"] = row.get("가는편도착") or ""
            row["소요시간"] = row.get("소요시간") or ""
            rows.append(row)
        return rows


def build_tab_data(rows, label):
    """
    특정 일정타입(label)에 대해 대시보드에 필요한 자료를 계산한다.
    반환: (역대최저가 dict 또는 None, 순위표 리스트)
    """
    type_rows = [r for r in rows if r.get("일정타입") == label]
    if not type_rows:
        return None, []

    # ── 역대 최저가 (해당 타입의 모든 기록 중 가장 싼 것) ──
    record = min(type_rows, key=lambda r: r["총가격KRW"])

    # ── 날짜 조합별로 묶기 (출발지+출국일+귀국일) ──
    groups = defaultdict(list)
    for r in type_rows:
        key = (r["출발지"], r["출국일"], r["귀국일"])
        groups[key].append(r)

    ranking = []
    for key, items in groups.items():
        # 검색시각 순으로 정렬 → 마지막이 가장 최근
        items.sort(key=lambda r: r["검색시각"])
        latest = items[-1]
        prev = items[-2] if len(items) >= 2 else None

        # 오름/내림 판단 (마지막 검색 대비)
        if prev is None:
            trend = "new"          # 새로 등장
            diff = 0
        elif latest["총가격KRW"] < prev["총가격KRW"]:
            trend = "down"         # 내림 (좋음)
            diff = prev["총가격KRW"] - latest["총가격KRW"]
        elif latest["총가격KRW"] > prev["총가격KRW"]:
            trend = "up"           # 오름
            diff = latest["총가격KRW"] - prev["총가격KRW"]
        else:
            trend = "same"
            diff = 0

        ranking.append({
            "origin": latest["출발지"],
            "departure": latest["출국일"],
            "return": latest["귀국일"],
            "airline": latest["항공사"],
            "total": latest["총가격KRW"],
            "per_person": latest["1인가격KRW"],
            "dep_time": latest.get("가는편출발", ""),
            "arr_time": latest.get("가는편도착", ""),
            "duration": latest.get("소요시간", ""),
            "trend": trend,
            "diff": diff,
        })

    # 가격 싼 순으로 정렬
    ranking.sort(key=lambda x: x["total"])
    return record, ranking


def trend_badge(trend, diff):
    """오름/내림을 색깔 있는 작은 표시로 만든다."""
    if trend == "down":
        return f'<span class="down">▼ {diff:,}</span>'
    if trend == "up":
        return f'<span class="up">▲ {diff:,}</span>'
    if trend == "new":
        return '<span class="new">NEW</span>'
    return '<span class="same">–</span>'


def render_tab(record, ranking, label):
    """한 탭(2박3일 또는 3박4일)의 HTML 내용을 만든다."""
    if record is None:
        return f'<p class="empty">아직 {html.escape(label)} 검색 결과가 없습니다.</p>'

    # 역대 최저가 강조 카드 (1인당 가격을 크게)
    record_link = flight_link(record['출발지'], record['출국일'], record['귀국일'])
    # 가는 편 시각 줄 (정보가 있을 때만 표시)
    r_dep, r_arr, r_dur = record.get("가는편출발", ""), record.get("가는편도착", ""), record.get("소요시간", "")
    record_time = ""
    if r_dep or r_arr:
        dur_txt = f" · {html.escape(r_dur)}" if r_dur else ""
        record_time = (f"<br>가는 편 {html.escape(r_dep)} → {html.escape(r_arr)}{dur_txt}")
    record_html = f"""
    <div class="record-card">
      <div class="record-title">역대 최저가 ({html.escape(label)}) · 1인당</div>
      <div class="record-price">{record['1인가격KRW']:,}원</div>
      <div class="record-sub">성인 {config.ADULTS}명 총액 {record['총가격KRW']:,}원</div>
      <div class="record-meta">
        {html.escape(record['출발지'])} → {html.escape(config.DESTINATION)}
        · {html.escape(record['항공사'])}<br>
        출국 {html.escape(record['출국일'])} / 귀국 {html.escape(record['귀국일'])}{record_time}
      </div>
      <a class="book-btn" href="{html.escape(record_link)}" target="_blank" rel="noopener">✈️ 예약하러 가기 (구글 항공권)</a>
    </div>
    """

    # 순위표 (각 줄 = 날짜 조합 하나)
    rows_html = ""
    for i, r in enumerate(ranking, start=1):
        link = flight_link(r['origin'], r['departure'], r['return'])
        # 가는 편 시각 (있을 때만)
        tm = ""
        if r.get("dep_time") or r.get("arr_time"):
            tm = f'<br><span class="tm">가는 편 {html.escape(r.get("dep_time",""))} → {html.escape(r.get("arr_time",""))}</span>'
        rows_html += f"""
        <tr>
          <td class="rank">{i}</td>
          <td>{html.escape(r['departure'])}<br><span class="ret">↩ {html.escape(r['return'])}</span></td>
          <td>{html.escape(r['origin'])}<br><span class="air">{html.escape(r['airline'])}</span>{tm}</td>
          <td class="price">1인 {r['per_person']:,}원<br><span class="pp">총 {r['total']:,}</span></td>
          <td class="trend">{trend_badge(r['trend'], r['diff'])}</td>
          <td><a class="book-link" href="{html.escape(link)}" target="_blank" rel="noopener">예약</a></td>
        </tr>
        """

    table_html = f"""
    <table>
      <thead>
        <tr>
          <th>#</th><th>출국일 / 귀국일</th><th>출발/항공사</th>
          <th>가격</th><th>추이</th><th>예약</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    """
    return record_html + table_html


def build_dashboard():
    """index.html 파일을 새로 만든다."""
    rows = read_rows()
    updated = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    labels = list(config.STAY_LABELS.values())  # ["2박3일", "3박4일"]

    # 각 탭 내용 만들기
    tab_contents = []
    for i, label in enumerate(labels):
        record, ranking = build_tab_data(rows, label)
        active = "active" if i == 0 else ""
        tab_contents.append(
            f'<div class="tab-content {active}" id="tab{i}">'
            f'{render_tab(record, ranking, label)}</div>'
        )

    # 탭 버튼 만들기
    tab_buttons = ""
    for i, label in enumerate(labels):
        active = "active" if i == 0 else ""
        tab_buttons += (
            f'<button class="tab-btn {active}" onclick="showTab({i})" '
            f'id="btn{i}">{html.escape(label)}</button>'
        )

    page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>부산 ↔ 도쿄 항공권 최저가</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    margin: 0; background: #f2f4f7; color: #1a1a2e;
    -webkit-text-size-adjust: 100%;
  }}
  header {{
    background: linear-gradient(135deg, #2563eb, #1e40af);
    color: #fff; padding: 20px 16px; text-align: center;
  }}
  header h1 {{ margin: 0; font-size: 20px; }}
  header p {{ margin: 6px 0 0; font-size: 13px; opacity: .9; }}
  .wrap {{ max-width: 720px; margin: 0 auto; padding: 12px; }}
  .tabs {{ display: flex; gap: 8px; margin: 12px 0; }}
  .tab-btn {{
    flex: 1; padding: 12px; font-size: 16px; border: none; border-radius: 10px;
    background: #e2e8f0; color: #475569; font-weight: 700; cursor: pointer;
  }}
  .tab-btn.active {{ background: #2563eb; color: #fff; }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
  .record-card {{
    background: #fff; border-radius: 16px; padding: 20px; text-align: center;
    box-shadow: 0 2px 10px rgba(0,0,0,.06); margin-bottom: 16px;
    border: 2px solid #2563eb;
  }}
  .record-title {{ font-size: 13px; color: #64748b; font-weight: 600; }}
  .record-price {{ font-size: 38px; font-weight: 800; color: #dc2626; margin: 6px 0; }}
  .record-sub {{ font-size: 13px; color: #475569; }}
  .record-meta {{ font-size: 13px; color: #334155; margin-top: 10px; line-height: 1.6; }}
  .book-btn {{
    display: inline-block; margin-top: 14px; padding: 12px 20px;
    background: #16a34a; color: #fff; text-decoration: none;
    border-radius: 10px; font-weight: 700; font-size: 15px;
  }}
  .book-link {{
    display: inline-block; padding: 6px 12px; background: #16a34a;
    color: #fff; text-decoration: none; border-radius: 8px;
    font-weight: 700; font-size: 12px;
  }}
  table {{
    width: 100%; border-collapse: collapse; background: #fff;
    border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,.05);
  }}
  th, td {{ padding: 10px 8px; text-align: center; font-size: 13px; border-bottom: 1px solid #eef2f6; }}
  th {{ background: #f8fafc; color: #64748b; font-size: 12px; }}
  td.rank {{ font-weight: 800; color: #2563eb; }}
  td.price {{ font-weight: 700; }}
  .ret, .air, .pp {{ font-size: 11px; color: #94a3b8; }}
  .tm {{ font-size: 11px; color: #2563eb; }}
  .down {{ color: #16a34a; font-weight: 700; }}
  .up {{ color: #dc2626; font-weight: 700; }}
  .new {{ color: #2563eb; font-weight: 700; font-size: 11px; }}
  .same {{ color: #94a3b8; }}
  .empty {{ text-align: center; color: #94a3b8; padding: 40px 0; }}
  footer {{ text-align: center; color: #94a3b8; font-size: 12px; padding: 20px; }}
</style>
</head>
<body>
<header>
  <h1>✈️ {html.escape(config.ORIGIN)} ↔ {html.escape(config.DESTINATION)} 왕복 직항 최저가</h1>
  <p>성인 {config.ADULTS}명 · 이코노미 · 마지막 업데이트 {updated} (KST)</p>
</header>
<div class="wrap">
  <div class="tabs">{tab_buttons}</div>
  {''.join(tab_contents)}
</div>
<footer>구글 항공권 기반 · 하루 3회 자동 갱신</footer>
<script>
  function showTab(n) {{
    var contents = document.getElementsByClassName('tab-content');
    var btns = document.getElementsByClassName('tab-btn');
    for (var i = 0; i < contents.length; i++) {{
      contents[i].classList.remove('active');
      btns[i].classList.remove('active');
    }}
    document.getElementById('tab' + n).classList.add('active');
    document.getElementById('btn' + n).classList.add('active');
  }}
</script>
</body>
</html>
"""

    with open(config.HTML_FILE, "w", encoding="utf-8") as f:
        f.write(page)


# 직접 실행하면 (테스트용) 대시보드만 만든다
if __name__ == "__main__":
    build_dashboard()
    print(f"{config.HTML_FILE} 생성 완료")
