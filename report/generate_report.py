#!/usr/bin/env python3
"""Gera e envia relatório semanal de uso do Cursor."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from report.charts import (
    aggregate_daily_spend,
    aggregate_daily_tokens,
    create_daily_tokens_chart,
    create_daily_value_chart,
    create_monthly_limit_chart,
    sum_spend,
    sum_tokens,
)
from report.cursor_client import (
    CursorAPIError,
    CursorClient,
    last_n_days_range,
    month_start,
)
from report.email_sender import EmailConfigError, send_report_email

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def resolve_contracted_limit(spend_data: dict) -> float:
    env_limit = os.environ.get("PLAN_INCLUDED_USAGE_DOLLARS", "").strip()
    if env_limit:
        return float(env_limit)

    members = spend_data.get("members", [])
    limits = [
        float(member.get("effectivePerUserLimitDollars", 0) or 0)
        for member in members
        if member.get("effectivePerUserLimitDollars")
    ]
    if limits:
        return max(limits)

    return float(os.environ.get("DEFAULT_PLAN_LIMIT_DOLLARS", "20"))


def build_html_summary(
    *,
    period_start: date,
    period_end: date,
    month_start_date: date,
    month_total: float,
    month_tokens: int,
    contracted_limit: float,
    total_members: int,
    daily_average: float,
) -> str:
    usage_pct = (month_total / contracted_limit * 100) if contracted_limit else 0
    remaining = max(contracted_limit - month_total, 0)
    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #111827; line-height: 1.5;">
        <h2>Relatório de uso do Cursor</h2>
        <p>Período analisado: <strong>{period_start.strftime('%d/%m/%Y')}</strong> a
           <strong>{period_end.strftime('%d/%m/%Y')}</strong></p>
        <ul>
          <li><strong>Total do mês ({month_start_date.strftime('%m/%Y')}):</strong> ${_usd(month_total)}</li>
          <li><strong>Tokens no mês:</strong> {_format_tokens(month_tokens)}</li>
          <li><strong>Limite contratado:</strong> ${_usd(contracted_limit)}</li>
          <li><strong>Utilização do limite:</strong> {usage_pct:.1f}%</li>
          <li><strong>Saldo restante:</strong> ${_usd(remaining)}</li>
          <li><strong>Média diária (30 dias):</strong> ${_usd(daily_average)}</li>
          <li><strong>Membros no time:</strong> {total_members}</li>
        </ul>
        <h3>Uso diário (valor)</h3>
        <p><img src="cid:chart0" alt="Uso diário em valor" style="max-width: 100%; height: auto;" /></p>
        <h3>Uso diário (tokens)</h3>
        <p><img src="cid:chart1" alt="Uso diário em tokens" style="max-width: 100%; height: auto;" /></p>
        <h3>Total do mês vs limite</h3>
        <p><img src="cid:chart2" alt="Total mensal" style="max-width: 100%; height: auto;" /></p>
        <p style="color: #6b7280; font-size: 12px;">Gerado automaticamente em {generated_at}.</p>
      </body>
    </html>
    """


def build_markdown_report(
    *,
    period_start: date,
    period_end: date,
    month_start_date: date,
    month_total: float,
    month_tokens: int,
    period_tokens: int,
    contracted_limit: float,
    total_members: int,
    daily_average: float,
    generated_at: datetime,
) -> str:
    usage_pct = (month_total / contracted_limit * 100) if contracted_limit else 0
    remaining = max(contracted_limit - month_total, 0)

    return f"""# Relatório de uso do Cursor

**Gerado em:** {generated_at.strftime('%d/%m/%Y %H:%M UTC')}

## Período

- **Análise:** {period_start.strftime('%d/%m/%Y')} a {period_end.strftime('%d/%m/%Y')} (últimos 30 dias)
- **Mês corrente:** {month_start_date.strftime('%m/%Y')}

## Resumo

| Métrica | Valor |
|---------|-------|
| Total do mês (USD) | ${_usd(month_total)} |
| Tokens no mês | {_format_tokens(month_tokens)} |
| Tokens no período (30 dias) | {_format_tokens(period_tokens)} |
| Limite contratado | ${_usd(contracted_limit)} |
| Utilização do limite | {usage_pct:.1f}% |
| Saldo restante | ${_usd(remaining)} |
| Média diária (30 dias) | ${_usd(daily_average)} |
| Membros no time | {total_members} |

## Gráficos

### Uso diário em valor

![Uso diário em valor](daily_value.png)

### Uso diário em tokens

![Uso diário em tokens](daily_tokens.png)

### Total do mês vs limite contratado

![Total do mês vs limite](monthly_limit.png)
"""


