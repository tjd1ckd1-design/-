# -*- coding: utf-8 -*-
"""
law_fetch.py
------------
국가법령정보센터(law.go.kr) Open API에서, 관심 분야별로 "현재 시행 중인"
법령 목록을 가져와 data.json의 laws[] 항목으로 채웁니다.

이 사이트는 법안(국회, 심의중)·국정과제(정부, 5개년 계획)에 이어
"이미 확정되어 지금 실제로 적용되고 있는 법"까지 다루기 위해 이 스크립트를
추가했습니다.

※ 왜 검색 기능이 아니라 목록만 가져오나요?
   법령 전체는 6,000건이 넘고, 사람이 언제 어떤 검색어를 입력할지 미리 알 수
   없어서, 국회 API 때처럼 "매일 정해진 키워드로 목록만 미리 받아두고, 자세한
   내용은 법령정보센터 원문으로 연결"하는 방식을 택했습니다. 이미 시행 중인
   법은 자주 바뀌지 않아서 이 방식으로도 충분합니다.

사용법
------
1) https://open.law.go.kr 회원가입 → 로그인 시 사용하는 아이디가 그대로
   API 인증값(OC)입니다. 별도 승인 절차 없이 바로 쓸 수 있는 경우가 많습니다.
2) 아래 API_OC 에 그 아이디를 넣거나, 환경변수 LAW_API_OC 로 설정합니다.
3) pip install requests
4) python law_fetch.py
"""

import json
import os
import time
import sys
import datetime
import requests

_PLACEHOLDER = "여기에_발급받은_OC_아이디를_입력하세요"
API_OC = os.environ.get("LAW_API_OC", _PLACEHOLDER)

BASE_URL = "https://www.law.go.kr/DRF/lawSearch.do"

# 관심 분야별 검색 키워드. 필요하면 자유롭게 추가/수정하세요.
# (category, 검색어, 분야당 최대 수집 건수)
LAW_TOPICS = [
    ("부동산", "부동산", 15),
    ("노동", "근로", 15),
    ("환경", "환경보전", 15),
    ("복지", "사회보장", 15),
    ("교육", "교육", 15),
    ("안전", "안전관리", 15),
    ("개인정보", "개인정보", 15),
    ("소비자", "소비자보호", 15),
    ("주거", "주택", 15),
    ("세금", "조세", 15),
    ("저작권", "저작권", 15),
    ("교통", "교통안전", 15),
    ("의료·보건", "보건의료", 15),
    ("식품", "식품안전", 15),
    ("동물보호", "동물보호", 10),
    ("문화재", "문화재보호", 10),
    ("정보통신", "정보통신", 15),
    ("금융", "금융소비자", 15),
    ("전자상거래", "전자상거래", 10),
    ("관광", "관광진흥", 10),
    ("체육", "국민체육", 10),
    ("아동", "아동복지", 15),
    ("장애인", "장애인복지", 15),
    ("고령자", "노인복지", 15),
    ("다문화·이민", "다문화가족", 10),
    ("재난안전", "재난관리", 15),
    ("에너지", "에너지", 15),
    ("농업", "농업", 15),
    ("수산업", "수산업", 10),
    ("지식재산권", "특허", 10),
    ("공정거래", "공정거래", 15),
    ("산림·자연환경", "백두대간", 3),  # 예시로 문의주신 주제 포함
]


def fetch_law_list(query: str, display: int = 10):
    """OC=test 로도 동작이 확인된 검색 API. 실 서비스에서는 반드시 본인 OC를 쓰세요."""
    if API_OC == _PLACEHOLDER:
        print("[안내] LAW_API_OC가 설정되지 않아 실제 호출을 생략합니다.")
        return []

    params = {
        "OC": API_OC,
        "target": "law",
        "type": "JSON",
        "query": query,
        "display": display,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"  → 요청 실패: {e}")
        return []
    except ValueError:
        print("  → 응답이 JSON 형식이 아닙니다 (OC 값을 확인해주세요).")
        return []

    laws = data.get("LawSearch", {}).get("law", [])
    if isinstance(laws, dict):  # 결과가 1건이면 dict로 오는 경우가 있어 리스트로 통일
        laws = [laws]
    return laws


def fmt_date(yyyymmdd: str) -> str:
    if not yyyymmdd or len(yyyymmdd) != 8:
        return yyyymmdd or ""
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def map_law(row: dict, category: str, idx: int) -> dict:
    title = row.get("법령명한글", "")
    # 법령/{법령명} 형태의 공개 URL은 인증키 없이도 누구나 접근 가능 (직접 확인함)
    source_url = "https://www.law.go.kr/법령/" + title.replace(" ", "%20")

    return {
        "id": f"law_auto_{idx}",
        "kind": "law",
        "title": title,
        "category": category,
        "status": "implemented",
        "lawType": row.get("법령구분명", ""),
        "ministry": row.get("소관부처명", "").split(",")[0] if row.get("소관부처명") else "미확인",
        "effectiveDate": fmt_date(row.get("시행일자", "")),
        "promulgateDate": fmt_date(row.get("공포일자", "")),
        "sourceUrl": source_url,
    }


def main():
    print("=" * 60)
    print("국가법령정보센터 Open API → data.json (laws) 변환 스크립트")
    print("=" * 60)

    all_laws = []
    seen_titles = set()

    for category, query, limit in LAW_TOPICS:
        print(f"[{category}] '{query}' 검색 중...")
        rows = fetch_law_list(query, display=limit * 2)  # 여유있게 받아서 필터링
        kept = 0
        for row in rows:
            if row.get("현행연혁코드") != "현행":
                continue  # 폐지·개정 전 이력은 제외, "현재 시행 중"인 것만
            title = row.get("법령명한글", "")
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            all_laws.append(map_law(row, category, len(all_laws)))
            kept += 1
            if kept >= limit:
                break
        print(f"  → {kept}건 채택")
        time.sleep(0.3)

    print(f"\n총 {len(all_laws)}건의 현행 법령 수집")

    if not all_laws:
        print("[안내] 수집된 법령이 없어 data.json을 변경하지 않습니다.")
        return

    existing = {}
    if os.path.exists("data.json"):
        try:
            with open("data.json", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing["laws"] = all_laws
    existing["lawsUpdatedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print("-" * 60)
    print(f"완료: laws {len(all_laws)}건 → data.json 저장 (bills/policies는 보존)")


if __name__ == "__main__":
    sys.exit(main())
