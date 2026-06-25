#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
텔레그램 → Claude Code 브리지
--------------------------------
폰 텔레그램에서 보낸 "수정 요청(+사진)"을 받아, 이 저장소에서 Claude Code를
헤드리스(claude -p)로 실행해 코드 수정 → git commit → push(배포)까지 자동 처리하고
결과를 다시 텔레그램으로 회신합니다.

의존성 없음(파이썬 표준 라이브러리만 사용). Python 3.8+

[빠른 설정]
  1) 텔레그램 @BotFather 에서 봇 생성 → 토큰 발급
  2) 환경변수 설정 후 실행:
       (Git Bash / Linux / macOS)
         export TELEGRAM_BOT_TOKEN="123456:ABC..."
         python tools/telegram_bridge.py
       (Windows PowerShell)
         $env:TELEGRAM_BOT_TOKEN="123456:ABC..."
         python tools\telegram_bridge.py
  3) 봇에게 아무 메시지나 보내면 → 봇이 "이 채팅의 chat_id" 를 알려줍니다.
       그 값을 TELEGRAM_ALLOWED_CHAT_ID 에 넣고 재시작하면 본인만 사용 가능.
  4) 이후 "히어로 부제를 ~로 바꿔줘" 처럼 보내면 자동 수정·배포됩니다.

[환경변수]
  TELEGRAM_BOT_TOKEN        (필수) 봇 토큰
  TELEGRAM_ALLOWED_CHAT_ID  (권장) 허용할 본인 chat_id. 비우면 누구나 chat_id 확인만 가능
  REPO_DIR                  작업할 저장소 경로(기본: 현재 폴더)
  CLAUDE_BIN                claude 실행 파일(기본: "claude")
  CLAUDE_FLAGS             claude 플래그(기본: "--dangerously-skip-permissions")
  RUN_TIMEOUT              한 작업 최대 실행 초(기본: 900)

⚠️ 보안: 봇 토큰은 비밀로. TELEGRAM_ALLOWED_CHAT_ID 를 꼭 설정해 본인만 명령하도록
   제한하세요. --dangerously-skip-permissions 는 PC에서 파일수정·git·명령을 무인 실행하므로
   반드시 화이트리스트(chat_id) 와 함께 쓰세요.
