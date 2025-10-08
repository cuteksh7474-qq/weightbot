# WeightBot (웹형/학습형) — 이미지 기반 무게 추정 챗봇

이미지(중국어 스펙표 포함) + 상품명 + 상품코드를 입력하면, **순중량/총중량/부피무게**를 자동 추정하고, 판매 후 **실측무게 피드백**을 넣으면 같은 카테고리의 예측에 **평균 보정치**가 반영됩니다. 결과 표시 언어는 한국어입니다.

---

## 1) 서버 없이 바로 호스팅 — Streamlit Cloud
1. GitHub에 새 레포 만들기 (예: `weightbot`).
2. 이 레포에 아래 3개 파일 업로드
   - `app_streamlit_weightbot.py`
   - `requirements.txt`
   - `README_DEPLOY.md` (이 파일)
3. https://share.streamlit.io → **New app** → 레포 선택 → Main 브랜치 → File path에 `app_streamlit_weightbot.py` → Deploy
4. 잠시 후 생성되는 URL로 접속 → 언제든 사용 가능

### (선택) Google Sheets에 피드백 영구 저장
- Streamlit Cloud의 **Secrets**에 아래 값을 추가하세요.
  - `GS_TYPE`, `GS_PROJECT_ID`, `GS_PRIVATE_KEY_ID`, `GS_PRIVATE_KEY`, `GS_CLIENT_EMAIL`, `GS_CLIENT_ID`, `GS_TOKEN_URI`, (옵션)`GS_WORKBOOK`
- 서비스 계정 이메일에 스프레드시트 공유 권한을 부여하세요.
- 설정이 없으면 로컬 파일(`feedback_db.json`)에 저장합니다(호스팅 환경에서는 재배포 시 초기화될 수 있음).

### (선택) OpenAI Vision/Text 사용
- Streamlit **Secrets**에 `OPENAI_API_KEY` 추가 시, 향후 코드에서 더 정밀한 비전 모델을 사용할 수 있습니다. (현재 버전은 OCR 기반)

---

## 2) 로컬 실행 (선택)
```bash
pip install -r requirements.txt
streamlit run app_streamlit_weightbot.py
```

---

## 기능 요약
- 이미지 업로드(다중) — **중국어 스펙표 OCR**로 치수/무게 추출
- 상품명 → **카테고리/용량 자동 추정**
- 옵션코드 자동 부여: `상품코드-01, -02, ...`
- 결과: **순중량, 포장 포함 총중량, 부피무게(5000/6000)**, 신뢰도
- **피드백 학습**: 실측값 저장 → 카테고리 평균 보정 자동 반영
- **Excel 내보내기**

---

## 주의 및 한계
- OCR 기반이라 표가 복잡하거나 해상도가 낮으면 인식 정확도가 떨어질 수 있습니다. 개선이 필요하면 OpenAI Vision API를 연결하시길 권장합니다.
- 피드백 DB의 영구 저장은 Google Sheets 같은 외부 저장소를 사용하세요.
- 계산식은 업계 경험식+근사치 기반입니다. 실제 출고 전 **실측 검증**이 필요합니다.

---

## Secrets 예시 (Streamlit Cloud)
```
# .streamlit/secrets.toml 대신, Cloud의 Secrets UI에 입력
GS_TYPE = "service_account"
GS_PROJECT_ID = "your-gcp-project-id"
GS_PRIVATE_KEY_ID = "xxxx"
GS_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\n...==\n-----END PRIVATE KEY-----\n"
GS_CLIENT_EMAIL = "your-sa@your-project.iam.gserviceaccount.com"
GS_CLIENT_ID = "1234567890"
GS_TOKEN_URI = "https://oauth2.googleapis.com/token"
GS_WORKBOOK = "WeightBot_Feedback"

OPENAI_API_KEY = "sk-... (optional)"
```

---

## 개선/확장 제안
- 운송사별 **요율표/최소 청구중량** 자동 반영
- **옵션 상세(색상/사이즈) 필드** 추가 및 코드 중복 방지
- OpenAI Vision 연결로 **스펙표 정밀 구조화**
- Supabase/Airtable로 데이터 백엔드 전환