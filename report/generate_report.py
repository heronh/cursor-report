#!/usr/bin/env python3
"""Gera e envia relatório semanal de uso do Cursor."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from report.charts import (
    aggregate_daily_spend,
    create_daily_usage_chart,
    create_monthly_limit_chart,
    sum_spend,
)
from report.cursor_client import (
    CursorAPIError,
    CursorClient,
    last_n_days_range,
    month_start,
)
from report.email_sender import EmailConfigError, send_report_email

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


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

    # Fallback para planos individuais Pro quando a API não expõe limite de time.
    return float(os.environ.get("DEFAULT_PLAN_LIMIT_DOLLARS", "20"))


def build_html_summary(
    *,
    period_start: date,
    period_end: date,
    month_start_date: date,
    month_total: float,
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
          <li><strong>Total do mês ({month_start_date.strftime('%m/%Y')}):</strong> ${month_total:,.2f}</li>
          <li><strong>Limite contratado:</strong> ${contracted_limit:,.2f}</li>
          <li><strong>Utilização do limite:</strong> {usage_pct:.1f}%</li>
          <li><strong>Saldo restante:</strong> ${remaining:,.2f}</li>
          <li><strong>Média diária (30 dias):</strong> ${daily_average:,.2f}</li>
          <li><strong>Membros no time:</strong> {total_members}</li>
        </ul>
        <h3>Uso diário</h3>
        <p><img src="cid:chart0" alt="Uso diário" style="max-width: 100%; height: auto;" /></p>
        <h3>Total do mês vs limite</h3>
        <p><img src="cid:chart1" alt="Total mensal" style="max-width: 100%; height: auto;" /></p>
        <p style="color: #6b7280; font-size: 12px;">Gerado automaticamente em {generated_at}.</p>
      </body>
    </html>
    """


def generate_report(send_email: bool = True) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    client = CursorClient()
    period_start, period_end = last_n_days_range(30)
    month_start_date = month_start()

    usage_events = client.fetch_usage_events(period_start, period_end)
    spend_data = client.fetch_team_spend()

    daily_spend = aggregate_daily_spend(usage_events)
    month_events = [
        event
        for event in usage_events
        if datetime.fromtimestamp(
            int(event["timestamp"]) / 1000, tz=timezone.utc
        ).date()
        >= month_start_date
    ]
    month_total = sum_spend(month_events)
    contracted_limit = resolve_contracted_limit(spend_data)
    daily_average = sum(daily_spend.values()) / max(len(daily_spend), 1)

    daily_chart = create_daily_usage_chart(
        daily_spend,
        period_start,
        period_end,
        OUTPUT_DIR / "daily_usage.png",
    )
    monthly_chart = create_monthly_limit_chart(
        month_total,
        contracted_limit,
        OUTPUT_DIR / "monthly_limit.png",
    )

    summary = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "month_total_usd": round(month_total, 2),
        "contracted_limit_usd": round(contracted_limit, 2),
        "daily_average_usd": round(daily_average, 2),
        "total_members": spend_data.get("totalMembers", 0),
        "charts": [str(daily_chart), str(monthly_chart)],
    }

    if send_email:
        html = build_html_summary(
            period_start=period_start,
            period_end=period_end,
            month_start_date=month_start_date,
            month_total=month_total,
            contracted_limit=contracted_limit,
            total_members=spend_data.get("totalMembers", 0),
            daily_average=daily_average,
        )
        recipient = send_report_email(
            subject=(
                f"Relatório Cursor — {_usd(month_total)} usados em "
                f"{month_start_date.strftime('%m/%Y')}"
            ),
            html_body=html,
            attachments=[daily_chart, monthly_chart],
        )
        summary["email_sent_to"] = recipient

    return summary


def _usd(value: float) -> str:
    return f"${value:,.2f}"


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
