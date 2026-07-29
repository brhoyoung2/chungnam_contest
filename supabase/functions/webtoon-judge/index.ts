// 충남 공모전 · 웹툰 AI 심사 (OpenAI gpt-4o 비전 · PDF 직접 분석)
//
// 흐름: 관리자(admin-index.html) → 이 함수 호출({pw,id})
//   1) 비밀번호 검증(기존 관리자 게이트와 동일: 5972 / ADMIN_PW)
//   2) 서비스롤로 접수 레코드 조회 → extra.pdf_url 확보
//   3) Storage 에서 PDF 원본 다운로드(공개/비공개 무관)
//   4) OpenAI Responses API(gpt-4o)에 PDF 파일 그대로 첨부 → 컷 분석·구성·흐름 평가
//   5) 결과를 extra.ai_review 에 저장(사용자 원본 데이터는 불변)
//
// 필요한 시크릿(대시보드 Edge Functions → Secrets):
//   OPENAI_API_KEY   (필수)
//   ADMIN_PW         (선택, 기본 5972)
// SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 는 런타임이 자동 주입.
//
// 배포:  supabase functions deploy webtoon-judge --no-verify-jwt
//   또는 대시보드에서 새 함수로 이 파일 내용을 붙여넣고 Deploy.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { encodeBase64 } from "https://deno.land/std@0.224.0/encoding/base64.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });

const DEFAULT_MODEL = "gpt-4o";
// 관리자 드롭다운에서 고를 수 있는 허용 모델(비전+PDF 지원)
const ALLOWED_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"];

const SYS = [
  "너는 충청남도교육청 청소년(초·중·고) 디지털 콘텐츠 창작 공모전의 '웹툰' 부문 심사위원이다.",
  "첨부된 PDF 는 학생이 제출한 웹툰 작품 원본이다. 페이지를 순서대로 실제로 보고 평가하라.",
  "다음을 반드시 수행한다:",
  "1) 각 페이지의 컷(장면)을 순서대로 파악해 무엇이 그려졌는지 요약한다.",
  "2) 페이지 구성·컷 레이아웃·스토리 흐름(서사 연결성)을 평가한다.",
  "3) 학생 수준을 고려하되 근거를 들어 채점한다.",
  "",
  "반드시 아래 JSON 형식으로만 답하라(코드펜스 없이 순수 JSON).",
  "{",
  '  "컷분석": [ {"페이지": 1, "컷": 1, "내용": "무엇이 그려졌는지", "연출": "컷 구성/시선유도 등"} ],',
  '  "페이지구성평": "페이지 구성에 대한 평가(한국어)",',
  '  "레이아웃평": "컷 레이아웃에 대한 평가(한국어)",',
  '  "스토리흐름평": "장면 전환·서사 연결성 평가(한국어)",',
  '  "주제적합성": 0, "창의성": 0, "완성도": 0, "표현력": 0,',
  '  "총평": "200자 이내 한두 문장",',
  '  "근거": "위 4개 점수를 그렇게 준 핵심 근거",',
  '  "추천": true',
  "}",
  "점수는 0~10 사이 정수. 매핑 기준 — 주제적합성: 공모 주제 부합도, 창의성: 발상·독창성,",
  "완성도: 페이지 구성 + 작화 완성도, 표현력: 컷 레이아웃 + 연출 + 스토리 흐름.",
].join("\n");

function extractText(data: any): string {
  // Responses API: data.output[] 중 message 의 content[] 에서 output_text 추출
  if (typeof data?.output_text === "string") return data.output_text;
  const out = data?.output;
  if (Array.isArray(out)) {
    for (const item of out) {
      const content = item?.content;
      if (Array.isArray(content)) {
        for (const c of content) {
          if ((c?.type === "output_text" || c?.type === "text") && typeof c?.text === "string") {
            return c.text;
          }
        }
      }
    }
  }
  return "";
}

function parseJson(txt: string): any {
  let s = (txt || "").trim();
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) s = fence[1].trim();
  const a = s.indexOf("{"), b = s.lastIndexOf("}");
  if (a >= 0 && b > a) s = s.slice(a, b + 1);
  return JSON.parse(s);
}

