# 📲 텔레그램 → Claude Code 자동 수정·배포 브리지

폰 텔레그램에서 "이 부분 이렇게 고쳐줘 (+사진)" 을 보내면, PC의 Claude Code가
코드를 수정 → `git commit` → `git push`(배포) 까지 자동으로 처리하고 결과를 회신합니다.

```
[폰 텔레그램] ──메시지/사진──▶ [PC: telegram_bridge.py] ──claude -p──▶ [Claude Code]
       ▲                                                                    │ 수정·커밋·push·배포
       └────────────── "✅ 완료 + 요약" 회신 ◀───────────────────────────────┘
```

- 단일 파일, **의존성 없음**(파이썬 표준 라이브러리). Python 3.8+
- 인바운드(명령·이미지)는 텔레그램 공식 Bot API 사용 — 무료·약관 OK.

---

## 1. 봇 만들기
1. 텔레그램에서 **@BotFather** 검색 → `/newbot` → 이름 지정
2. 발급된 **토큰**(`123456:ABC...`) 복사

## 2. 실행
**Windows PowerShell**
```powershell
$env:TELEGRAM_BOT_TOKEN="123456:ABC..."
$env:REPO_DIR="C:\Users\user\Downloads\code\chungnam_contest"
python tools\telegram_bridge.py
```
**Git Bash / macOS / Linux**
```bash
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export REPO_DIR="/c/Users/user/Downloads/code/chungnam_contest"
python tools/telegram_bridge.py
```

## 3. 본인만 사용하도록 잠그기 (중요)
봇에게 아무 메시지나 보내면 → 봇이 **이 채팅의 chat_id** 를 알려줍니다.
그 값을 환경변수에 넣고 재시작하세요. (이때부터 본인만 명령 실행 가능)
```powershell
$env:TELEGRAM_ALLOWED_CHAT_ID="123456789"
```

## 4. 사용
- 텍스트만: `"히어로 부제를 ○○로 바꿔줘"` → 수정·배포 후 요약 회신
- 사진 먼저 보내고 → 이어서 `"이 이미지를 보드 가이드 2단계에 넣어줘"`
  (사진은 `inbox/` 에 저장되고, Claude가 필요한 위치(`image/` 등)로 옮겨 커밋)

---

## 환경변수
| 변수 | 필수 | 설명 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | BotFather 토큰 |
| `TELEGRAM_ALLOWED_CHAT_ID` | 권장 | 허용할 본인 chat_id (미설정 시 실행 안 하고 chat_id만 안내) |
| `REPO_DIR` | | 작업 저장소 경로(기본: 현재 폴더) |
| `CLAUDE_BIN` | | `claude` 실행 파일 경로(기본: `claude`) |
| `CLAUDE_FLAGS` | | 기본 `--dangerously-skip-permissions` |
| `RUN_TIMEOUT` | | 한 작업 최대 실행 초(기본 900) |

## ⚠️ 보안 주의
- **봇 토큰은 비밀**. 공개 저장소·채팅에 노출 금지.
- `TELEGRAM_ALLOWED_CHAT_ID` 를 **반드시 설정**해 본인만 명령하도록 제한.
- `--dangerously-skip-permissions` 는 PC에서 파일수정·git·셸 명령을 **무인 실행**합니다.
  화이트리스트(chat_id)와 함께만 사용하고, 신뢰된 PC에서만 구동하세요.
- PC가 켜져 있고 브리지가 실행 중일 때만 동작합니다(백그라운드 실행/서비스 등록 권장).

## 동작 방식 메모
- 텔레그램 `getUpdates` 롱폴링(50초) → 새 메시지 처리.
- 사진은 가장 큰 해상도를 `inbox/`(gitignore됨)에 저장 후, 지시 텍스트와 함께 Claude에 전달.
- Claude는 `claude -p "<지시>"` 로 이 저장소에서 실행되어 수정→커밋→push 수행.
