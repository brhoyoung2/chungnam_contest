#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
텔레그램 → Claude Code 멀티 프로젝트 브리지
-------------------------------------------------
봇 하나로 여러 프로젝트를 제어합니다. 텔레그램에서 프로젝트를 고르면(또는 메시지에
[별칭]을 붙이면) 해당 프로젝트 폴더에서 Claude Code(claude -p)가 실행되어 수정→커밋→
push(배포)까지 자동 처리하고 결과를 회신합니다.

의존성 없음(표준 라이브러리만). Python 3.8+

[프로젝트 설정]
  중앙 설정 파일: ~/.claude-tg-bridge/projects.json  (BRIDGE_CONFIG 로 변경 가능)
  형식:
    {
      "충남":   {"name":"투닝 충남 공모전", "dir":"C:/.../chungnam_contest", "auto_deploy": true},
      "몬스터": {"name":"투닝 몬스터",      "dir":"C:/.../tooning_monster",  "auto_deploy": true}
    }
  각 프로젝트의 Claude Code 에게 MULTI_BRIDGE.md 를 주면 자기 경로를 여기에 등록합니다.
  브리지는 매 메시지마다 이 파일을 다시 읽으므로, 새 프로젝트는 재시작 없이 즉시 반영됩니다.

[텔레그램 명령]
  /projects            등록된 프로젝트 목록 + 현재 활성 표시
  /use <이름>          활성 프로젝트 전환 (예: /use 몬스터)
  /current             현재 활성 프로젝트
  /help                도움말
  [몬스터] 메시지       이번 한 번만 '몬스터'에서 실행(활성은 그대로)
  그 외 메시지          현재 활성 프로젝트에서 실행

[환경변수]
  TELEGRAM_BOT_TOKEN        (필수)
  TELEGRAM_ALLOWED_CHAT_ID  (권장) 허용 chat_id. 쉼표로 여러 개 가능
  BRIDGE_CONFIG             설정 파일 경로(기본 ~/.claude-tg-bridge/projects.json)
  CLAUDE_BIN, CLAUDE_FLAGS, RUN_TIMEOUT  (단일 브리지와 동일)