def write_repo_report(
    *,
    report_date: date,
    summary: dict,
    charts: dict[str, Path],
    markdown: str,
) -> Path:
    dated_dir = REPORTS_DIR / report_date.isoformat()
    latest_dir = REPORTS_DIR / "latest"

    for target in (dated_dir, latest_dir):
        target.mkdir(parents=True, exist_ok=True)
        for name, chart_path in charts.items():
            shutil.copy2(chart_path, target / name)
        (target / "report.md").write_text(markdown, encoding="utf-8")
        (target / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return latest_dir


def generate_report(send_email: bool = True) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    client = CursorClient()
    period_start, period_end = last_n_days_range(30)
    month_start_date = month_start()
    generated_at = datetime.now(timezone.utc)

    usage_events = client.fetch_usage_events(period_start, period_end)
    spend_data = client.fetch_team_spend()

    daily_spend = aggregate_daily_spend(usage_events)
    daily_tokens = aggregate_daily_tokens(usage_events)
    month_events = [
        event
        for event in usage_events
        if datetime.fromtimestamp(
            int(event["timestamp"]) / 1000, tz=timezone.utc
        ).date()
        >= month_start_date
    ]
    month_total = sum_spend(month_events)
    month_tokens = sum_tokens(month_events)
    period_tokens = sum_tokens(usage_events)
    contracted_limit = resolve_contracted_limit(spend_data)
    daily_average = sum(daily_spend.values()) / max(len(daily_spend), 1)

    value_chart = create_daily_value_chart(
        daily_spend,
        period_start,
        period_end,
        OUTPUT_DIR / "daily_value.png",
    )
    tokens_chart = create_daily_tokens_chart(
        daily_tokens,
        period_start,
        period_end,
        OUTPUT_DIR / "daily_tokens.png",
    )
    monthly_chart = create_monthly_limit_chart(
        month_total,
        contracted_limit,
        OUTPUT_DIR / "monthly_limit.png",
    )

    charts = {
        "daily_value.png": value_chart,
        "daily_tokens.png": tokens_chart,
        "monthly_limit.png": monthly_chart,
    }

    summary = {
        "generated_at": generated_at.isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "month_start": month_start_date.isoformat(),
        "month_total_usd": round(month_total, 2),
        "month_tokens": month_tokens,
        "period_tokens": period_tokens,
        "contracted_limit_usd": round(contracted_limit, 2),
        "daily_average_usd": round(daily_average, 2),
        "total_members": spend_data.get("totalMembers", 0),
        "charts": list(charts.keys()),
    }

    markdown = build_markdown_report(
        period_start=period_start,
        period_end=period_end,
        month_start_date=month_start_date,
        month_total=month_total,
        month_tokens=month_tokens,
        period_tokens=period_tokens,
        contracted_limit=contracted_limit,
        total_members=spend_data.get("totalMembers", 0),
        daily_average=daily_average,
        generated_at=generated_at,
    )
    repo_path = write_repo_report(
        report_date=generated_at.date(),
        summary=summary,
        charts=charts,
        markdown=markdown,
    )
    summary["repo_path"] = str(repo_path)

    if send_email and _email_configured():
        html = build_html_summary(
            period_start=period_start,
            period_end=period_end,
            month_start_date=month_start_date,
            month_total=month_total,
            month_tokens=month_tokens,
            contracted_limit=contracted_limit,
            total_members=spend_data.get("totalMembers", 0),
            daily_average=daily_average,
        )
        recipient = send_report_email(
            subject=(
                f"Relatório Cursor — ${_usd(month_total)} usados em "
                f"{month_start_date.strftime('%m/%Y')}"
            ),
            html_body=html,
            attachments=[value_chart, tokens_chart, monthly_chart],
        )
        summary["email_sent_to"] = recipient
    elif send_email:
        summary["email_sent_to"] = None
        summary["email_skipped"] = "SMTP_USER ou SMTP_PASSWORD não configurados"

    return summary


def _email_configured() -> bool:
    return bool(
        os.environ.get("SMTP_USER", "").strip()
        and os.environ.get("SMTP_PASSWORD", "").strip()
    )


def _usd(value: float) -> str:
    return f"{value:,.2f}"


def _format_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera relatório de uso do Cursor")
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Apenas gera os gráficos, sem enviar e-mail",
    )
    args = parser.parse_args()

    try:
        result = generate_report(send_email=not args.no_email)
    except (CursorAPIError, EmailConfigError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1

    print("Relatório gerado com sucesso:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
