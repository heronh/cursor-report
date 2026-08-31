"""Envio do relatório por e-mail."""

from __future__ import annotations

import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


class EmailConfigError(RuntimeError):
    """Configuração de e-mail ausente ou inválida."""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EmailConfigError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


def send_report_email(
    *,
    subject: str,
    html_body: str,
    attachments: list[Path],
    to_email: str | None = None,
) -> str:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = _require_env("SMTP_USER")
    smtp_password = _require_env("SMTP_PASSWORD")
    recipient = to_email or os.environ.get("REPORT_EMAIL_TO", smtp_user)

    message = MIMEMultipart("related")
    message["Subject"] = subject
    message["From"] = smtp_user
    message["To"] = recipient

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(html_body, "html", "utf-8"))
    message.attach(alternative)

    for index, attachment in enumerate(attachments):
        with attachment.open("rb") as image_file:
            image = MIMEImage(image_file.read(), name=attachment.name)
        content_id = f"chart{index}"
        image.add_header("Content-ID", f"<{content_id}>")
        image.add_header("Content-Disposition", "inline", filename=attachment.name)
        message.attach(image)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [recipient], message.as_string())

    return recipient
