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
ASSEMBLY_UNIT = "22"                    # 대수 (22대 국회)
PAGE_SIZE = 100
MAX_PAGES = 5                           # 필요시 늘리세요 (요청 제한에 유의)


def fetch_page(service_id: str, page_index: int, extra_params: dict | None = None):
    """Open API 공통 호출 함수. Type=json 고정."""
    params = {
        "KEY": API_KEY,
        "Type": "json",
        "pIndex": page_index,
        "pSize": PAGE_SIZE,
    }
    if extra_params:
        params.update(extra_params)

    url = f"{BASE_URL}/{service_id}"
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # 오류 응답 형식: {"RESULT": {"CODE": "ERROR-290", "MESSAGE": "..."}}
    if "RESULT" in data:
        code = data["RESULT"].get("CODE", "")
        msg = data["RESULT"].get("MESSAGE", "")
        raise RuntimeError(f"API 오류 {code}: {msg}")

    return data


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
           data = fetch_page(BILL_SERVICE_ID, page)
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

BILL_STAGE_KEYWORDS = [
    ("공포", 6), ("정부이송", 6),
    ("본회의", 4),   # 부의/의결 등 본회의 관련 텍스트가 있으면 4단계 이상으로 취급
    ("법사위", 3), ("체계자구", 3),
    ("소관위", 2), ("상임위", 2),
    ("접수", 0),
]


def guess_bill_stage(proc_stage_text: str) -> int:
    text = proc_stage_text or ""
    for keyword, stage in BILL_STAGE_KEYWORDS:
        if keyword in text:
            return stage
    return 0  # 기본값: 접수 단계


def guess_status(proc_result_text: str, stage: int) -> str:
    text = proc_result_text or ""
    if any(k in text for k in ["가결", "공포", "제정", "개정"]):
        return "done"
    if any(k in text for k in ["부결", "폐기", "철회"]):
        return "dropped"
    if stage >= 4:
        return "floor"
    return "progress"


def map_bill(row: dict, idx: int) -> dict:
    """
    ALLBILLV2 원본 row를 웹페이지 스키마로 변환.
    아래 get() 후보 키들은 국회 의안 API 계열에서 흔히 쓰이는 이름을 나열한 것으로,
    실제 응답을 열어보고 정확한 키로 교체해야 합니다.
    """
    def pick(*keys, default=""):
        for k in keys:
            if k in row and row[k]:
                return row[k]
        return default

    bill_name = pick("BILL_NAME", "BILL_NM", "billName")
    bill_no = pick("BILL_NO", "billNo")
    proposer = pick("PROPOSER", "PROPOSE_KND", "proposer")
    propose_dt = pick("PROPOSE_DT", "proposeDt")
    committee = pick("COMMITTEE", "CURR_COMMITTEE", "committee")
    proc_stage_text = pick("PROC_STAGE_CD", "CURR_STAGE", "procStage")
    proc_result_text = pick("PROC_RESULT_CD", "PROC_RESULT", "procResult")
    link_url = pick("LINK_URL", "DETAIL_URL", "detailLink")

    stage = guess_bill_stage(proc_stage_text)
    status = guess_status(proc_result_text, stage)

    reason_text = pick("BILL_SUMMARY", "PROPOSE_REASON", "SUMMARY")
    # 주요내용이 줄바꿈이나 번호로 구분되어 오는 경우가 많아 대략적으로 나눠봅니다.
    # 실제 응답 형식을 보고 조정하는 것을 권장합니다.
    key_points_raw = pick("MAIN_CONTENT", "KEY_POINTS")
    key_points = [s.strip("-· ") for s in key_points_raw.split("\n") if s.strip()] if key_points_raw else []

    return {
        "id": f"b_auto_{idx}",
        "kind": "bill",
        "title": bill_name or "(제목 미확인 - 필드명 확인 필요)",
        "category": "미분류",
        "status": status,
        "billNo": bill_no,
        "proposer": proposer,
        "proposeDate": propose_dt,
        "committee": committee or "미확인",
        "summary": pick("BILL_SUMMARY", "SUMMARY", default="(요약 필드 미확인 - map_bill() 조정 필요)"),
        "reason": reason_text,
        "keyPoints": key_points,
        "history": [],  # 심사 경과 이력은 별도 API(BILLJUDGE 등) 조회가 필요해 기본값은 비워둡니다.
        "billStage": stage,
        "sourceUrl": link_url,
        "raw": row,  # 디버깅용: 실제 서비스에서는 제거해도 됩니다.
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
