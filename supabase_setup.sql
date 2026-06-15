-- ============================================================
--  제5회 AI 로봇 끝장 개발 한마당 · 주제2 (충남) 작품 접수
--  Supabase 초기 설정 SQL
--
--  실행 방법: Supabase 대시보드 → SQL Editor → New query →
--             아래 전체 붙여넣기 → Run
--
--  테이블 명명 규칙: 프로젝트명_테이블명  →  chungnam_contest_submissions
-- ============================================================

-- 1) 접수 테이블 ------------------------------------------------
create table if not exists public.chungnam_contest_submissions (
  id              bigint generated always as identity primary key,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  name            text    not null,                                  -- 이름
  school          text    not null,                                  -- 학교
  grade           text    not null,                                  -- 학년
  teacher_email   text    not null,                                  -- 지도교사 이메일
  tooning_account text    not null unique,                           -- 투닝 계정 (정규화: 소문자/공백제거) · 1인 1작품 기준키
  category        text    not null check (category in ('웹툰','웹소설')), -- 참가 부문
  board_link      text    not null,                                  -- 투닝 보드 링크
  agreed          boolean not null default false                     -- 출품 요건 동의
);

-- 2) RLS (Row Level Security) ---------------------------------
alter table public.chungnam_contest_submissions enable row level security;

-- 익명(anon) INSERT 허용 — 접수 폼 제출
drop policy if exists "chungnam_contest_anon_insert" on public.chungnam_contest_submissions;
create policy "chungnam_contest_anon_insert"
  on public.chungnam_contest_submissions
  for insert to anon
  with check (true);

-- 익명(anon) UPDATE 허용 — 같은 계정 재제출 시 최신 작품으로 덮어쓰기(upsert)
drop policy if exists "chungnam_contest_anon_update" on public.chungnam_contest_submissions;
create policy "chungnam_contest_anon_update"
  on public.chungnam_contest_submissions
  for update to anon
  using (true) with check (true);

-- ※ 의도적으로 SELECT 정책은 만들지 않습니다.
--    → anon 키로는 테이블 전체 조회가 불가(개인정보 보호).
--    → 조회는 아래 RPC(본인 계정 한정)로만 가능.

-- 3) 조회용 RPC (security definer) ----------------------------
--    챗봇 "접수 확인" 기능: 본인 투닝 계정으로 1건만 조회.
create or replace function public.chungnam_contest_lookup(p_account text)
returns table (
  name        text,
  school      text,
  grade       text,
  category    text,
  board_link  text,
  created_at  timestamptz,
  updated_at  timestamptz
)
language sql
security definer
set search_path = public
as $$
  select s.name, s.school, s.grade, s.category, s.board_link, s.created_at, s.updated_at
  from public.chungnam_contest_submissions s
  where s.tooning_account = lower(trim(p_account))
  limit 1;
$$;

grant execute on function public.chungnam_contest_lookup(text) to anon;

-- ============================================================
--  완료. 아래로 동작 확인 가능:
--  select * from public.chungnam_contest_submissions;
--  select * from public.chungnam_contest_lookup('test@tooning.io');
-- ============================================================
