# -*- coding: utf-8 -*-
"""
policy_fetch.py
----------------
"대한민국 정책브리핑"이 공공데이터포털에 공개한 정책뉴스 Open API에서
국정과제·정책 항목과 관련된 최신 보도자료/뉴스를 찾아 data.json의
policies[].relatedNews 에 덧붙입니다.

※ 이 스크립트가 하는 일과 하지 않는 일 (중요)
   - 국회 의안 API(ALLBILLV2)와 달리, 정책뉴스 API는 "이 정책이 지금
     몇 번째 단계인지"를 알려주는 구조화된 데이터가 아니라 낱개의
     보도자료 기사 목록입니다.
   - 그래서 이 스크립트는 policyStage(추진 단계)나 keyPoints(주요내용)를
     자동으로 바꾸지 않습니다. 그걸 자동으로 바꾸려면 "이 기사가 어느
     단계에 해당하는지" 판단이 필요한데, 그 판단을 스크립트가 대신하면
     오히려 부정확한 내용이 조용히 섞여 들어갈 위험이 있기 때문입니다.
   - 대신 각 정책 항목에 관련 키워드로 검색된 최신 기사 제목·날짜·링크만
     "관련 최신 뉴스"로 추가합니다. 원문은 사람이 직접 확인할 수 있고,
     제가(또는 사용자가) 필요하면 그 내용을 보고 keyPoints/history를
     수동으로 업데이트하는 흐름을 권장합니다.

사용법
------
1) https://www.data.go.kr 회원가입 → "문화체육관광부_정책브리핑_정책뉴스_API"
   활용신청 (자동승인, 즉시 발급)
2) 발급받은 서비스키를 DATA_GO_KR_API_KEY 환경변수로 설정하거나 아래 API_KEY에 입력
3) pip install requests
4) python policy_fetch.py
   (반드시 data.json이 있는 폴더에서 실행해야 기존 petitions/bills를 보존합니다)
"""

import json
import os
import sys
import time
import datetime
import requests

_PLACEHOLDER = "여기에_data.go.kr_서비스키를_입력하세요"
API_KEY = os.environ.get("DATA_GO_KR_API_KEY", _PLACEHOLDER)

# 실제로 존재가 확인된 엔드포인트 (문화체육관광부_정책브리핑_정책뉴스_API, data.go.kr 15095335)
BASE_URL = "http://apis.data.go.kr/1371000/policyNewsService/policyNewsList"
NUM_OF_ROWS = 30
MAX_PAGES = 3
NEWS_PER_POLICY = 3          # 정책 항목당 보관할 최신 기사 수
LOOKBACK_DAYS = 90           # 이 기간 이내 기사만 관련 뉴스로 채택


def fetch_page(page_no: int):
    params = {
        "serviceKey": API_KEY,
        "pageNo": page_no,
        "numOfRows": NUM_OF_ROWS,
        "type": "json",
    }
    resp = requests.get(BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_recent_articles():
    """최근 정책뉴스 기사를 모아옵니다. 실패하거나 키가 없으면 빈 리스트."""
    if API_KEY == _PLACEHOLDER:
        print("[안내] DATA_GO_KR_API_KEY가 설정되지 않아 실제 호출을 생략합니다.")
        return []

    all_items = []
    for page in range(1, MAX_PAGES + 1):
        print(f"[정책뉴스] {page}페이지 요청 중...")
        try:
            data = fetch_page(page)
        except requests.RequestException as e:
            print(f"  → 요청 실패: {e}")
            break

        # 공공데이터포털의 전형적인 응답 구조: response.body.items.item (list or dict)
        try:
            body = data["response"]["body"]
            items = body.get("items") or []
            if isinstance(items, dict):
                items = items.get("item", [])
            if isinstance(items, dict):
                items = [items]
        except (KeyError, TypeError):
            print("  → 예상과 다른 응답 구조입니다. 실제 응답을 확인해 파싱 로직을 조정하세요.")
            print("     응답 일부:", json.dumps(data, ensure_ascii=False)[:300])
            break

        if not items:
            break
        all_items.extend(items)
        time.sleep(0.3)

    print(f"[정책뉴스] 총 {len(all_items)}건 수집")
    return all_items


def pick(row: dict, *keys, default=""):
    for k in keys:
        if k in row and row[k]:
            return row[k]
    return default


def is_recent(date_str: str) -> bool:
    """날짜 문자열이 LOOKBACK_DAYS 이내인지 확인합니다. 형식을 못 읽으면
    사람이 확인할 수 있도록 일단 포함시킵니다(True)."""
    if not date_str:
        return True
    digits = date_str[:10].replace("-", "")[:8]
    try:
        d = datetime.datetime.strptime(digits, "%Y%m%d")
    except ValueError:
        return True
    return (datetime.datetime.now() - d).days <= LOOKBACK_DAYS


def match_articles_to_policies(articles, policies):
    for policy in policies:
        keywords = policy.get("keywords") or []
        if not keywords:
            continue
        matched = []
        for a in articles:
            title = pick(a, "title", "TITLE", "newsTitle")
            date = pick(a, "approvalDate", "regDate", "APPROVAL_DATE")
            url = pick(a, "newsUrl", "NEWS_URL", "url")
            if not title or not url:
                continue
            if any(kw in title for kw in keywords) and is_recent(date):
                matched.append({"title": title, "date": date[:10] if date else "", "url": url})
        if matched:
            policy["relatedNews"] = matched[:NEWS_PER_POLICY]
    return policies


def main():
    print("=" * 60)
    print("정책브리핑 Open API → data.json (policies[].relatedNews) 갱신")
    print("=" * 60)

    if not os.path.exists("data.json"):
        print("[오류] data.json이 없습니다. assembly_fetch.py를 먼저 실행하거나,")
        print("       저장소에 포함된 초기 data.json이 있는 폴더에서 실행하세요.")
        return

    with open("data.json", encoding="utf-8") as f:
        existing = json.load(f)

    policies = existing.get("policies")
    if not policies:
        print("[안내] data.json에 policies 항목이 없어 갱신할 대상이 없습니다.")
        return

    articles = fetch_recent_articles()
    if not articles:
        print("[안내] 새로 가져온 기사가 없어 policies를 변경하지 않습니다.")
        return

    policies = match_articles_to_policies(articles, policies)
    existing["policies"] = policies
    existing["policiesUpdatedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    matched_count = sum(1 for p in policies if p.get("relatedNews"))
    print("-" * 60)
    print(f"완료: {matched_count}/{len(policies)}개 정책 항목에 관련 뉴스 반영")
    print("주의: policyStage·keyPoints는 자동으로 바뀌지 않습니다 (스크립트 상단 설명 참고).")


if __name__ == "__main__":
    sys.exit(main())
