"""固件清单：版本比较、SHA-256 校验、HMAC 签名与防篡改。"""
import hashlib
import hmac
import json
import re
from functools import total_ordering


class ManifestError(Exception):
    pass


SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@total_ordering
class Version:
    def __init__(self, text: str):
        m = SEMVER.match(text.strip())
        if not m:
            raise ManifestError(f"版本号格式错误：{text}")
        self.text = text.strip().lstrip("v")
        self.tuple = tuple(int(x) for x in m.groups())

    def __lt__(self, other: "Version"):
        if not isinstance(other, Version):
            return NotImplemented
        return self.tuple < other.tuple

    def __eq__(self, other):
        return isinstance(other, Version) and self.tuple == other.tuple

    def __str__(self):
        return self.text


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(manifest: dict) -> bytes:
    """签名只覆盖可变字段，键排序 + 紧凑分隔符，保证两端一致。"""
    body = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode()


def sign(manifest: dict, secret: bytes) -> dict:
    out = dict(manifest)
    out["signature"] = hmac.new(secret, canonical(manifest), hashlib.sha256).hexdigest()
    return out


def verify(manifest: dict, secret: bytes) -> bool:
    sig = manifest.get("signature")
    if not sig:
        raise ManifestError("清单缺少 signature")
    expect = hmac.new(secret, canonical(manifest), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expect)


def build(version: str, firmware: bytes, secret: bytes, min_battery: int = 20,
          notes: str = "") -> dict:
    Version(version)
    return sign({
        "version": str(Version(version)),
        "size": len(firmware),
        "sha256": sha256_bytes(firmware),
        "min_battery": min_battery,
        "notes": notes,
    }, secret)


def check(manifest: dict, firmware: bytes, secret: bytes,
          current_version: str | None = None, battery: int = 100) -> dict:
    problems = []
    try:
        if not verify(manifest, secret):
            problems.append("签名不匹配")
    except ManifestError as e:
        problems.append(str(e))
    if len(firmware) != manifest.get("size"):
        problems.append(f"包体大小不符：{len(firmware)} != {manifest.get('size')}")
    if sha256_bytes(firmware) != manifest.get("sha256"):
        problems.append("SHA-256 不符")
    if battery < int(manifest.get("min_battery", 0)):
        problems.append(f"电量不足：{battery}% < {manifest.get('min_battery')}%")
    if current_version:
        try:
            if Version(manifest["version"]) <= Version(current_version):
                problems.append("版本不高于当前版本，跳过")
        except ManifestError as e:
            problems.append(str(e))
    return {"ok": not problems, "problems": problems}
