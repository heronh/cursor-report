"""Geração de gráficos do relatório de uso."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

plt.style.use("seaborn-v0_8-whitegrid")


def _usd(value: float) -> str:
    return f"${value:,.2f}"


def aggregate_daily_spend(events: list[dict]) -> dict[date, float]:
    daily: dict[date, float] = defaultdict(float)
    for event in events:
        timestamp = event.get("timestamp")
        if not timestamp:
            continue
        day = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).date()
        daily[day] += float(event.get("chargedCents", 0) or 0) / 100
    return dict(daily)


def aggregate_daily_tokens(events: list[dict]) -> dict[date, int]:
    daily: dict[date, int] = defaultdict(int)
    for event in events:
        timestamp = event.get("timestamp")
        token_usage = event.get("tokenUsage")
        if not timestamp or not token_usage:
            continue
        day = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).date()
        daily[day] += int(token_usage.get("inputTokens", 0) or 0)
        daily[day] += int(token_usage.get("outputTokens", 0) or 0)
        daily[day] += int(token_usage.get("cacheWriteTokens", 0) or 0)
        daily[day] += int(token_usage.get("cacheReadTokens", 0) or 0)
    return dict(daily)


def sum_spend(events: list[dict]) -> float:
    return sum(float(event.get("chargedCents", 0) or 0) for event in events) / 100


def sum_tokens(events: list[dict]) -> int:
    total = 0
    for event in events:
        token_usage = event.get("tokenUsage")
        if not token_usage:
            continue
        total += int(token_usage.get("inputTokens", 0) or 0)
        total += int(token_usage.get("outputTokens", 0) or 0)
        total += int(token_usage.get("cacheWriteTokens", 0) or 0)
        total += int(token_usage.get("cacheReadTokens", 0) or 0)
    return total


def _format_tokens(value: float, _: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{int(value)}"


def create_daily_value_chart(
    daily_spend: dict[date, float],
    start: date,
    end: date,
    output_path: Path,
) -> Path:
    days: list[date] = []
    values: list[float] = []
    current = start
    while current <= end:
        days.append(current)
        values.append(daily_spend.get(current, 0.0))
        current = current.fromordinal(current.toordinal() + 1)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(days, values, color="#2563eb", width=0.8, edgecolor="white", linewidth=0.4)
    ax.set_title("Uso diário em valor (últimos 30 dias)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Data")
    ax.set_ylabel("Gasto (USD)")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: _usd(x)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    fig.autofmt_xdate(rotation=45, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def create_daily_tokens_chart(
    daily_tokens: dict[date, int],
    start: date,
    end: date,
    output_path: Path,
) -> Path:
    days: list[date] = []
    values: list[int] = []
    current = start
    while current <= end:
        days.append(current)
        values.append(daily_tokens.get(current, 0))
        current = current.fromordinal(current.toordinal() + 1)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(days, values, color="#7c3aed", width=0.8, edgecolor="white", linewidth=0.4)
    ax.set_title("Uso diário em tokens (últimos 30 dias)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Data")
    ax.set_ylabel("Tokens")
    ax.yaxis.set_major_formatter(FuncFormatter(_format_tokens))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    fig.autofmt_xdate(rotation=45, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


# Alias para compatibilidade com chamadas anteriores.
create_daily_usage_chart = create_daily_value_chart


def create_monthly_limit_chart(
    month_total: float,
    contracted_limit: float,
    output_path: Path,
) -> Path:
    usage_pct = min((month_total / contracted_limit) * 100, 150) if contracted_limit else 0
    remaining = max(contracted_limit - month_total, 0)

    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.barh(
        ["Mês corrente"],
        [month_total],
        color="#2563eb",
        height=0.45,
        label="Uso no mês",
    )
    ax.barh(
        ["Mês corrente"],
        [contracted_limit],
        color="#e5e7eb",
        height=0.45,
        alpha=0.8,
        label="Limite contratado",
        zorder=0,
    )
    bars[0].set_zorder(1)

    ax.axvline(contracted_limit, color="#dc2626", linestyle="--", linewidth=1.5, label="Limite")
    ax.set_xlim(0, max(contracted_limit * 1.15, month_total * 1.1, 1))
    ax.set_title(
        f"Total do mês: {_usd(month_total)} / Limite: {_usd(contracted_limit)} ({usage_pct:.1f}%)",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Valor (USD)")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: _usd(x)))
    ax.legend(loc="lower right")
    ax.text(
        month_total,
        0,
        f"  Restante: {_usd(remaining)}",
        va="center",
        fontsize=10,
        color="#374151",
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path
