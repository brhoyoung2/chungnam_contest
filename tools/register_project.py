#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
멀티 브리지에 '현재 폴더(프로젝트)'를 등록합니다.
프로젝트 루트에서 실행하세요.

  python tools/register_project.py <별칭> "<표시이름>" [auto_deploy(true/false)]

예)
  python tools/register_project.py 충남 "투닝 충남 공모전" true
  python tools/register_project.py 몬스터 "투닝 몬스터"

설정은 ~/.claude-tg-bridge/projects.json (BRIDGE_CONFIG 로 변경 가능) 에 저장됩니다.
브리지는 매 메시지마다 이 파일을 다시 읽으므로 재시작이 필요 없습니다.
"""
import os, sys, json
try:
    sys.stdout.reconfigure(encoding="utf-8")   # Windows cp949 콘솔에서도 이모지/한글 출력
except Exception:
    pass

if len(sys.argv) < 2:
    print("사용법: python tools/register_project.py <별칭> \"<표시이름>\" [auto_deploy]")
    sys.exit(1)

alias = sys.argv[1].strip()
name = sys.argv[2].strip() if len(sys.argv) > 2 else alias
auto = True
if len(sys.argv) > 3:
    auto = sys.argv[3].strip().lower() not in ("false", "0", "no", "n")

cfg_path = os.environ.get("BRIDGE_CONFIG",
                          os.path.join(os.path.expanduser("~"), ".claude-tg-bridge", "projects.json"))
os.makedirs(os.path.dirname(cfg_path), exist_ok=True)

data = {}
if os.path.isfile(cfg_path):
    try:
        with open(cfg_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

data[alias] = {"name": name, "dir": os.getcwd().replace("\\", "/"), "auto_deploy": auto}
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ 등록됨: [" + alias + "] " + name)
print("   경로: " + os.getcwd())
print("   설정파일: " + cfg_path)
print("   현재 등록된 프로젝트: " + ", ".join(data.keys()))
