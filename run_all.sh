#!/usr/bin/env bash
# 逐个运行每个工程的演示入口与单元测试；任一环节失败即以非 0 退出。
set -u
BASE="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE" || exit 1

TOTAL_TESTS=0
FAILED=0

fail() {
  FAILED=$((FAILED + 1))
  echo "    FAIL: $1"
}

for d in "$BASE"/0* "$BASE"/10-*; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  echo ""
  echo ">>> $name"

  # 1) 演示入口：统一约定为 src/demo.py，必须退出码 0 且打印内容
  demo_ok=1
  if [ ! -f "$d/src/demo.py" ]; then
    echo "    FAIL: 缺少 src/demo.py"
    demo_ok=0
  else
    out="$( cd "$d" && python3 src/demo.py 2>&1 )"
    rc=$?
    if [ $rc -ne 0 ]; then
      echo "    FAIL: src/demo.py 退出码 $rc"
      printf '%s\n' "$out" | tail -8
      demo_ok=0
    elif [ -z "$out" ]; then
      echo "    FAIL: src/demo.py 没有任何输出"
      demo_ok=0
    fi
  fi
  [ $demo_ok -eq 1 ] && echo "    OK   演示入口全部正常"

  # 2) 单元测试
  out="$( cd "$d" && python3 -m unittest discover -s tests 2>&1 )"
  rc=$?
  n="$(printf '%s' "$out" | grep -oE 'Ran [0-9]+ test' | grep -oE '[0-9]+')"
  n="${n:-0}"
  if [ $rc -eq 0 ]; then
    echo "    OK   单元测试 $n 项通过"
    TOTAL_TESTS=$((TOTAL_TESTS + n))
  else
    echo "    FAIL: 单元测试未通过"
    printf '%s\n' "$out" | tail -10
    fail "$name 单元测试"
  fi
  [ $demo_ok -eq 0 ] && fail "$name 演示入口"
done

# 3) 01 的 HTTP 接口单独冒烟（server 常驻，不适合放进上面的循环）
echo ""
echo ">>> 01-document-qa HTTP 接口冒烟"
python3 - "$BASE/01-document-qa" <<'PY' || fail "01 HTTP 接口"
import json, os, subprocess, sys, time, urllib.request

cwd = sys.argv[1]
port = "8099"
env = dict(os.environ, PORT=port)
p = subprocess.Popen([sys.executable, "src/server.py"], cwd=cwd, env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
try:
    deadline = time.time() + 8
    body = None
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/ask",
                data=json.dumps({"question": "年假几天"}).encode(),
                headers={"Content-Type": "application/json"})
            body = json.loads(urllib.request.urlopen(req, timeout=2).read().decode())
            break
        except Exception:
            time.sleep(0.3)
    assert body and "answer" in body and body.get("citations"), f"无有效返回：{body}"
    print(f"    OK   POST /ask -> {body['answer']}")
finally:
    p.terminate()
    try:
        p.wait(timeout=3)
    except subprocess.TimeoutExpired:
        p.kill()
PY

echo ""
echo "================ 汇总 ================"
echo "单元测试通过：$TOTAL_TESTS 项    失败项：$FAILED"
if [ $FAILED -eq 0 ]; then
  echo "[结论] 全部演示入口可运行，单元测试全绿。"
else
  exit 1
fi
