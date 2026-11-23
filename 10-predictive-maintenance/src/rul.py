"""退化趋势与剩余寿命：最小二乘斜率、阈值穿越、残差置信带。"""
import math


class Trend:
    def __init__(self, xs: list[float], ys: list[float]):
        if len(xs) < 3 or len(xs) != len(ys):
            raise ValueError("至少 3 个同长度样本")
        self.xs, self.ys = xs, ys
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        self.slope = sxy / sxx if sxx else 0.0
        self.intercept = my - self.slope * mx
        self.residual_std = math.sqrt(
            sum((y - (self.slope * x + self.intercept)) ** 2 for x, y in zip(xs, ys))
            / max(1, n - 2))

    def predict(self, x: float) -> float:
        return self.slope * x + self.intercept

    def rul(self, x_now: float, threshold: float) -> float | None:
        """按当前斜率外推穿越阈值所需时间；斜率为正（变好）时返回 None。"""
        if self.slope >= 0:
            return None
        y_now = self.predict(x_now)
        if y_now <= threshold:
            return 0.0
        return (y_now - threshold) / -self.slope

    def rul_lower(self, x_now: float, threshold: float, z: float = 1.96) -> float | None:
        """悲观估计：斜率再陡一个残差标准差，给维护排期留余量。"""
        if self.slope >= 0:
            return None
        y_now = self.predict(x_now)
        if y_now <= threshold:
            return 0.0
        return (y_now - threshold) / (-self.slope + self.residual_std)


def alert(rul: float | None, window: float) -> str:
    if rul is None:
        return "stable"
    if rul <= 0:
        return "failed"
    return "maintenance_due" if rul <= window else "watch"
