"""演示：清单签名/校验、Range 断点续传、设备状态机、灰度与回滚。"""
from delivery import serve, next_offset
from device import Device, UpdateError
from manifest import build, check, sha256_bytes
from rollout import Rollout, bucket_of

SECRET = b"demo-secret"


def main():
    fw = bytes((i * 7) % 256 for i in range(10_000))
    m = build("1.2.0", fw, SECRET, min_battery=30, notes="修复低温重启")
    print("== 清单 ==")
    print("  ", {k: (v[:16] + "…" if k == "sha256" else v) for k, v in m.items()})
    print("  校验（正常）：", check(m, fw, SECRET, current_version="1.1.0", battery=80))
    print("  校验（被改包）：", check(m, fw[:-1] + b"\x00", SECRET)["problems"])
    print("  校验（电量不足）：", check(m, fw, SECRET, battery=10)["problems"])

    print("\n== 断点续传 ==")
    r1 = serve(fw, "bytes=0-")
    print(f"  第一段 {r1.start}-{r1.end}/{r1.total} 状态 {r1.status} "
          f"Content-Range={r1.headers['Content-Range']}")
    off = next_offset(r1)
    r2 = serve(fw, f"bytes={off}-")
    print(f"  续传段 {r2.start}-{r2.end}（偏移 {off}），累计 {r2.end + 1} 字节")
    tail = serve(fw, "bytes=-100")
    print(f"  末尾段 {tail.start}-{tail.end}（{len(tail.body)} 字节）")

    print("\n== 设备升级 ==")
    dev = Device("dev-001", version="1.1.0", battery=80)
    dev.begin(m, now=0)
    offset = 0
    while offset is not None:
        r = serve(fw, f"bytes={offset}-")
        dev.accept_chunk(r.start, r.body, r.digest, chunk_sha=r.digest)
        offset = next_offset(r)
    print("  下载完成状态：", dev.finish_download(m, len(fw)), "缓冲", len(dev.buffer), "字节")
    print("  校验（包体哈希正确）：", dev.verify(sha256_bytes(bytes(dev.buffer)) == m["sha256"]))
    print("  刷写→重启→启动：", dev.flash(), dev.boot(True), "版本", m["version"])

    bad = Device("dev-002", version="1.1.0")
    bad.begin(m, now=0)
    r = serve(fw, "bytes=0-")
    print("\n  乱序块测试：", end="")
    try:
        bad.accept_chunk(r.end + 1, r.body, r.digest)
    except UpdateError as e:
        print(e)
    print("  状态仍为下载中（未污染缓冲）：", bad.state)
    try:
        bad.finish_download(m, len(fw))
    except UpdateError as e:
        print("  包体不完整：", e, "| 状态", bad.state)
    print("  回滚：", bad.rollback("1.1.0"))

    print("\n== 灰度 ==")
    ro = Rollout(failure_threshold=0.1, min_samples=10)
    ids = [f"dev-{i:03d}" for i in range(40)]
    print(f"  第一批（{ro.percent}%）命中设备：",
          sum(1 for d in ids if ro.eligible(d)), "/", len(ids))
    for d in ids:
        if ro.eligible(d):
            ro.report(d, ok=True)
    print("  推进：", ro.promote(), "当前比例", ro.percent, "%")
    for d in ids:
        if ro.eligible(d):
            ro.report(d, ok=True)
    print("  再推进：", ro.promote(), "当前比例", ro.percent, "%")
    ro2 = Rollout(failure_threshold=0.1, min_samples=10)
    for i in range(12):
        ro2.report(f"bad-{i}", ok=(i < 8))
    print("  失败率过高：", ro2.report("bad-12", ok=True), "| 已回滚", ro2.rolled_back)
    print("  分桶示例：", {d: bucket_of(d) for d in ids[:5]})


if __name__ == "__main__":
    main()
