-- ============================================================
--  제5회 AI 로봇 끝장 개발 한마당 · 주제2 (충남) 작품 접수
--  Supabase 설정 SQL  (v2 · SECURITY DEFINER 기반)
--
--  실행 방법: Supabase 대시보드 → SQL Editor → New query →
--             아래 전체 붙여넣기 → Run
--
--  테이블 명명 규칙(한글): 프로젝트명_테이블명 → "충남콘테스트_접수"
--
--  설계: 접수/조회 모두 SECURITY DEFINER 함수로만 처리.
--        anon 키는 테이블에 직접 접근 불가(INSERT/UPDATE/SELECT 전부 차단)
--        → 타인 데이터 덮어쓰기·전체 조회 불가, 개인정보 보호.
-- ============================================================

-- 1) 접수 테이블 ------------------------------------------------
create table if not exists public."충남콘테스트_접수" (
  id              uuid        primary key default gen_random_uuid(),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  name            text    not null,                                  -- 이름
  school          text    not null,                                  -- 학교
  grade           text    not null,                                  -- 학년
  teacher_email   text    not null,                                  -- 지도교사 이메일
  tooning_account text    not null unique,                           -- 투닝 계정(소문자/공백제거 정규화) · 1인 1작품 기준키
  category        text    not null check (category in ('웹툰','웹소설')), -- 참가 부문
  board_link      text    not null,                                  -- 투닝 보드 링크
  agreed          boolean not null default false                     -- 출품 요건 동의
);

-- 2) RLS: 켜되 anon 직접 접근 정책은 두지 않음(전부 차단) ---------
alter table public."충남콘테스트_접수" enable row level security;
-- 이전 버전(v1)에서 만든 직접 접근 정책 제거
drop policy if exists "충남콘테스트_접수_anon_insert" on public."충남콘테스트_접수";
drop policy if exists "충남콘테스트_접수_anon_update" on public."충남콘테스트_접수";

-- (이전 테스트 데이터 정리)
delete from public."충남콘테스트_접수" where tooning_account = '__claude_test__@tooning.io';

-- 3) 접수 함수 (INSERT or UPDATE) ------------------------------
--    반환: 'created'(신규) | 'updated'(갱신)
--    부문 변경 시 예외 'category_locked:<기존부문>' 발생 → 클라이언트가 안내.
create or replace function public."충남콘테스트_제출"(
  p_name          text,
  p_school        text,
  p_grade         text,
  p_teacher_email text,
  p_account       text,
  p_category      text,
  p_board_link    text,
  p_agreed        boolean
)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_acct text := lower(trim(p_account));
  v_prev record;
begin
  if coalesce(p_agreed,false) = false then
    raise exception 'agreement_required';
  end if;
  if p_category not in ('웹툰','웹소설') then
    raise exception 'invalid_category';
  end if;
  if p_board_link is null or position('tooning.io' in p_board_link) = 0 then
    raise exception 'invalid_link';
  end if;

  select * into v_prev from "충남콘테스트_접수" where tooning_account = v_acct;

  if found then
    if v_prev.category <> p_category then
      raise exception 'category_locked:%', v_prev.category;   -- 부문 변경 차단
    end if;
    update "충남콘테스트_접수"
       set name=p_name, school=p_school, grade=p_grade, teacher_email=p_teacher_email,
           category=p_category, board_link=p_board_link, agreed=p_agreed, updated_at=now()
     where tooning_account = v_acct;
    return 'updated';
  else
    insert into "충남콘테스트_접수"
      (name, school, grade, teacher_email, tooning_account, category, board_link, agreed)
    values
      (p_name, p_school, p_grade, p_teacher_email, v_acct, p_category, p_board_link, p_agreed);
    return 'created';
  end if;
end;
$$;

grant execute on function
  public."충남콘테스트_제출"(text,text,text,text,text,text,text,boolean) to anon;

-- 4) 조회 함수 (본인 계정 1건) --------------------------------
create or replace function public."충남콘테스트_조회"(p_account text)
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
  from public."충남콘테스트_접수" s
  where s.tooning_account = lower(trim(p_account))
  limit 1;
$$;

grant execute on function public."충남콘테스트_조회"(text) to anon;

-- ============================================================
--  동작 확인용:
--  select public."충남콘테스트_제출"('홍길동','OO고','고 2학년','t@s.kr','me@tooning.io','웹툰','https://tooning.io/board/x',true);
--  select * from public."충남콘테스트_조회"('me@tooning.io');
-- ============================================================