"""
import os, sys, time, json, re, subprocess, datetime, pathlib, shutil, glob
import urllib.parse, urllib.request, urllib.error
try:
    sys.stdout.reconfigure(encoding="utf-8")   # Windows cp949 콘솔 출력 보호
except Exception:
    pass

TOKEN        = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED      = [x.strip() for x in os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "").split(",") if x.strip()]
CLAUDE_BIN   = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_FLAGS = os.environ.get("CLAUDE_FLAGS", "--dangerously-skip-permissions")
RUN_TIMEOUT  = int(os.environ.get("RUN_TIMEOUT", "1800"))
CONFIG_PATH  = os.environ.get("BRIDGE_CONFIG",
                              os.path.join(os.path.expanduser("~"), ".claude-tg-bridge", "projects.json"))

API = "https://api.telegram.org/bot" + TOKEN
ACTIVE = {}          # chat_id -> alias (활성 프로젝트)
PENDING = {}         # chat_id -> [이미지 경로...]


# ── 텔레그램 ──
def tg(method, params, post=False):
    try:
        if post:
            data = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(API + "/" + method, data=data)
            with urllib.request.urlopen(req, timeout=70) as r:
                return json.load(r)
        url = API + "/" + method + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=70) as r:
            return json.load(r)
    except Exception as e:
        print("[tg]", e); return {}


def send(chat_id, text):
    if not text:
        text = "(빈 응답)"
    if len(text) > 4000:
        text = text[:3990] + "\n…(생략)"
    tg("sendMessage", {"chat_id": chat_id, "text": text}, post=True)


def download_photo(file_id, base_dir):
    info = tg("getFile", {"file_id": file_id})
    fp = (info.get("result") or {}).get("file_path")
    if not fp:
        raise RuntimeError("getFile 실패")
    inbox = pathlib.Path(base_dir) / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(fp)[1] or ".jpg"
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = inbox / (ts + ext)
    urllib.request.urlretrieve("https://api.telegram.org/file/bot" + TOKEN + "/" + fp, dest)
    return os.path.relpath(dest, base_dir).replace("\\", "/")


# ── 프로젝트 설정 ──
def load_projects():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def match_project(projects, query):
    q = (query or "").strip().lower()
    if not q:
        return None
    for alias in projects:                       # 별칭 정확 일치
        if alias.lower() == q:
            return alias
    for alias, info in projects.items():         # 별칭/이름 부분 일치
        if q in alias.lower() or q in str(info.get("name", "")).lower():
            return alias
    return None


def projects_text(projects, chat_id):
    if not projects:
        return ("등록된 프로젝트가 없습니다.\n각 프로젝트의 Claude Code 에 MULTI_BRIDGE.md 를 주고 "
                "등록 스니펫을 실행하게 하세요. (설정: " + CONFIG_PATH + ")")
    cur = ACTIVE.get(chat_id)
    lines = ["📂 등록된 프로젝트:"]
    for alias, info in projects.items():
        mark = " ✅(활성)" if alias == cur else ""
        lines.append("• [" + alias + "] " + str(info.get("name", alias)) + mark)
    lines.append("\n전환: /use <이름>   ·   1회 지정: [이름] 메시지")
    return "\n".join(lines)


# ── Claude 실행 ──
def find_claude():
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
        return ["cmd", "/c", p]
    return [p or CLAUDE_BIN]


def run_claude(prompt, cwd):
    cmd = find_claude() + ["-p", prompt] + CLAUDE_FLAGS.split()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=RUN_TIMEOUT,
                           encoding="utf-8", errors="replace")
        out = (p.stdout or "").strip()
        if p.returncode != 0 and p.stderr:
            out += "\n[stderr]\n" + p.stderr.strip()
        return out or "(출력 없음)"
    except subprocess.TimeoutExpired:
        return "⏱️ 실행 시간 초과(RUN_TIMEOUT)."
    except FileNotFoundError:
        return "claude 실행 파일을 찾을 수 없습니다. CLAUDE_BIN 을 확인하세요."


def build_prompt(text, images, info):
    deploy = info.get("auto_deploy", True)
    has_cmd = bool(info.get("deploy_cmd"))
    steps = ["1) 먼저 요청한 화면/기능이 이 저장소에 실제로 존재하는지 확인하세요. 요청이 이 프로젝트와 무관하면"
             "(설명된 화면·기능이 코드에 없음) 아무것도 수정/커밋하지 말고, 답변 맨 앞에 정확히 '⚠️ 프로젝트 불일치'"
             "라고 쓴 뒤 이유와 함께 맞는 프로젝트로 다시 보내달라고 한국어로 안내하세요."]
    if deploy and has_cmd:
        steps.append("2) 요청이 맞으면 코드를 수정하고 git 으로 커밋하세요. (push/배포는 시스템이 처리하니 직접 하지 않아도 됩니다.)")
    elif deploy:
        steps.append("2) 요청이 맞으면 코드를 수정하고 git 으로 커밋한 뒤 origin 기본 브랜치에 push 하세요(자동배포).")
    else:
        steps.append("2) 요청이 맞으면 코드를 수정하고 git 으로 커밋만 하세요(push/배포 금지).")
    note = ("\n\n첨부 이미지(이 저장소 기준 경로): " + ", ".join(images)) if images else ""
    return ("아래는 텔레그램으로 받은 작업 지시입니다. 다음 절차로 처리하세요.\n" + "\n".join(steps) +
            " 첨부 이미지를 사이트에 쓰라는 지시면 inbox/ 에서 적절한 위치로 옮겨 커밋하세요."
            "\n마지막에 무엇을 했는지(또는 왜 안 했는지)를 한국어로 1~3줄 반드시 요약하세요." + note +
            "\n\n[지시]\n" + (text or "(텍스트 없음)"))


def git_head(cwd):
    try:
        return subprocess.run(["git", "-C", cwd, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=20,
                              encoding="utf-8", errors="replace").stdout.strip()
    except Exception:
        return ""


def git_info(cwd):
    def g(a):
        try:
            return subprocess.run(["git", "-C", cwd] + a, capture_output=True, text=True, timeout=20,
                                  encoding="utf-8", errors="replace").stdout.strip()
        except Exception:
            return ""
    last = g(["log", "-1", "--pretty=%h %s"])
    dirty = g(["status", "--porcelain"])
    ahead = g(["rev-list", "--count", "@{u}..HEAD"])
    out = []
    if last:
        out.append("최근 커밋: " + last)
    if dirty:
        out.append("⚠️ 커밋 안 된 변경 있음")
    if ahead.isdigit() and int(ahead) > 0:
        out.append("⚠️ 아직 push 안 됨(" + ahead + "개)")
    return "\n".join(out)


def run_deploy(cmd, cwd):
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=600,
                           encoding="utf-8", errors="replace")
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        urls = re.findall(r"https://[^\s\"']+", out)
        if p.returncode == 0:
            return "🚀 배포 완료" + ((": " + urls[-1]) if urls else "")
        return "⚠️ 배포 실패(코드 " + str(p.returncode) + ")\n" + out.strip()[-400:]
    except subprocess.TimeoutExpired:
        return "⏱️ 배포 시간 초과"
    except Exception as e:
        return "⚠️ 배포 오류: " + str(e)


# ── 메시지 처리 ──
def handle(msg):
    chat_id = str(msg.get("chat", {}).get("id", ""))
    if not chat_id:
        return
    if not ALLOWED:
        send(chat_id, "이 채팅의 chat_id 는 [" + chat_id + "] 입니다. TELEGRAM_ALLOWED_CHAT_ID 에 설정 후 재시작하세요.")
        return
    if chat_id not in ALLOWED:
        print("[handle] 미허용 chat_id:", chat_id); return

    projects = load_projects()
    text = (msg.get("text") or msg.get("caption") or "").strip()

    # 명령 처리
    low = text.lower()
    if low in ("/start", "/help", "도움말"):
        send(chat_id, "🤖 멀티 프로젝트 브리지\n\n/projects 목록\n/use <이름> 활성 전환\n/current 현재\n"
                      "[이름] 메시지 → 이번만 해당 프로젝트에서 실행\n그 외 메시지 → 활성 프로젝트에서 실행")
        return
    if low in ("/projects", "/list", "/프로젝트", "프로젝트", "목록"):
        send(chat_id, projects_text(projects, chat_id)); return
    if low in ("/current", "현재"):
        a = ACTIVE.get(chat_id)
        send(chat_id, ("현재 활성: [" + a + "] " + str(projects.get(a, {}).get("name", "")) if a else "활성 프로젝트가 없습니다. /use <이름>"))
        return
    m_use = re.match(r"^(?:/use|프로젝트[:：]?)\s+(.+)$", text, re.I)
    if m_use:
        alias = match_project(projects, m_use.group(1))
        if alias:
            ACTIVE[chat_id] = alias
            send(chat_id, "✅ 활성 프로젝트: [" + alias + "] " + str(projects[alias].get("name", "")) +
                          "\n경로: " + projects[alias].get("dir", "?"))
        else:
            send(chat_id, "프로젝트를 찾지 못했어요.\n\n" + projects_text(projects, chat_id))
        return

    # 인라인 1회 지정: [별칭] ... 또는 @별칭 ...
    override = None
    m_in = re.match(r"^[\[\(]([^\]\)]+)[\]\)]\s*(.*)$", text, re.S) or re.match(r"^@(\S+)\s+(.*)$", text, re.S)
    if m_in:
        alias = match_project(projects, m_in.group(1))
        if not alias:
            send(chat_id, "프로젝트 '" + m_in.group(1) + "' 를 찾지 못했어요.\n\n" + projects_text(projects, chat_id)); return
        override = alias
        text = (m_in.group(2) or "").strip()
        # [별칭] 만 단독으로 보내면 → 그 프로젝트를 활성으로 선택
        if not text and "photo" not in msg:
            ACTIVE[chat_id] = alias
            send(chat_id, "✅ 활성 프로젝트: [" + alias + "] " + str(projects[alias].get("name", "")) +
                          "\n이제 수정사항을 보내면 여기서 실행됩니다. (또는 [" + alias + "] 수정내용 형태로 한 번에)")
            return

    # 대상 프로젝트 결정
    alias = override or ACTIVE.get(chat_id)
    if not alias:
        if len(projects) == 1:
            alias = next(iter(projects))
            ACTIVE[chat_id] = alias
        else:
            send(chat_id, "먼저 프로젝트를 선택하세요.\n\n" + projects_text(projects, chat_id)); return

    info = projects.get(alias, {})
    cwd = info.get("dir", "")
    if not cwd or not os.path.isdir(cwd):
        send(chat_id, "프로젝트 [" + alias + "] 의 경로가 올바르지 않습니다: " + str(cwd)); return

    # 사진: 모았다가 지시와 함께 실행
    if "photo" in msg:
        try:
            path = download_photo(msg["photo"][-1]["file_id"], cwd)
            PENDING.setdefault(chat_id, []).append(path)
        except Exception as e:
            send(chat_id, "이미지 저장 실패: " + str(e)); return
        if not text:
            send(chat_id, "🖼️ [" + alias + "] 이미지 저장됨 (" + str(len(PENDING[chat_id])) +
                          "장). 이어서 지시를 보내면 함께 처리합니다."); return

    if not text and not PENDING.get(chat_id):
        return

    images = PENDING.pop(chat_id, [])
    send(chat_id, "🛠️ [" + alias + "] " + str(info.get("name", "")) + " 작업 시작…")
    pre = git_head(cwd)
    result = run_claude(build_prompt(text, images, info), cwd)
    post = git_head(cwd)
    mismatch = result.strip().startswith("⚠️ 프로젝트 불일치")

    head = ("⚠️ [" + alias + "] 프로젝트 불일치" if mismatch else "✅ [" + alias + "] 완료")
    parts = [head, "", result]
    # 새 커밋이 생겼고 deploy_cmd 가 있으면 시스템이 배포
    if not mismatch and info.get("deploy_cmd") and post and pre != post:
        parts.append("\n" + run_deploy(info["deploy_cmd"], cwd))
    gi = git_info(cwd)
    if gi:
        parts.append("\n— git 상태 —\n" + gi)
    send(chat_id, "\n".join(parts))


def main():
    if not TOKEN:
        print("오류: TELEGRAM_BOT_TOKEN 미설정"); sys.exit(1)
    me = tg("getMe", {})
    print("멀티 브리지 시작. 봇 @" + str((me.get("result") or {}).get("username", "?")) +
          " · 설정=" + CONFIG_PATH + " · 프로젝트 " + str(len(load_projects())) + "개")
    offset = None
    while True:
        try:
            params = {"timeout": 50}
            if offset:
                params["offset"] = offset
            data = tg("getUpdates", params)
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                tg("getUpdates", {"offset": offset, "timeout": 0})  # 즉시 확인 → 재시작 시 같은 메시지 재실행 방지
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
            print("[main] loop error:", e); time.sleep(3)


if __name__ == "__main__":
    main()
