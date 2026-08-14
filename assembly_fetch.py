# -*- coding: utf-8 -*-
"""
assembly_fetch.py
------------------
국회 "열린국회정보" Open API에서 실제 법안(의안) 데이터를 가져와,
index.html이 그대로 읽을 수 있는 data.json으로 변환합니다.

이 사이트는 "국가는 지금 어디로 가고 있나"에 집중하기 위해 법안(국회)과
국정과제(정부, policy_fetch.py 담당)만 자동 추적합니다. 청원 데이터는
Open API가 아니라 로그인 브라우저에서만 받아지는 파일 다운로드 방식이라
자동화 대상에서 제외했습니다.

※ 왜 브라우저(JS)가 아니라 파이썬 스크립트로 받아오나요?
   open.assembly.go.kr API는 브라우저 간 요청(CORS)을 허용하지 않습니다.
   실제로 다음과 같이 직접 확인했습니다:
     curl -I -H "Origin: https://example.com" https://open.assembly.go.kr/portal/openapi/ALLBILLV2...
     → Access-Control-Allow-Origin 헤더 없음 (브라우저 fetch 차단됨)
   그래서 이 스크립트를 로컬/서버(GitHub Actions)에서 실행해 JSON 파일을 만들고,
   웹페이지는 그 data.json을 접속할 때마다 자동으로 읽습니다.

사용법 (로컬에서 직접 실행)
------
1) https://open.assembly.go.kr 회원가입 → 마이페이지 > Open API > 인증키 발급 (무료)
2) 아래 API_KEY 에 발급받은 키를 넣거나, 환경변수 ASSEMBLY_API_KEY 로 설정합니다.
3) pip install requests
4) python assembly_fetch.py
5) 같은 폴더에 생성된 data.json 을 웹페이지의 "데이터 불러오기" 버튼으로 불러오세요.

사용법 (GitHub Actions로 매일 자동 갱신 — 온라인 배포용)
------
같은 세트로 받은 README.md와 update-data.yml을 참고하세요.
저장소 Settings > Secrets 에 ASSEMBLY_API_KEY 를 등록해두면, 이 스크립트가
매일 정해진 시각에 자동 실행되어 data.json을 새로 만들고 그대로 커밋합니다.

주의
----
이 스크립트가 만드는 분류(카테고리/진행단계)는 API 원본 필드를 바탕으로 한
"최선의 추정" 규칙입니다. 실제 서비스로 쓰기 전에 원본 응답(raw_bills_sample.json)을
직접 열어 필드명을 확인하고, map_bill() 함수의 필드명을 필요에 맞게 조정해 주세요.
(Open API 상세 페이지의 "명세서 다운로드"에서 정확한 필드 정의를 확인할 수 있습니다.)
"""

import json
import os
import time
import sys
import datetime
import requests

# ============================================================
# 설정
# ============================================================
# 환경변수 ASSEMBLY_API_KEY가 설정되어 있으면 그 값을 우선 사용합니다.
# (GitHub Actions 등 CI에서는 저장소 Secret으로 이 환경변수를 주입합니다.)
_PLACEHOLDER = "여기에_발급받은_인증키를_입력하세요"
API_KEY = os.environ.get("ASSEMBLY_API_KEY", _PLACEHOLDER)

# 실제로 존재가 확인된 엔드포인트 (2026-08 기준, curl로 검증됨)
BASE_URL = "https://open.assembly.go.kr/portal/openapi"
BILL_SERVICE_ID = "ALLBILLV2"          # 의안정보 통합 API
ASSEMBLY_ERACO = "제22대"               # 대수 — ALLBILLV2의 실제 필수 파라미터명은 ERACO이며,
# 값 형식은 '제22대'처럼 "제"+숫자+"대" 문자열이어야 합니다.
# (요청인자 표에서 직접 확인: ERACO='제22대')
PAGE_SIZE = 100
MAX_PAGES = 5                           # 필요시 늘리세요 (요청 제한에 유의)


def fetch_page(service_id: str, page_index: int, extra_params: dict | None = None):
    """Open API 공통 호출 함수. Type=json 고정.
    GitHub Actions 등 해외 데이터센터 IP에서 연결이 간헐적으로 막히는 경우를
    고려해, 타임아웃을 늘리고 짧게 재시도합니다."""
    params = {
        "KEY": API_KEY,
        "Type": "json",
        "pIndex": page_index,
        "pSize": PAGE_SIZE,
    }
    if extra_params:
        params.update(extra_params)

    url = f"{BASE_URL}/{service_id}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    last_error = None
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # 오류 응답 형식: {"RESULT": {"CODE": "ERROR-290", "MESSAGE": "..."}}
            if "RESULT" in data:
                code = data["RESULT"].get("CODE", "")
                msg = data["RESULT"].get("MESSAGE", "")
                raise RuntimeError(f"API 오류 {code}: {msg}")

            return data
        except requests.exceptions.ConnectTimeout as e:
            last_error = e
            print(f"  ⚠ 연결 시간 초과 (시도 {attempt}/3). 5초 후 재시도...")
            time.sleep(5)
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"  ⚠ 요청 실패 (시도 {attempt}/3): {e}. 5초 후 재시도...")
            time.sleep(5)

    raise RuntimeError(
        f"3번 재시도했지만 계속 연결에 실패했습니다: {last_error}\n"
        "   → open.assembly.go.kr 서버가 이 실행 환경(GitHub Actions)의 IP를 "
        "차단하고 있을 가능성이 있습니다. 아래 assembly_fetch.py 상단 안내의 "
        "'로컬에서 직접 실행' 방법을 시도해보세요."
    )