// pdf_url 에서 Storage 경로 추출: .../object/(public|sign)/submissions/<path>
function storagePath(url: string): string | null {
  const m = url.match(/\/object\/(?:public|sign)\/submissions\/([^?]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  try {
    const { pw, id, model } = await req.json().catch(() => ({}));
    const ADMIN_PW = Deno.env.get("ADMIN_PW") || "5972";
    if (pw !== ADMIN_PW) return json({ error: "unauthorized" }, 401);
    if (!id) return json({ error: "id 누락" }, 400);
    const MODEL = ALLOWED_MODELS.includes(model) ? model : DEFAULT_MODEL;

    const OPENAI_KEY = Deno.env.get("OPENAI_API_KEY");
    if (!OPENAI_KEY) return json({ error: "OPENAI_API_KEY 시크릿 미설정" }, 500);

    const admin = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );

    // 1) 접수 레코드
    const { data: row, error: qerr } = await admin
      .from("충남콘테스트_접수")
      .select("id, category, extra, name, school, board_link")
      .eq("id", id)
      .single();
    if (qerr || !row) return json({ error: "접수 레코드를 찾을 수 없습니다." }, 404);
    if (row.category !== "웹툰")
      return json({ error: "이 함수는 웹툰 부문 전용입니다." }, 400);

    const extra = row.extra || {};
    const pdfUrl: string | undefined = extra.pdf_url;
    if (!pdfUrl) return json({ error: "제출된 PDF(pdf_url)가 없습니다." }, 400);

    // 2) PDF 원본 다운로드 (Storage 우선, 실패 시 URL 직접)
    let bytes: Uint8Array | null = null;
    const path = storagePath(pdfUrl);
    if (path) {
      const dl = await admin.storage.from("submissions").download(path);
      if (dl.data) bytes = new Uint8Array(await dl.data.arrayBuffer());
    }
    if (!bytes) {
      const r = await fetch(pdfUrl);
      if (!r.ok) return json({ error: "PDF 다운로드 실패: " + r.status }, 502);
      bytes = new Uint8Array(await r.arrayBuffer());
    }
    const b64 = encodeBase64(bytes);

    // 3) 메타 + 사용자 지시 텍스트
    const meta = [
      "[부문] 웹툰",
      "[학교] " + (row.school || ""),
      extra.ai_process ? "[생성형 AI 활용 과정]\n" + extra.ai_process : "",
      "위 첨부 PDF(웹툰 작품)를 페이지 순서대로 보고 심사 기준에 따라 평가하라.",
    ].filter(Boolean).join("\n\n");

    // 4) OpenAI Responses API (PDF 파일 직접 첨부)
    const oa = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + OPENAI_KEY,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        temperature: 0.3,
        input: [
          { role: "system", content: SYS },
          {
            role: "user",
            content: [
              { type: "input_text", text: meta },
              {
                type: "input_file",
                filename: "webtoon.pdf",
                file_data: "data:application/pdf;base64," + b64,
              },
            ],
          },
        ],
      }),
    });
    const oaData = await oa.json();
    if (!oa.ok) {
      return json({ error: "OpenAI 오류: " + (oaData?.error?.message || oa.status) }, 502);
    }

    let review: any;
    try {
      review = parseJson(extractText(oaData));
    } catch (_e) {
      return json({ error: "심사 결과 JSON 파싱 실패" }, 502);
    }
    review._model = MODEL + " (vision)";
    review._at = new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });

    // 5) 저장 (ai_review 칸만 갱신 · 원본 불변)
    const nextExtra = { ...extra, ai_review: review };
    const { error: uerr } = await admin
      .from("충남콘테스트_접수")
      .update({ extra: nextExtra })
      .eq("id", id);
    if (uerr) return json({ error: "저장 실패: " + uerr.message }, 500);

    return json({ ok: true, review });
  } catch (e) {
    return json({ error: String((e as Error)?.message || e) }, 500);
  }
});
