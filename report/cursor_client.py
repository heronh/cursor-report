"""Cliente para a Cursor Admin API."""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import requests

API_BASE = "https://api.cursor.com"


class CursorAPIError(RuntimeError):
    """Erro ao consultar a API do Cursor."""


class CursorClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("CURSOR_API_KEY", "")
        if not self.api_key:
            raise CursorAPIError(
                "CURSOR_API_KEY não configurada. Gere uma chave em "
                "https://cursor.com/dashboard/api com escopo admin."
            )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{API_BASE}{path}",
            json=payload,
            auth=(self.api_key, ""),
            timeout=60,
        )
        if response.status_code >= 400:
            raise CursorAPIError(
                f"Falha na API {path} ({response.status_code}): {response.text}"
            )
        return response.json()

    def fetch_usage_events(
        self,
        start: date,
        end: date,
        page_size: int = 1000,
    ) -> list[dict[str, Any]]:
        start_ms = _date_to_ms(start)
        end_ms = _end_of_day_ms(end)
        events: list[dict[str, Any]] = []
        page = 1

        while True:
            payload = {
                "startDate": start_ms,
                "endDate": end_ms,
                "page": page,
                "pageSize": page_size,
            }
            data = self._post("/teams/filtered-usage-events", payload)
            events.extend(data.get("usageEvents", []))
            pagination = data.get("pagination", {})
            if not pagination.get("hasNextPage"):
                break
            page += 1

        return events

    def fetch_team_spend(self, page_size: int = 100) -> dict[str, Any]:
        members: list[dict[str, Any]] = []
        page = 1
        subscription_cycle_start: int | None = None
        total_members = 0
        total_pages = 1

        while True:
            data = self._post(
                "/teams/spend",
                {"page": page, "pageSize": page_size, "sortBy": "amount", "sortDirection": "desc"},
            )
            members.extend(data.get("teamMemberSpend", []))
            subscription_cycle_start = data.get("subscriptionCycleStart", subscription_cycle_start)
            total_members = data.get("totalMembers", total_members)
            total_pages = data.get("totalPages", total_pages)
            if page >= total_pages:
                break
            page += 1

        return {
            "members": members,
            "subscriptionCycleStart": subscription_cycle_start,
            "totalMembers": total_members,
        }


def _date_to_ms(value: date) -> int:
    dt = datetime.combine(value, time.min, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _end_of_day_ms(value: date) -> int:
    dt = datetime.combine(value, time(23, 59, 59, 999000), tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def last_n_days_range(days: int = 30) -> tuple[date, date]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days - 1)
    return start, end


def month_start(today: date | None = None) -> date:
    current = today or datetime.now(timezone.utc).date()
    return current.replace(day=1)
