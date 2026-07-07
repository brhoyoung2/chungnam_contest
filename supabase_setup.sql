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
  agreed          boolean not null default false,                    -- 출품 요건 동의
  extra           jsonb   not null default '{}'::jsonb,              -- 부문별 추가 데이터(웹툰 PDF URL / 웹소설 본문·AI과정·이미지 등)
  submit_key      text    unique                                     -- 접수 고유 키(수정·확인용, 예: CNAI-7K3Q-2M9X)
);

-- (기존 테이블에 컬럼 보강)
alter table public."충남콘테스트_접수" add column if not exists extra jsonb not null default '{}'::jsonb;
alter table public."충남콘테스트_접수" add column if not exists submit_key text;
do $$ begin
  alter table public."충남콘테스트_접수" add constraint "충남콘테스트_접수_submit_key_key" unique (submit_key);
exception when duplicate_table or duplicate_object then null; end $$;

-- 2) RLS: 켜되 anon 직접 접근 정책은 두지 않음(전부 차단) ---------
alter table public."충남콘테스트_접수" enable row level security;
-- 이전 버전(v1)에서 만든 직접 접근 정책 제거
drop policy if exists "충남콘테스트_접수_anon_insert" on public."충남콘테스트_접수";
drop policy if exists "충남콘테스트_접수_anon_update" on public."충남콘테스트_접수";

-- (이전 테스트 데이터 정리)
delete from public."충남콘테스트_접수" where tooning_account = '__claude_test__@tooning.io';

-- 3) 접수 함수 (INSERT or UPDATE) ------------------------------
--    반환(jsonb): { "status":"created"|"updated", "key":"CNAI-XXXX-XXXX" }
--    부문 변경 시 예외 'category_locked:<기존부문>' 발생 → 클라이언트가 안내.
--    p_extra: 부문별 추가 데이터(웹툰 pdf_url / 웹소설 description·ai_process·ai_images·episodes)
-- (이전 버전 제거 후 재생성)
drop function if exists public."충남콘테스트_제출"(text,text,text,text,text,text,text,boolean);
drop function if exists public."충남콘테스트_제출"(text,text,text,text,text,text,text,boolean,jsonb);
create or replace function public."충남콘테스트_제출"(
  p_name          text,
  p_school        text,
  p_grade         text,
  p_teacher_email text,
  p_account       text,
  p_category      text,
  p_board_link    text,
  p_agreed        boolean,
  p_extra         jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_acct  text  := lower(trim(p_account));
  v_extra jsonb := coalesce(p_extra, '{}'::jsonb);
  v_prev  record;
  v_key   text;
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
    v_key := v_prev.submit_key;
    if v_key is null then                                     -- 레거시 행이면 키 발급
      v_key := 'CNAI-'||upper(substr(md5(random()::text||clock_timestamp()::text),1,4))
                     ||'-'||upper(substr(md5(random()::text||clock_timestamp()::text),1,4));
    end if;
    update "충남콘테스트_접수"
       set name=p_name, school=p_school, grade=p_grade, teacher_email=p_teacher_email,
           category=p_category, board_link=p_board_link, agreed=p_agreed, extra=v_extra,
           submit_key=v_key, updated_at=now()
     where tooning_account = v_acct;
    return jsonb_build_object('status','updated','key',v_key);
  else
    v_key := 'CNAI-'||upper(substr(md5(random()::text||clock_timestamp()::text),1,4))
                   ||'-'||upper(substr(md5(random()::text||clock_timestamp()::text),1,4));
    insert into "충남콘테스트_접수"
      (name, school, grade, teacher_email, tooning_account, category, board_link, agreed, extra, submit_key)
    values
      (p_name, p_school, p_grade, p_teacher_email, v_acct, p_category, p_board_link, p_agreed, v_extra, v_key);
    return jsonb_build_object('status','created','key',v_key);
  end if;
end;
$$;

grant execute on function
  public."충남콘테스트_제출"(text,text,text,text,text,text,text,boolean,jsonb) to anon;

-- 4) 조회 함수 (접수 키 전용) -------------------------------------
--    ⚠️ 개인정보 보호: 투닝 계정은 규칙적이라 열거(enumeration) 가능하므로
--       계정으로는 조회하지 않고, 제출 시 발급되는 무작위 '접수 키'로만 1건 반환.
drop function if exists public."충남콘테스트_조회"(text);
create or replace function public."충남콘테스트_조회"(p_account text)
returns table (
  name        text,
  school      text,
  grade       text,
  category    text,
  board_link  text,
  submit_key  text,
  extra       jsonb,
  created_at  timestamptz,
  updated_at  timestamptz
)
language sql
security definer
set search_path = public
as $$
  select s.name, s.school, s.grade, s.category, s.board_link, s.submit_key, s.extra, s.created_at, s.updated_at
  from public."충남콘테스트_접수" s
  where upper(s.submit_key) = upper(trim(p_account))   -- 접수 키로만 조회(계정 열거 차단)
  limit 1;