"""
import os, sys, time, json, subprocess, datetime, pathlib, shutil, glob
import urllib.parse, urllib.request, urllib.error

TOKEN        = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED      = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
REPO_DIR     = os.environ.get("REPO_DIR", os.getcwd())
CLAUDE_BIN   = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_FLAGS = os.environ.get("CLAUDE_FLAGS", "--dangerously-skip-permissions")
RUN_TIMEOUT  = int(os.environ.get("RUN_TIMEOUT", "900"))

API   = "https://api.telegram.org/bot" + TOKEN
INBOX = pathlib.Path(REPO_DIR) / "inbox"
PENDING_IMAGES = []   # 지시 메시지가 올 때까지 모아둘 첨부 이미지 경로


def tg(method, params, post=False):
    """텔레그램 API 호출 (표준 라이브러리)."""
    try:
        if post:
            data = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(API + "/" + method, data=data)
            with urllib.request.urlopen(req, timeout=70) as r:
                return json.load(r)
        else:
            url = API + "/" + method + "?" + urllib.parse.urlencode(params)
            with urllib.request.urlopen(url, timeout=70) as r:
                return json.load(r)
    except urllib.error.URLError as e:
        print("[tg] network error:", e)
        return {}
    except Exception as e:
        print("[tg] error:", e)
        return {}


def send(chat_id, text):
    """텔레그램으로 메시지 전송(4096자 제한 → 4000자에서 자름)."""
    if not text:
        text = "(빈 응답)"
    if len(text) > 4000:
        text = text[:3990] + "\n…(생략)"
    tg("sendMessage", {"chat_id": chat_id, "text": text}, post=True)


def download_photo(file_id):
    """텔레그램 사진을 inbox/ 에 저장하고 레포 기준 상대경로 반환."""
    info = tg("getFile", {"file_id": file_id})
    fp = (info.get("result") or {}).get("file_path")
    if not fp:
        raise RuntimeError("getFile 실패")
    INBOX.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(fp)[1] or ".jpg"
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = INBOX / (ts + ext)
    url = "https://api.telegram.org/file/bot" + TOKEN + "/" + fp
    urllib.request.urlretrieve(url, dest)
    return os.path.relpath(dest, REPO_DIR).replace("\\", "/")


def find_claude():
    """claude 실행 파일을 견고하게 탐색해 실행 prefix(list) 반환.
    Windows npm 전역설치는 claude(확장자 없음)/claude.cmd 라 subprocess가 직접 못 찾으므로
    네이티브 claude.exe 를 우선 사용한다."""
    p = shutil.which(CLAUDE_BIN)
    if p and p.lower().endswith(".exe"):
        return [p]
    home = os.path.expanduser("~")
    cands = [
        os.path.join(home, "AppData", "Roaming", "npm", "node_modules",
                     "@anthropic-ai", "claude-code", "bin", "claude.exe"),
        os.path.join(home, ".local", "bin", "claude.exe"),
        os.path.join(home, ".local", "bin", "claude"),
    ]
    cands += glob.glob(os.path.join(home, "AppData", "Roaming", "npm", "node_modules",
                                    "@anthropic-ai", "claude-code", "bin", "claude*"))
    for c in cands:
        if os.path.isfile(c):
            return [c]
    if p and p.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", p]            # 폴백: 배치 래퍼는 cmd 경유
    return [p or CLAUDE_BIN]


def run_claude(prompt):
    """Claude Code 를 헤드리스로 실행하고 최종 출력 텍스트 반환."""
    cmd = find_claude() + ["-p", prompt] + CLAUDE_FLAGS.split()
    try:
        p = subprocess.run(cmd, cwd=REPO_DIR, capture_output=True,
                           text=True, timeout=RUN_TIMEOUT)
        out = (p.stdout or "").strip()
        if p.returncode != 0 and p.stderr:
            out += "\n[stderr]\n" + p.stderr.strip()
        return out or "(출력 없음)"
    except subprocess.TimeoutExpired:
        return "⏱️ 실행 시간 초과(RUN_TIMEOUT). 작업이 길면 값을 늘려보세요."
    except FileNotFoundError:
        return ("'" + CLAUDE_BIN + "' 실행 파일을 찾을 수 없습니다. "
                "CLAUDE_BIN 환경변수로 claude 경로를 지정하세요.")


def build_prompt(text, images):
    note = ""
    if images:
        note = ("\n\n첨부 이미지(이 저장소 기준 경로, 필요하면 Read 로 열어보세요): "
                + ", ".join(images))
    return (
        "아래는 텔레그램으로 받은 작업 지시입니다. 이 저장소에서 요청대로 코드를 수정한 뒤, "
        "변경 사항을 git 으로 커밋하고 origin main 에 push 하여 배포까지 완료하세요. "
        "첨부 이미지를 사이트에 사용하라는 지시라면 inbox/ 에서 적절한 위치(예: image/)로 "
        "옮겨 커밋하세요. 작업을 마치면 무엇을 어떻게 했는지 한국어로 1~3줄 요약하세요." + note +
        "\n\n[지시]\n" + (text or "(텍스트 없음)")
    )


def handle(msg):
    chat_id = str(msg.get("chat", {}).get("id", ""))
    if not chat_id:
        return

    # chat_id 화이트리스트
    if not ALLOWED:
        send(chat_id, "이 채팅의 chat_id 는 [" + chat_id + "] 입니다.\n"
                      "환경변수 TELEGRAM_ALLOWED_CHAT_ID 에 이 값을 설정하고 브리지를 재시작하면, "
                      "본인만 명령을 실행할 수 있습니다. (지금은 보안을 위해 작업을 실행하지 않습니다.)")
        return
    if chat_id != ALLOWED:
        print("[handle] 허용되지 않은 chat_id 무시:", chat_id)
        return

    text = msg.get("text") or msg.get("caption") or ""

    # 사진 처리: 모아두고, 지시 텍스트가 오면 함께 실행
    if "photo" in msg:
        try:
            path = download_photo(msg["photo"][-1]["file_id"])  # 가장 큰 해상도
            PENDING_IMAGES.append(path)
        except Exception as e:
            send(chat_id, "이미지 저장 실패: " + str(e))
            return
        if not text:
            send(chat_id, "🖼️ 이미지 저장됨 (" + str(len(PENDING_IMAGES)) +
                          "장). 이어서 수정 지시를 보내면 함께 처리합니다.")
            return

    if not text and not PENDING_IMAGES:
        return

    images = PENDING_IMAGES[:]
    PENDING_IMAGES.clear()

    send(chat_id, "🛠️ 작업 시작… (수정 → 커밋 → push → 배포)")
    result = run_claude(build_prompt(text, images))
    send(chat_id, "✅ 완료\n\n" + result)


def main():
    if not TOKEN:
        print("오류: TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
    me = tg("getMe", {})
    uname = (me.get("result") or {}).get("username", "?")
    print("브리지 시작. 봇 @" + str(uname) + " 대기 중…  (REPO_DIR=" + REPO_DIR + ")")
    if not ALLOWED:
        print("주의: TELEGRAM_ALLOWED_CHAT_ID 미설정 — 메시지를 보내 chat_id 를 먼저 확인하세요.")
    offset = None
    while True:
        try:
            params = {"timeout": 50}
            if offset:
                params["offset"] = offset
            data = tg("getUpdates", params)
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                try:
                    handle(msg)
                except Exception as e:
                    cid = str(msg.get("chat", {}).get("id", ""))
                    if cid:
                        send(cid, "오류: " + str(e))
                    print("[main] handle error:", e)
        except Exception as e:
            print("[main] loop error:", e)
            time.sleep(3)


if __name__ == "__main__":
    main()