def fetch_all_bills():
    """ALLBILLV2 전체 페이지를 가져와 원본 row 리스트를 반환."""
    if API_KEY == _PLACEHOLDER:
        print("[안내] API_KEY가 설정되지 않아 실제 호출을 생략합니다.")
        print("       open.assembly.go.kr 에서 키를 발급받은 뒤 스크립트 상단에 입력해주세요.")
        return []

    all_rows = []
    for page in range(1, MAX_PAGES + 1):
        print(f"[의안정보] {page}페이지 요청 중...")
        try:
            data = fetch_page(BILL_SERVICE_ID, page, {"ERACO": ASSEMBLY_ERACO})
        except RuntimeError as e:
            print(f"  → 중단: {e}")
            break

        # 응답 구조: {"ALLBILLV2": [ {"head":[...]}, {"row":[ {...}, {...} ]} ]}
        rows = []
        for block in data.get(BILL_SERVICE_ID, []):
            if "row" in block:
                rows = block["row"]

        if not rows:
            print("  → 더 이상 데이터 없음, 종료")
            break

        all_rows.extend(rows)
        time.sleep(0.3)  # 서버 부담을 줄이기 위한 짧은 대기

    print(f"[의안정보] 총 {len(all_rows)}건 수집")
    return all_rows


# ============================================================
# 원본 API 필드 → 웹페이지가 쓰는 스키마로 변환
# (필드명은 실제 raw_bills_sample.json을 열어 확인 후 조정하세요)
# ============================================================

# 소관위원회명 → 사이트 분야(category) 매핑.
# ALLBILLV2에는 별도 "분야" 필드가 없어서, 실제로 존재하는 소관위원회명(JRCMIT_NM)으로
# 최대한 합리적인 분야를 추정합니다. 목록에 없는 위원회는 "기타"로 남습니다.
COMMITTEE_CATEGORY_MAP = {
    "기획재정위원회": "경제", "정무위원회": "경제", "산업통상자원중소벤처기업위원회": "경제",
    "환경노동위원회": "노동", "고용노동": "노동",
    "국토교통위원회": "주거", "농림축산식품해양수산위원회": "농림수산",
    "보건복지위원회": "복지", "여성가족위원회": "복지",
    "교육위원회": "교육", "문화체육관광위원회": "문화",
    "법제사법위원회": "사법", "행정안전위원회": "행정",
    "과학기술정보방송통신위원회": "과학기술", "국방위원회": "안보",
    "외교통일위원회": "외교", "정보위원회": "안보",
}


def infer_category(committee: str) -> str:
    for key, cat in COMMITTEE_CATEGORY_MAP.items():
        if key in (committee or ""):
            return cat
    return "기타"


def determine_stage_and_status(row: dict):
    """개별 텍스트 키워드보다, 각 단계의 날짜 필드가 채워져 있는지(=그 단계를
    실제로 통과했는지)를 보는 게 훨씬 정확합니다. 뒤 단계부터 역순으로 확인합니다."""

    def has(*keys):
        return any((row.get(k) or "").strip() for k in keys)

    # 공포까지 완료
    if has("PROM_DT"):
        return 6, "done"

    # 본회의 의결까지 완료 — 가결/부결 여부 확인
    if has("RGS_RSLN_DT"):
        result = (row.get("RGS_CONF_RSLT") or "")
        if any(k in result for k in ["부결", "폐기"]):
            return 5, "dropped"
        return 5, "done"

    # 본회의에 부의(상정)된 상태
    if has("RGS_PRSNT_DT"):
        return 4, "floor"

    # 법사위 체계자구심사 단계
    if has("LAW_PROC_DT", "LAW_PRSNT_DT", "LAW_CMMT_DT"):
        return 3, "floor"

    # 소관위 심사 완료 — 가결/폐기 여부 확인
    if has("JRCMIT_PROC_DT"):
        result = (row.get("JRCMIT_PROC_RSLT") or "")
        if any(k in result for k in ["부결", "폐기"]):
            return 2, "dropped"
        return 2, "progress"

    # 소관위에 상정만 된 상태
    if has("JRCMIT_PRSNT_DT"):
        return 1, "progress"

    # 소관위 회부까지만 된 상태 (접수 직후)
    if has("JRCMIT_CMMT_DT"):
        return 1, "progress"

    return 0, "progress"


