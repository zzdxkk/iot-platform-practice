"""OTA 固件升级服务：分包 -> CRC32 校验 -> 断点续传 -> 版本比较 -> 灰度发布。"""
import zlib, hashlib

def chunk_firmware(data: bytes, size=256):
    return [data[i:i+size] for i in range(0, len(data), size)]

def shard_checksum(chunks):
    return [zlib.crc32(c) & 0xFFFFFFFF for c in chunks]

def verify(data, checksums, size=256):
    chunks = chunk_firmware(data, size)
    return len(chunks) == len(checksums) and shard_checksum(chunks) == checksums

def version_gt(a, b):
    pa = [int(x) for x in a.lstrip("v").split(".")]
    pb = [int(x) for x in b.lstrip("v").split(".")]
    return (pa + [0]*3)[:3] > (pb + [0]*3)[:3]

class OTAJob:
    def __init__(self, version, data, size=256):
        self.version = version
        self.chunks = chunk_firmware(data, size)
        self.checksums = shard_checksum(self.chunks)
        self.received = {}
    def deliver(self, idx, chunk, corrupt=False):
        b = bytearray(chunk)
        if corrupt and b: b[0] ^= 0xFF
        ok = (zlib.crc32(bytes(b)) & 0xFFFFFFFF) == self.checksums[idx]
        if ok: self.received[idx] = bytes(b)
        return ok
    def progress(self): return round(len(self.received) / len(self.chunks), 3)
    def assemble(self):
        if len(self.received) != len(self.chunks): return None
        return b"".join(self.received[i] for i in sorted(self.received))

def canary(devices, ratio=0.2):
    return [d for i, d in enumerate(devices) if i < max(1, int(len(devices) * ratio))]

if __name__ == "__main__":
    fw = b"FIRMWARE" * 60
    job = OTAJob("v1.2.0", fw)
    for i, c in enumerate(job.chunks): job.deliver(i, c)
    print("版本可升级:", version_gt("v1.2.0", "v1.1.9"))
    print("进度:", job.progress(), "校验一致:", verify(job.assemble(), job.checksums))
    print("灰度设备:", canary([f"dev{i}" for i in range(10)]))
