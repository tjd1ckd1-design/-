# 법안·국정과제 트래커 — 배포 가이드

"국가는 지금 어디로 가고 있나"에 집중하는 사이트입니다. 국회 법안 진행 현황과
정부 국정과제를 100% 자동으로 갱신되는 데이터만으로 추적합니다.
(청원 데이터는 자동화가 불가능해 이 버전에서는 다루지 않습니다 — 아래 참고)

이 폴더를 그대로 GitHub에 올리면, 모든 사람이 접속할 수 있는 무료 웹페이지가 되고
매일 자동으로 법안·국정과제 데이터가 갱신됩니다. 순서대로 따라 하면 됩니다. (전부 무료)

```
petition-tracker-site/
├── index.html                       ← 웹페이지 본체
├── data.json                        ← 화면에 표시될 데이터 (처음엔 예시 데이터)
├── assembly_fetch.py                ← 국회 Open API에서 법안 데이터를 받아오는 스크립트
├── policy_fetch.py                  ← 정책브리핑 API에서 국정과제 관련 뉴스를 받아오는 스크립트
├── requirements.txt
└── .github/workflows/update-data.yml ← 매일 자동으로 두 스크립트를 실행시켜주는 설정
```

## 1. GitHub 저장소 만들기

1. https://github.com 가입 (이미 있으면 생략)
2. 오른쪽 위 `+` → `New repository` 클릭
3. 이름 예: `national-direction-tracker` (원하는 이름으로), **Public** 선택 → `Create repository`

## 2. 이 폴더의 파일 올리기

가장 쉬운 방법:
1. 방금 만든 저장소 페이지에서 `uploading an existing file` 클릭
2. 이 폴더 안의 파일을 **폴더 구조 그대로** 끌어다 놓기
   - `.github/workflows/update-data.yml` 처럼 숨김 폴더가 포함된 경우, 브라우저 업로드에서
     폴더째 끌어다 놓으면 구조가 유지됩니다. (안 되면 아래 "Git으로 올리기" 방법을 쓰세요)
3. `Commit changes`

Git에 익숙하다면 이 방법이 더 확실합니다.
```bash
cd petition-tracker-site
git init
git add .
git commit -m "초기 배포"
git branch -M main
git remote add origin https://github.com/{내 계정}/national-direction-tracker.git
git push -u origin main
```

## 3. GitHub Pages 켜기 (여기서 실제 주소가 생깁니다)

1. 저장소 → `Settings` → 왼쪽 메뉴 `Pages`
2. `Source`를 `Deploy from a branch`로 설정
3. `Branch`를 `main` / `root`로 설정 → `Save`
4. 1~2분 뒤 페이지 상단에 아래와 같은 주소가 나타납니다.
   ```
   https://{내 계정}.github.io/national-direction-tracker/
   ```
   이 주소를 아무나 접속해서 볼 수 있습니다.

여기까지만 해도 **예시 법안 데이터 + 실제 국정과제 데이터로 채워진 사이트**가 이미 온라인에 공개됩니다.
(국정과제 항목은 처음부터 실제 정부 발표 기반이라 별도 키 없이도 진짜 정보입니다.)

## 4. 실제 법안 데이터 자동 연동하기

1. https://open.assembly.go.kr 회원가입 → 마이페이지 → Open API → 인증키 발급 (무료, 즉시)
2. 저장소 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
   - Name: `ASSEMBLY_API_KEY`
   - Value: 방금 발급받은 키
3. 저장소 → `Actions` 탭 → 워크플로 선택 → `Run workflow` 버튼으로 한 번 수동 실행 (테스트)
4. 몇십 초 후 저장소의 `data.json`이 실제 법안 데이터로 갱신된 커밋이 생기고,
   사이트를 새로고침하면 화면 상단 안내가 "실시간 데이터"로 바뀝니다.
5. 이후로는 **매일 한국시간 오전 6시에 자동으로** 다시 실행되어 갱신됩니다.
   (`.github/workflows/update-data.yml`의 `cron` 값을 바꾸면 주기를 조정할 수 있어요.
   예: `"0 */6 * * *"` = 6시간마다.)

## 5. 국정과제 관련 최신 뉴스 자동 갱신 (선택)

`policy_fetch.py`는 "대한민국 정책브리핑" Open API(문화체육관광부, data.go.kr)에서
6개 국정과제 항목과 관련된 최신 보도자료를 찾아 각 항목에 "관련 최신 뉴스"로 붙여줍니다.

1. https://www.data.go.kr 회원가입 → "문화체육관광부_정책브리핑_정책뉴스_API" 검색 →
   활용신청 (자동승인이라 바로 키가 발급됩니다)
2. 저장소 Settings → Secrets and variables → Actions → New repository secret
   - Name: `DATA_GO_KR_API_KEY`
   - Value: 발급받은 서비스키
3. Actions 탭에서 워크플로를 한 번 수동 실행하면 반영됩니다.

**중요한 한계**: 이 API는 국회 의안 API와 달리 개별 보도자료 목록일 뿐,
"이 정책이 지금 몇 단계인지"를 알려주는 데이터가 아닙니다. 그래서 스크립트는
`policyStage`(추진 단계)나 `keyPoints`(주요내용)를 자동으로 바꾸지 않고,
관련 기사 제목·날짜·링크만 참고 자료로 덧붙입니다.

## 청원 데이터를 뺀 이유

국민동의청원 현황은 인증키로 호출하는 Open API가 아니라, 로그인한 브라우저에서
직접 눌러야 받아지는 파일 다운로드 방식이었습니다 (다운로드 버튼의 요청을 직접
확인해봤는데, 세션 기반이라 스크립트로 자동 호출할 수 없었습니다). "국가가 지금
어디로 가고 있는지"를 매일 100% 자동으로 보여주는 것이 이 사이트의 목표라서,
수동 작업이 필요한 청원 섹션은 이번 버전에서 제외했습니다.

## 자주 묻는 것들

**꼭 GitHub Actions를 써야 하나요?**
아니요. 3단계까지만 해도 예시 법안 + 실제 국정과제 데이터로 사이트는 정상
배포됩니다. 실시간 법안 갱신을 원할 때만 4단계를 진행하면 됩니다.

**더 쉬운 배포 방법은 없나요?**
`index.html`, `data.json` 두 파일만 있으면 Netlify(app.netlify.com)에 드래그 앤 드롭으로도
1분 안에 배포할 수 있어요. 다만 그 경우 데이터 자동 갱신(4~5단계)은 별도로 GitHub Actions를
연결하거나 다른 스케줄러가 필요합니다. GitHub Pages 방식이 한 플랫폼 안에서 호스팅+자동갱신이
모두 해결되어 가장 간단합니다.

**나중에 내 도메인으로 연결할 수 있나요?**
네. `Settings > Pages`의 `Custom domain`에 도메인을 입력하고, 도메인 DNS에
안내되는 CNAME 레코드를 추가하면 됩니다.

**비용은요?**
GitHub Pages, GitHub Actions(공개 저장소), 국회 Open API, data.go.kr 모두 무료입니다.
