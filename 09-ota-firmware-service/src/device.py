"""设备端升级状态机：断点续传、校验、刷写、看门狗超时、失败回滚。"""
from dataclasses import dataclass, field

IDLE, DOWNLOADING, VERIFYING, FLASHING, REBOOTING, SUCCESS, FAILED = (
    "idle", "downloading", "verifying", "flashing", "rebooting", "success", "failed")


class UpdateError(Exception):
    pass


@dataclass
class Device:
    device_id: str
    version: str = "1.0.0"
    battery: int = 100
    state: str = IDLE
    buffer: bytearray = field(default_factory=bytearray)
    expected_offset: int = 0
    target: str = ""
    attempts: int = 0
    history: list = field(default_factory=list)

    def begin(self, manifest: dict, now: float) -> str:
        if self.state == DOWNLOADING:
            raise UpdateError("已在下载中")
        self.target = manifest["version"]
        self.buffer = bytearray()
        self.expected_offset = 0
        self.state = DOWNLOADING
        self.attempts += 1
        self.history.append((now, "begin", self.target))
        return self.state

    def accept_chunk(self, start: int, body: bytes, digest: str, chunk_sha=None) -> str:
        if self.state != DOWNLOADING:
            raise UpdateError(f"状态不允许写块：{self.state}")
        if chunk_sha and chunk_sha != digest:
            self.state = FAILED
            raise UpdateError("分块 SHA-256 不符")
        if start != self.expected_offset:
            # 乱序/重复块一律拒绝，避免把固件拼错
            raise UpdateError(f"偏移不符：收到 {start}，期望 {self.expected_offset}")
        self.buffer.extend(body)
        self.expected_offset = start + len(body)
        return self.state

    def finish_download(self, manifest: dict, expected_size: int) -> str:
        if self.state != DOWNLOADING:
            raise UpdateError(f"状态不允许收尾：{self.state}")
        if len(self.buffer) != expected_size or len(self.buffer) != manifest["size"]:
            self.state = FAILED
            raise UpdateError(f"固件长度不符：{len(self.buffer)} != {manifest['size']}")
        self.state = VERIFYING
        return self.state

    def verify(self, ok: bool) -> str:
        if self.state != VERIFYING:
            raise UpdateError(f"状态不允许校验：{self.state}")
        if not ok:
            self.state = FAILED
            return self.state
        self.state = FLASHING
        return self.state

    def flash(self, ok: bool = True) -> str:
        if self.state != FLASHING:
            raise UpdateError(f"状态不允许刷写：{self.state}")
        self.state = REBOOTING if ok else FAILED
        return self.state

    def boot(self, ok: bool = True) -> str:
        if self.state != REBOOTING:
            raise UpdateError(f"状态不允许启动：{self.state}")
        self.state = SUCCESS if ok else FAILED
        return self.state

    def rollback(self, previous_version: str) -> dict:
        """校验/启动失败后回到旧版本，并把目标清空。"""
        self.state = FAILED
        self.version = previous_version
        self.buffer = bytearray()
        self.expected_offset = 0
        return {"state": self.state, "version": self.version,
                "rolled_back_to": previous_version}

    def watchdog(self, now: float, last_event_at: float, timeout: float) -> bool:
        """下载/刷写阶段超时判定，超时即判失败（设备侧需自行回滚）。"""
        if self.state in (DOWNLOADING, VERIFYING, FLASHING, REBOOTING) and \
                now - last_event_at > timeout:
            self.state = FAILED
            return True
        return False
