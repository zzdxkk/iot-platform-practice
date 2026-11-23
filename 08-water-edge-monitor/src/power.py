"""功耗预算：睡眠/测量/发射分项电流，估算日耗与电池寿命。"""
from dataclasses import dataclass

UA_PER_MA = 1000.0


@dataclass
class PowerProfile:
    sleep_ua: float = 12.0           # 睡眠电流（微安）
    measure_ma: float = 6.0          # 测量时电流
    measure_s: float = 2.0
    tx_ma: float = 25.0              # 发射电流
    tx_s: float = 0.6
    measures_per_day: int = 24
    reports_per_day: int = 4

    def daily_mah(self) -> float:
        sleep = self.sleep_ua / UA_PER_MA * 24
        measure = self.measure_ma * self.measure_s / 3600 * self.measures_per_day
        tx = self.tx_ma * self.tx_s / 3600 * self.reports_per_day
        return round(sleep + measure + tx, 4)

    def life_days(self, capacity_mah: float, derating: float = 0.85) -> float:
        usable = capacity_mah * derating          # 温度/自放电余量
        daily = self.daily_mah()
        return round(usable / daily, 1) if daily > 0 else float("inf")

    def meets(self, capacity_mah: float, target_years: float) -> dict:
        days = self.life_days(capacity_mah)
        need = target_years * 365
        return {"life_days": days, "target_days": round(need, 1),
                "ok": days >= need, "daily_mah": self.daily_mah()}


def budget(profile: PowerProfile, capacity_mah: float, target_years: float) -> dict:
    return profile.meets(capacity_mah, target_years)
