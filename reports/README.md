# Relatórios de uso do Cursor

Esta pasta é atualizada automaticamente pela automação semanal.

- `latest/` — relatório mais recente (gráficos, `cursor_activity.csv`, `report.md` e `summary.json`)
- `YYYY-MM-DD/` — histórico por data de geração

Para gerar manualmente:

```bash
python3 -m report.generate_report --no-email
```
