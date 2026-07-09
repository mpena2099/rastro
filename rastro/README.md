# Rastro

Pipeline pessoal de mineração de dados astronômicos que busca candidatos a anãs marrons/estrelas frias próximas ao Sol através de movimento próprio anômalo no catálogo **CatWISE2020**.

## Pipeline

| Fase | O que faz | Status |
|------|-----------|--------|
| 1 | Teste de sanidade — redescobre Luhman 16 (PM ~2.67"/yr) via CatWISE2020 + SIMBAD | ✅ |
| 2 | Query ADQL TAP no CatWISE2020 com filtro server-side (PM > 0.15"/yr, ka=km=3) | ✅ |
| 3 | Filtragem de qualidade (flags w1flg/w2flg < 8, SNR >= 5/3, cc/ab flags limpos) | ✅ |
| 4 | Cross-match batch via CDS XMatch contra SIMBAD — descarta conhecidos | ✅ |
| 5 | Triagem LLM via OpenRouter (gpt-4o-mini) nos top N candidatos por PM | ✅ |
| 6 | Inspeção visual (notebook Jupyter com links IRSA Finder Chart) | 🟡 template |
| 7 | Segunda opinião com astrônomo | ⬜ |

## Como usar

```bash
cd rastro
source venv/bin/activate
pip install -r requirements.txt
export PYTHONUNBUFFERED=1
python pipeline.py
```

Para rodar uma fase específica:

```bash
python -c "from src.llm_triage import run; run()"
```

## Dados

Resultados intermediários e finais ficam em `data/rastro.db` (SQLite). Tabelas:

- `campo_bruto` — resultado da query TAP (Fase 2)
- `candidatos_fase3` — após filtro de qualidade
- `candidatos_fase4` — após cross-match SIMBAD
- `candidatos_fase5` — após triagem LLM (com `llm_triage_score` e `llm_triage_notes`)

## Configuração

Tudo em `config.py`: coordenadas do campo, limiares de PM/flags, modelo LLM, caminhos.

A chave da OpenRouter é lida automaticamente de `~/.local/share/opencode/auth.json`.

## Estrutura

```
rastro/
├── pipeline.py              # entrypoint
├── config.py                # configurações centralizadas
├── requirements.txt
├── src/
│   ├── sanity_check.py      # Fase 1
│   ├── fetch_field.py       # Fase 2
│   ├── quality_filter.py    # Fase 3
│   ├── known_catalog_match.py # Fase 4
│   ├── llm_triage.py        # Fase 5
│   └── proper_motion.py     # util
├── notebooks/
│   └── inspecao_visual.ipynb # Fase 6
└── data/
    └── rastro.db
```

## Projeto conceitual

Especificação completa em `../projeto-rastro-especificacao-tecnica.md`.