$$;

grant execute on function public."충남콘테스트_조회"(text) to anon;

-- 5) Storage: 제출 파일 버킷 (웹툰 PDF / 웹소설 AI과정 이미지) ----
--    공개 버킷 + anon 업로드 허용. 파일 경로에 타임스탬프를 포함해 충돌 방지.
insert into storage.buckets (id, name, public)
values ('submissions','submissions', true)
on conflict (id) do update set public = true;

drop policy if exists "submissions_anon_insert" on storage.objects;
create policy "submissions_anon_insert" on storage.objects
  for insert to anon with check (bucket_id = 'submissions');

drop policy if exists "submissions_public_read" on storage.objects;
create policy "submissions_public_read" on storage.objects
  for select to anon using (bucket_id = 'submissions');

-- 6) 관리자 함수 (비밀번호 게이트) --------------------------------
--    ⚠️ 운영 전 아래 비밀번호('5972')를 반드시 변경하세요. (두 함수 동일하게)
--    anon 키만으로는 전체 조회 불가 — 올바른 비밀번호일 때만 전체 목록/심사 저장 허용.

-- 6-1) 전체 접수 목록 (개인정보·결과물 포함)
create or replace function public."충남콘테스트_관리자목록"(p_pw text)
returns setof public."충남콘테스트_접수"
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_pw is distinct from '5972' then
    raise exception 'unauthorized';
  end if;
  return query select * from public."충남콘테스트_접수" order by created_at desc;
end;
$$;
grant execute on function public."충남콘테스트_관리자목록"(text) to anon;

-- 6-2) AI 심사 결과 저장 (extra.ai_review 에 기록)
create or replace function public."충남콘테스트_관리자심사저장"(p_pw text, p_id uuid, p_review jsonb)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_pw is distinct from '5972' then
    raise exception 'unauthorized';
  end if;
  update public."충남콘테스트_접수"
     set extra = jsonb_set(coalesce(extra,'{}'::jsonb), '{ai_review}', p_review, true)
   where id = p_id;
end;
$$;
grant execute on function public."충남콘테스트_관리자심사저장"(text,uuid,jsonb) to anon;

-- 6-3) 접수 삭제 (관리자 전용)
create or replace function public."충남콘테스트_관리자삭제"(p_pw text, p_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_pw is distinct from '5972' then
    raise exception 'unauthorized';
  end if;
  delete from public."충남콘테스트_접수" where id = p_id;
end;
$$;
grant execute on function public."충남콘테스트_관리자삭제"(text,uuid) to anon;

-- 7) 접수 완료 자동메일 (Resend) — 양식은 관리자 페이지에서 편집 -----
--    첫 접수(INSERT)·재제출(UPDATE·updated_at 변경 시)에 지도교사 메일로 발송, leo@tooning.io 참조.
--    ⚠️ 아래 v_key 를 실제 Resend API 키(re_...)로 교체하세요. (공개 레포엔 키를 넣지 마세요)
--    ⚠️ api.resend.com 은 Cloudflare 뒤라 User-Agent 헤더가 없으면 차단(1010)됨 → 헤더 포함.
create extension if not exists pg_net with schema extensions;

-- 7-1) 메일 양식 저장(단일 행) + 기본값
create table if not exists public."충남콘테스트_설정" (
  id           int primary key default 1,
  mail_subject text,
  mail_body    text,
  updated_at   timestamptz default now(),
  constraint "충남설정_singleton" check (id = 1)
);
alter table public."충남콘테스트_설정" enable row level security;   -- anon 직접 접근 차단(관리자 RPC로만)
insert into public."충남콘테스트_설정"(id, mail_subject, mail_body) values (1,
  '[AI 도구 활용 디지털 콘텐츠 창작] 접수완료',
  E'안녕하세요, 선생님.\n제5회 인공지능 로봇 끝장 개발(해커톤) 한마당 · 주제2 공모전 접수를 안내드립니다.\n아래와 같이 작품이 정상적으로 접수되었습니다.\n\n• 이름: {이름}\n• 학교: {학교} ({학년})\n• 부문: {부문}\n• 접수 키: {접수키}\n• 작품 링크: {작품링크}\n• 최종 접수: {최종접수}\n\n투닝 공모전을 사랑해 주셔서 감사드립니다.\n오늘도 즐거운 하루 보내세요! 😊'
) on conflict (id) do nothing;

