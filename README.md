# cursor-report

Automação para gerar e enviar por e-mail um relatório semanal de uso do Cursor.

## O que o relatório inclui

- Gráfico de **uso diário em valor** (últimos 30 dias)
- Gráfico de **uso diário em tokens** (últimos 30 dias)
- **Total do mês corrente** em USD comparado ao **limite contratado**
- Relatório versionado em `reports/` (pasta `latest/` e histórico por data)
- Envio automático por e-mail com os gráficos embutidos

## Pré-requisitos

1. **Chave da Cursor Admin API** com escopo `admin:*`  
   Gere em [Cursor Dashboard → API Keys](https://cursor.com/dashboard/api).

2. **Credenciais SMTP** para envio de e-mail (ex.: senha de app do Gmail).

3. Plano **Teams** ou **Enterprise** (a Admin API não está disponível em contas individuais).

## Secrets do ambiente

Configure estes secrets no ambiente do Cloud Agent:

| Secret | Obrigatório | Descrição |
|--------|-------------|-----------|
| `CURSOR_API_KEY` | Sim | Chave da Admin API do Cursor |
| `SMTP_USER` | Sim | E-mail remetente (ex.: `seu@gmail.com`) |
| `SMTP_PASSWORD` | Sim | Senha de app SMTP |
| `REPORT_EMAIL_TO` | Não | Destinatário (padrão: `SMTP_USER`) |
| `SMTP_HOST` | Não | Padrão: `smtp.gmail.com` |
| `SMTP_PORT` | Não | Padrão: `587` |
| `PLAN_INCLUDED_USAGE_DOLLARS` | Não | Limite mensal em USD (padrão: limite da API ou $20) |

## Execução manual

```bash
pip install -r requirements.txt
python -m report.generate_report
```

Para gerar apenas os gráficos, sem enviar e-mail:

```bash
python -m report.generate_report --no-email
```

Os gráficos são salvos em `output/` e publicados em `reports/latest/`.

## Automação

A automação roda toda segunda-feira às 10:00 UTC e executa o relatório automaticamente.
