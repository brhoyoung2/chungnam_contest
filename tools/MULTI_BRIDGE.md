# 📲 텔레그램 멀티 프로젝트 브리지 — 설정 안내

봇 **하나**로 여러 프로젝트(투닝 몬스터 / 리딩 / 글쓰기 / 충남 공모전 …)를
폰 텔레그램에서 제어합니다. 텔레그램에서 프로젝트를 고르면 그 폴더에서 Claude Code가
수정 → 커밋 → push(배포) 까지 자동 처리하고 결과를 회신합니다.

```
              ┌── /use 몬스터 → [투닝 몬스터]   폴더에서 claude 실행
[폰 텔레그램] ─┼── /use 리딩   → [투닝 리딩]     폴더에서 claude 실행
   (봇 1개)   ├── /use 글쓰기 → [투닝 글쓰기]   폴더에서 claude 실행
              └── 기본       → [충남 공모전]   폴더에서 claude 실행
                         ▲ 매 메시지마다 중앙 설정을 다시 읽어 라우팅
```

- 중앙 설정: `~/.claude-tg-bridge/projects.json` (모든 프로젝트가 여기에 등록됨)
- 브리지는 메시지마다 설정을 **다시 읽으므로**, 새 프로젝트 등록 후 **재시작 불필요**.

---

## 🟦 각 프로젝트의 Claude Code 가 할 일 — "내 프로젝트 등록"

> 이 문서를 받은 프로젝트의 Claude Code 에게 아래를 그대로 부탁하세요.
> **프로젝트 루트에서** 실행하면, 그 폴더 경로가 중앙 설정에 등록됩니다.

**별칭/이름만 본인 프로젝트에 맞게 바꿔서 실행** (Git Bash 기준):

```bash
python - <<'PY'
import os, json
# ▼▼ 이 3줄만 본인 프로젝트에 맞게 수정 ▼▼
alias = "몬스터"          # 텔레그램에서 부를 짧은 별칭
name  = "투닝 몬스터"      # 표시 이름
auto_deploy = True         # 커밋 후 자동 push(배포) 여부
# ▲▲----------------------------------▲▲
cfg = os.path.join(os.path.expanduser("~"), ".claude-tg-bridge", "projects.json")
os.makedirs(os.path.dirname(cfg), exist_ok=True)
d = {}
if os.path.isfile(cfg):
    try: d = json.load(open(cfg, encoding="utf-8"))
    except Exception: d = {}
d[alias] = {"name": name, "dir": os.getcwd().replace("\\", "/"), "auto_deploy": auto_deploy}
json.dump(d, open(cfg, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("✅ 등록:", alias, "→", os.getcwd())
print("현재 등록된 프로젝트:", ", ".join(d.keys()))
PY
```

> PowerShell만 쓰는 환경이면 `tools/register_project.py`(이 저장소에 포함) 를 복사해
> `python tools\register_project.py 몬스터 "투닝 몬스터"` 로 실행해도 됩니다.

각 프로젝트(몬스터·리딩·글쓰기)에서 별칭만 바꿔 1회씩 등록하면 끝입니다.
(충남 공모전은 이미 등록되어 있습니다.)

---

## 🟩 브리지 실행 — 한 번만, 아무 PC 한 곳에서

> 브리지는 **한 곳에서 하나만** 띄웁니다(여러 개 띄우면 봇 충돌). 등록된 모든 프로젝트
> 폴더에 접근 가능한 PC에서 실행하세요.

**PowerShell**
```powershell
$env:TELEGRAM_BOT_TOKEN="<봇 토큰>"
$env:TELEGRAM_ALLOWED_CHAT_ID="8422078291"     # 본인 chat_id (쉼표로 여러 명 가능)
python tools\telegram_bridge_multi.py
```
**Git Bash**
```bash
export TELEGRAM_BOT_TOKEN="<봇 토큰>"
export TELEGRAM_ALLOWED_CHAT_ID="8422078291"
python tools/telegram_bridge_multi.py
```

---

## 🟨 텔레그램 사용법

| 입력 | 동작 |
|---|---|
| `/projects` | 등록된 프로젝트 목록 + 현재 활성 표시 |
| `/use 몬스터` | 활성 프로젝트를 '몬스터'로 전환 |
| `/current` | 현재 활성 프로젝트 확인 |
| `히어로 문구 ○○로 바꿔줘` | **현재 활성 프로젝트**에서 실행 |
| `[리딩] 버튼 색 파랑으로` | 이번 한 번만 '리딩'에서 실행(활성은 유지) |
| (사진) → 지시 | 사진을 활성 프로젝트 `inbox/`에 저장 후 함께 처리 |

작업이 끝나기 전에 연달아 보내지 말고, **회신을 받은 뒤 다음 요청**을 보내세요(순차 처리).

---

## ⚙️ 환경변수
| 변수 | 필수 | 설명 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | 봇 토큰 |
| `TELEGRAM_ALLOWED_CHAT_ID` | 권장 | 허용 chat_id(쉼표로 여러 개) |
| `BRIDGE_CONFIG` | | 설정 파일 경로(기본 `~/.claude-tg-bridge/projects.json`) |
| `CLAUDE_BIN` | | claude 실행 파일(미지정 시 자동 탐색) |
| `CLAUDE_FLAGS` | | 기본 `--dangerously-skip-permissions` |
| `RUN_TIMEOUT` | | 한 작업 최대 실행 초(기본 900) |

## ⚠️ 보안
- 봇 토큰은 비밀. `TELEGRAM_ALLOWED_CHAT_ID` 로 **본인만** 명령하도록 제한.
- `--dangerously-skip-permissions` 는 PC에서 파일수정·git·셸을 무인 실행합니다. 신뢰된 PC에서만.
- `auto_deploy:false` 로 등록하면 해당 프로젝트는 **커밋만** 하고 push/배포는 안 합니다.
- 프로젝트별 `inbox/` 는 각 프로젝트의 `.gitignore` 에 추가하세요.