-- 7-2) 관리자 양식 조회/저장 (비밀번호 게이트)
create or replace function public."충남콘테스트_메일템플릿"(p_pw text)
returns table(mail_subject text, mail_body text)
language plpgsql security definer set search_path = public as $$
begin
  if p_pw is distinct from '5972' then raise exception 'unauthorized'; end if;
  return query select s.mail_subject, s.mail_body from public."충남콘테스트_설정" s where s.id = 1;
end $$;
grant execute on function public."충남콘테스트_메일템플릿"(text) to anon;

create or replace function public."충남콘테스트_메일템플릿저장"(p_pw text, p_subject text, p_body text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if p_pw is distinct from '5972' then raise exception 'unauthorized'; end if;
  insert into public."충남콘테스트_설정"(id, mail_subject, mail_body, updated_at)
  values (1, p_subject, p_body, now())
  on conflict (id) do update set mail_subject = excluded.mail_subject, mail_body = excluded.mail_body, updated_at = now();
end $$;
grant execute on function public."충남콘테스트_메일템플릿저장"(text,text,text) to anon;

-- 7-3) 트리거 함수: 저장된 양식을 읽어 치환 후 발송
create or replace function public."충남_접수완료메일"()
returns trigger language plpgsql security definer set search_path = public, extensions as $$
declare
  v_key  text := 're_REPLACE_WITH_RESEND_KEY';   -- ← 실제 키로 교체
  v_new  boolean := (TG_OP = 'INSERT');
  v_when text := to_char(NEW.updated_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI');
  v_subj text;
  v_body text;
  v_html text;
begin
  if NEW.teacher_email is null or position('@' in NEW.teacher_email) = 0 then
    return NEW;
  end if;
  select mail_subject, mail_body into v_subj, v_body from public."충남콘테스트_설정" where id = 1;
  v_subj := coalesce(nullif(btrim(v_subj),''), '[AI 도구 활용 디지털 콘텐츠 창작] 접수완료');
  v_body := coalesce(v_body, '작품 접수가 완료되었습니다.');
  v_body := replace(v_body, '{선생님}', '');
  v_body := replace(v_body, '{이름}',   coalesce(NEW.name,''));
  v_body := replace(v_body, '{학교}',   coalesce(NEW.school,''));
  v_body := replace(v_body, '{학년}',   coalesce(NEW.grade,''));
  v_body := replace(v_body, '{부문}',   coalesce(NEW.category,''));
  v_body := replace(v_body, '{접수키}', coalesce(NEW.submit_key,''));
  v_body := replace(v_body, '{최종접수}', v_when);
  v_body := replace(v_body, '{상태}', case when v_new then '접수 완료' else '접수 갱신' end);
  v_body := replace(v_body, '{작품링크}', '<a href="'||coalesce(NEW.board_link,'')||'">'||coalesce(NEW.board_link,'')||'</a>');
  v_subj := replace(replace(v_subj,'{이름}',coalesce(NEW.name,'')),'{부문}',coalesce(NEW.category,''));
  v_html := '<div style="font-family:sans-serif;font-size:15px;line-height:1.7;color:#222">'
         || replace(v_body, E'\n', '<br>') || '</div>';
  begin
    perform net.http_post(
      url := 'https://api.resend.com/emails',
      headers := jsonb_build_object(
        'Authorization', 'Bearer '||v_key,
        'Content-Type', 'application/json',
        'User-Agent', 'tooning-contest/1.0 (+https://c-contest.tooning.io)'
      ),
      body := jsonb_build_object(
        'from', '충남 AI 공모전 접수 <noreply@tooning.io>',
        'to',   jsonb_build_array(NEW.teacher_email),
        'cc',   jsonb_build_array('leo@tooning.io'),
        'reply_to', 'leo@tooning.io',
        'subject', v_subj,
        'html', v_html
      )
    );
  exception when others then null;   -- 메일 실패해도 접수는 정상 저장
  end;
  return NEW;
end $$;

drop trigger if exists trg_충남_접수메일_ins on public."충남콘테스트_접수";
create trigger trg_충남_접수메일_ins after insert on public."충남콘테스트_접수"
  for each row execute function public."충남_접수완료메일"();

drop trigger if exists trg_충남_접수메일_upd on public."충남콘테스트_접수";
create trigger trg_충남_접수메일_upd after update on public."충남콘테스트_접수"
  for each row when (NEW.updated_at is distinct from OLD.updated_at)
  execute function public."충남_접수완료메일"();

-- ============================================================
--  동작 확인용:
--  select public."충남콘테스트_제출"('홍길동','OO고','고 2학년','t@s.kr','me@tooning.io','웹툰','https://tooning.io/board/x',true,'{"type":"webtoon","pdf_url":"https://..."}'::jsonb);
--  select * from public."충남콘테스트_조회"('me@tooning.io');
--  select * from public."충남콘테스트_관리자목록"('5972');
-- ============================================================