def map_bill(row: dict, idx: int) -> dict:
    """ALLBILLV2 원본 row를 웹페이지 스키마로 변환.
    아래 필드명은 실제 raw_bills_sample.json 응답을 직접 확인해 확정한 값입니다."""

    bill_name = row.get("BILL_NM", "")
    bill_no = row.get("BILL_NO", "")
    proposer = row.get("PPSR_NM", "")
    proposer_kind = row.get("PPSR_KND", "")
    propose_dt = row.get("PPSL_DT", "")
    committee = row.get("JRCMIT_NM", "") or "미확인"
    link_url = row.get("LINK_URL", "")

    stage, status = determine_stage_and_status(row)
    category = infer_category(committee)

    # 이 API에는 제안이유·주요내용 같은 서술형 요약 필드가 아예 없습니다.
    # 자연스러운 문장(조사 이/가 처리)은 오류 여지가 있어, 라벨 형식으로 안전하게 구성합니다.
    if proposer:
        summary = f"제안자: {proposer} · 소관위원회: {committee}"
    else:
        summary = f"소관위원회: {committee}"

    # 실제로 값이 채워진 날짜 필드만으로 심사 경과를 구성합니다.
    # label은 단계명(BILL_STAGES)과 중복되지 않도록, 추가 정보가 있을 때만 채웁니다.
    history = []
    if propose_dt:
        history.append({"stage": 0, "date": propose_dt, "label": ""})
    if row.get("JRCMIT_CMMT_DT"):
        history.append({"stage": 1, "date": row["JRCMIT_CMMT_DT"], "label": ""})
    if row.get("JRCMIT_PROC_DT"):
        result = row.get("JRCMIT_PROC_RSLT") or ""
        history.append({"stage": 2, "date": row["JRCMIT_PROC_DT"], "label": result})
    if row.get("LAW_PROC_DT"):
        result = row.get("LAW_PROC_RSLT") or ""
        history.append({"stage": 3, "date": row["LAW_PROC_DT"], "label": result})
    if row.get("RGS_PRSNT_DT"):
        history.append({"stage": 4, "date": row["RGS_PRSNT_DT"], "label": ""})
    if row.get("RGS_RSLN_DT"):
        history.append({"stage": 5, "date": row["RGS_RSLN_DT"], "label": row.get("RGS_CONF_RSLT") or ""})
    if row.get("PROM_DT"):
        history.append({"stage": 6, "date": row["PROM_DT"], "label": ""})

    return {
        "id": f"b_auto_{idx}",
        "kind": "bill",
        "title": bill_name or "(제목 미확인)",
        "category": category,
        "status": status,
        "billNo": bill_no,
        "proposer": f"{proposer}({proposer_kind})" if proposer and proposer_kind else (proposer or proposer_kind or "미확인"),
        "proposeDate": propose_dt,
        "committee": committee,
        "summary": summary,
        "reason": "",
        "keyPoints": [],
        "history": history,
        "billStage": stage,
        "sourceUrl": link_url,
    }


def main():
    print("=" * 60)
    print("국회 열린국회정보 Open API → data.json 변환 스크립트")
    print("=" * 60)

    bill_rows = fetch_all_bills()

    # 디버깅용 원본 저장 (필드명 확인할 때 유용)
    if bill_rows:
        with open("raw_bills_sample.json", "w", encoding="utf-8") as f:
            json.dump(bill_rows[:3], f, ensure_ascii=False, indent=2)
        print("→ raw_bills_sample.json 에 원본 응답 3건 저장 (필드명 확인용)")

    # 안전장치: 이번에 아무 데이터도 못 받아왔다면(예: 키 미설정, 일시적 API 오류)
    # 기존 data.json을 건드리지 않고 그대로 종료합니다.
    if not bill_rows:
        print("\n[안내] 이번 실행에서 새 데이터를 받아오지 못해 data.json을 변경하지 않습니다.")
        print("       키를 넣고 다시 실행하면 실제 데이터를 받아옵니다.")
        return

    bills = [map_bill(r, i) for i, r in enumerate(bill_rows)]

    # 기존 data.json을 읽어와 병합합니다. 이 스크립트는 bills 키만 책임지고,
    # policies 등 다른 스크립트(policy_fetch.py)가 관리하는 키는 그대로
    # 보존합니다. (여러 자동 수집 스크립트가 같은 파일을 나눠 쓰는 구조)
    existing = {}
    if os.path.exists("data.json"):
        try:
            with open("data.json", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    output = dict(existing)
    output["bills"] = bills
    output["isSampleData"] = False
    output["generatedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("-" * 60)
    print(f"완료: bills {len(bills)}건 → data.json 저장 (policies 등 기존 항목은 보존)")


if __name__ == "__main__":
    sys.exit(main())
