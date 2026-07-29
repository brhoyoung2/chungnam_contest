# 웹툰 AI 심사 Edge Function 배포

관리자 페이지의 **웹툰 부문**을 OpenAI `gpt-4o` 비전으로 심사한다.
PDF 를 서버에서 직접 읽어 컷 분석·페이지 구성·레이아웃·스토리 흐름을 평가하고
결과를 `충남콘테스트_접수.extra.ai_review` 에 저장한다. (웹소설은 기존 Grok 방식 유지)

> OpenAI 키는 **서버(Supabase 시크릿)에만** 둔다. 브라우저·저장소에 절대 넣지 않는다.

---

## 방법 A — Supabase 대시보드 (CLI 없이, 권장)

1. **Edge Functions → Create a new function** → 이름 `webtoon-judge`
2. `index.ts` 내용을 그대로 붙여넣고 **Deploy**
3. **Deploy 시 JWT 검증 끄기**: 함수 Settings → **Verify JWT = Off**
   (관리자 비밀번호로 자체 검증하므로)
4. **Secrets** (Project Settings → Edge Functions → Secrets, 또는 함수 Secrets)에 추가:
   - `OPENAI_API_KEY` = (OpenAI 서비스 계정 키)
   - `ADMIN_PW` = `5972` (선택 · 미설정 시 기본 5972)

## 방법 B — CLI

```bash
supabase login
supabase link --project-ref mllbsqnrvhvnqvxkpxof
supabase secrets set OPENAI_API_KEY=sk-...          # 실제 키
supabase functions deploy webtoon-judge --no-verify-jwt
```

---

## 확인

1. 관리자 페이지에서 **웹툰** 접수 건의 「🤖 AI 심사」 클릭 → "PDF 분석 중…" 후 결과 표시.
2. 결과에 **총점/40 · 컷 분석 · 페이지 구성/레이아웃/스토리 흐름 평 · 채점 근거**가 보이면 정상.
3. 실패 시 메시지 확인:
   - `OPENAI_API_KEY 시크릿 미설정` → 4번 시크릿 재확인
   - `unauthorized` → 관리자 비밀번호(PW)와 `ADMIN_PW` 불일치
   - `PDF 다운로드 실패` → `submissions` 버킷 접근 권한(서비스롤은 통과하나, 경로 확인)

## 자동 주입 환경변수 (설정 불필요)
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` 는 런타임이 자동 제공.

## 비용·성능 메모
- 건당 PDF(최대 20MB)를 gpt-4o 에 통째로 전달 → **건당 수십 초 + 토큰 비용**. 대량은 순차 처리.
- 페이지 수가 많으면 비용↑. 필요 시 모델을 `gpt-4o-mini` 로 낮추거나 페이지 상한을 두는 최적화 가능.
