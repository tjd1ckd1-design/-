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
"""

import json
import os
import time
import sys
import datetime
import requests

_PLACEHOLDER = "여기에_발급받은_인증키를_입력하세요"
API_KEY = os.environ.get("ASSEMBLY_API_KEY", _PLACEHOLDER)

BASE_URL = "https://open.assembly.go.kr/portal/openapi"
BILL_SERVICE_ID = "ALLBILLV2"
PAGE_SIZE = 100
MAX_PAGES = 5


def fetch_page(service_id: str, page_index: int, extra_params: dict | None = None):
    """Open API 공통 호출 함수. GitHub Actions 등 해외 데이터센터 IP에서
    연결이 간헐적으로 막히는 경우를 고려해, 타임아웃을 늘리고 재시도합니다."""
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
        "차단하고 있을 가능성이 있습니다."
    )


def fetch_all_bills():
    if API_KEY == _PLACEHOLDER:
        print("[안내] API_KEY가 설정되지 않아 실제 호출을 생략합니다.")
        return []

    all_rows = []
    for page in range(1, MAX_PAGES + 1):
        print(f"[의안정보] {page}페이지 요청 중...")
        try:
            data = fetch_page(BILL_SERVICE_ID, page)
        except RuntimeError as e:
            print(f"  → 중단: {e}")
            break

        rows = []
        for block in data.get(BILL_SERVICE_ID, []):
            if "row" in block:
                rows = block["row"]

        if not rows:
            print("  → 더 이상 데이터 없음, 종료")
            break

        all_rows.extend(rows)
        time.sleep(0.3)

    print(f"[의안정보] 총 {len(all_rows)}건 수집")
    return all_rows


BILL_STAGE_KEYWORDS = [
    ("공포", 6), ("정부이송", 6),
    ("본회의", 4),
    ("법사위", 3), ("체계자구", 3),
    ("소관위", 2), ("상임위", 2),
    ("접수", 0),
]


def guess_bill_stage(proc_stage_text: str) -> int:
    text = proc_stage_text or ""
    for keyword, stage in BILL_STAGE_KEYWORDS:
        if keyword in text:
            return stage
    return 0


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
        "summary": pick("BILL_SUMMARY", "SUMMARY", default="(요약 필드 미확인)"),
        "reason": reason_text,
        "keyPoints": key_points,
        "history": [],
        "billStage": stage,
        "sourceUrl": link_url,
        "raw": row,
    }


def main():
    print("=" * 60)
    print("국회 열린국회정보 Open API → data.json 변환 스크립트")
    print("=" * 60)

    bill_rows = fetch_all_bills()

    if bill_rows:
        with open("raw_bills_sample.json", "w", encoding="utf-8") as f:
            json.dump(bill_rows[:3], f, ensure_ascii=False, indent=2)
        print("→ raw_bills_sample.json 에 원본 응답 3건 저장")

    if not bill_rows:
        print("\n[안내] 새 데이터를 받아오지 못해 data.json을 변경하지 않습니다.")
        return

    bills = [map_bill(r, i) for i, r in enumerate(bill_rows)]

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
    print(f"완료: bills {len(bills)}건 → data.json 저장")


if __name__ == "__main__":
    sys.exit(main())
