"""分块下发：HTTP Range 解析、断点续传、分块校验、206 响应。"""
from dataclasses import dataclass

from manifest import sha256_bytes

DEFAULT_CHUNK = 4096


class RangeError(Exception):
    pass


@dataclass
class ChunkResponse:
    status: int
    start: int
    end: int
    total: int
    body: bytes
    headers: dict
    digest: str


def parse_range(header: str | None, total: int) -> tuple[int, int]:
    """只支持单区间 `bytes=a-b` / `bytes=a-` / `bytes=-n`。"""
    if not header:
        return 0, total - 1
    if not header.startswith("bytes=") or "," in header:
        raise RangeError(f"不支持的 Range：{header}")
    spec = header[6:].strip()
    if "-" not in spec:
        raise RangeError(f"Range 格式错误：{header}")
    a, b = spec.split("-", 1)
    if a == "":
        n = int(b)
        if n <= 0:
            raise RangeError("后缀长度必须为正")
        start = max(0, total - n)
        end = total - 1
    else:
        start = int(a)
        end = int(b) if b else total - 1
    if start > end or start >= total:
        raise RangeError(f"区间越界：{start}-{end} / total={total}")
    return start, min(end, total - 1)


def serve(firmware: bytes, range_header: str | None = None,
          max_chunk: int = DEFAULT_CHUNK) -> ChunkResponse:
    total = len(firmware)
    if total == 0:
        raise RangeError("固件为空")
    start, end = parse_range(range_header, total)
    if end - start + 1 > max_chunk:
        end = start + max_chunk - 1           # 服务端限制单次下发大小
    body = firmware[start:end + 1]
    return ChunkResponse(status=206 if range_header else 200, start=start, end=end,
                         total=total, body=body,
                         headers={"Accept-Ranges": "bytes",
                                  "Content-Range": f"bytes {start}-{end}/{total}",
                                  "Content-Length": str(len(body)),
                                  "ETag": sha256_bytes(firmware)[:16]},
                         digest=sha256_bytes(body))


def next_offset(resp: ChunkResponse) -> int | None:
    return resp.end + 1 if resp.end + 1 < resp.total else None
