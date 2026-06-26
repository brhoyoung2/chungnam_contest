#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
현재 폴더를 Vercel 프로덕션으로 배포하고, (선택) 커스텀 도메인을 그 배포로 연결한다.
일부 프로젝트는 `vercel --prod` 만으론 커스텀 도메인이 최신 배포로 자동 이동하지 않으므로,
배포 후 `vercel alias set` 으로 도메인을 명시적으로 연결한다.

사용:  python vercel_deploy.py [도메인]
예)    python vercel_deploy.py mon.tooning.io
"""
import sys, re, subprocess

domain = sys.argv[1].strip() if len(sys.argv) > 1 else ""


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


p = run("vercel --prod --yes")
out = (p.stdout or "") + "\n" + (p.stderr or "")

url = ""
for line in out.splitlines():
    if "Production:" in line:
        m = re.search(r"https://\S+\.vercel\.app", line)
        if m:
            url = m.group(0)
if not url:
    m = re.search(r"https://[a-z0-9-]+\.vercel\.app", out)
    if m:
        url = m.group(0)

if url and domain:
    a = run('vercel alias set "%s" %s' % (url, domain))
    print((a.stdout or "") + (a.stderr or ""))
    if a.returncode == 0:
        print("🚀 배포 완료: https://%s (→ %s)" % (domain, url))
    else:
        print("⚠️ 배포는 됐으나 도메인 연결 실패: %s" % url)
elif url:
    print("🚀 배포 완료: %s" % url)
else:
    print("⚠️ 배포 실패\n" + out.strip()[-400:])
