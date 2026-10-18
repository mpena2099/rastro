"""Fase 7: relatorio dos candidatos revisados, pra mandar a um astronomo.

Manual, como a Fase 6: nao entra no pipeline.py. Le as decisoes humanas em
`revisao_humana`, refaz os cruzamentos (Gaia, Pan-STARRS, AllWISE) so pros
escolhidos e grava um HTML unico (imagens embutidas, abre offline) e um CSV.

    python src/relatorio.py                  # so os confirmados
    python src/relatorio.py --duvidas        # confirmados e duvidas
"""

import argparse
import base64
import html
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
import numpy as np
import pandas as pd

import config
from app import dados

CAMADAS = (
    ("unwise-neo2", "unWISE NEO2 (infravermelho)"),
    ("unwise-neo7", "unWISE NEO7 (infravermelho)"),
    ("ls-dr10", "Legacy Surveys DR10 (grz)"),
)
PASTA_SAIDA = ROOT / "data" / "relatorio"


def nome_iau(ra: float, dec: float) -> str:
    """Designacao no formato JHHMMSS.ss+DDMMSS.s (truncada, como nos catalogos)."""
    h = ra / 15.0
    hh, mm = int(h), int((h - int(h)) * 60)
    ss = ((h - hh) * 60 - mm) * 60
    sinal = "+" if dec >= 0 else "-"
    a = abs(dec)
    dd, dm = int(a), int((a - int(a)) * 60)
    ds = ((a - dd) * 60 - dm) * 60
    return (f"J{hh:02d}{mm:02d}{int(ss * 100) / 100:05.2f}"
            f"{sinal}{dd:02d}{dm:02d}{int(ds * 10) / 10:04.1f}")


def baixar_recorte(ra: float, dec: float, camada: str) -> bytes | None:
    try:
        r = httpx.get(dados.url_recorte(ra, dec, camada), timeout=60, follow_redirects=True)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"  recorte {camada} falhou: {e}")
        return None


def _fmt(v, casas: int = 2) -> str:
    return "-" if v is None or pd.isna(v) else f"{v:.{casas}f}"


def _sim_nao(v) -> str:
    return "sem dado" if pd.isna(v) else ("sim" if bool(v) else "nao")


def _bloco(x, imagens: dict) -> str:
    esc = html.escape
    figs = ""
    for camada, titulo in CAMADAS:
        img = imagens.get(camada)
        if img:
            src = "data:image/jpeg;base64," + base64.b64encode(img).decode()
            figs += f'<figure><img src="{src}" alt="{esc(titulo)}"><figcaption>{esc(titulo)}</figcaption></figure>'
        else:
            figs += f'<figure><p>(recorte indisponivel)</p><figcaption>{esc(titulo)}</figcaption></figure>'
    gaia, ps1 = _sim_nao(x.gaia_detectada), _sim_nao(x.ps1_detectada)
    nota = f"<p><b>Nota do revisor:</b> {esc(x.nota)}</p>" if isinstance(x.nota, str) and x.nota else ""
    return f"""
<section>
<h2>{esc(nome_iau(x.ra, x.dec))} <small>({esc(x.decisao)})</small></h2>
<p class="id">CatWISE2020 {esc(str(x.source_id))} &middot; RA {x.ra:.6f} &middot; Dec {x.dec:+.6f}</p>
<div class="figs">{figs}</div>
<table>
<tr><th>W1 / W2 (mag)</th><td>{_fmt(x.w1mpro)} / {_fmt(x.w2mpro)}</td>
    <th>W1-W2</th><td>{_fmt(x.cor_w1w2)}</td></tr>
<tr><th>Mov. proprio (&Prime;/ano)</th><td>{_fmt(x.pm_total, 3)} (RA {_fmt(x.pmra, 3)}, Dec {_fmt(x.pmdec, 3)})</td>
    <th>PM / &sigma;</th><td>{_fmt(x.pm_signif, 1)}</td></tr>
<tr><th>SNR W2</th><td>{_fmt(x.w2snr, 1)}</td>
    <th>Epoca (MJD)</th><td>{_fmt(x.meanobsmjd, 1)}</td></tr>
<tr><th>Teste AllWISE</th><td colspan="3">{esc(str(x.allwise_status))}
    (fonte a {_fmt(x.allwise_sep_prevista)}&Prime; da posicao prevista e a {_fmt(x.allwise_sep_atual)}&Prime; da atual;
    deslocamento esperado {_fmt(x.allwise_desloc_esperado)}&Prime;)</td></tr>
<tr><th>Gaia DR3 (3&Prime;)</th><td>{gaia}</td><th>Pan-STARRS (2&Prime;)</th><td>{ps1}</td></tr>
<tr><th>SIMBAD</th><td colspan="3">sem objeto conhecido a {config.SIMBAD_RADIUS_ARCSEC}&Prime;</td></tr>
</table>
{nota}
<p class="links"><a href="{esc(dados.link_wiseview(x.ra, x.dec))}">WiseView</a> &middot;
<a href="{esc(dados.link_legacy_viewer(x.ra, x.dec))}">Legacy Surveys</a></p>
</section>"""


def montar_html(linhas: pd.DataFrame, imagens_por_id: dict) -> str:
    corpo = "".join(_bloco(x, imagens_por_id.get(x.source_id, {})) for x in linhas.itertuples())
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rastro: candidatos a anas frias</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;line-height:1.45}}
section{{border-top:2px solid #888;margin-top:2rem;padding-top:1rem;break-inside:avoid}}
small{{font-weight:normal;color:#666}} .id{{color:#555;font-family:monospace}}
.figs{{display:flex;gap:.5rem;flex-wrap:wrap}} figure{{margin:0;flex:1 1 280px}}
figure img{{width:100%;image-rendering:pixelated}} figcaption{{font-size:.85rem;color:#555}}
table{{border-collapse:collapse;width:100%;margin-top:.5rem}}
th,td{{border:1px solid #ccc;padding:.25rem .5rem;text-align:left;font-size:.9rem}} th{{background:#f3f3f3}}
</style></head><body>
<h1>Rastro: candidatos a anas marrons e estrelas frias proximas</h1>
<p>Gerado em {date.today().isoformat()}. {len(linhas)} candidato(s) revisado(s) a olho.</p>
<h2>Como foram escolhidos</h2>
<p>Fonte: CatWISE2020 (IRSA/TAP), regiao RA {config.FIELD_RA_RANGE[0]:g}-{config.FIELD_RA_RANGE[1]:g},
Dec {config.FIELD_DEC_RANGE[0]:g}-{config.FIELD_DEC_RANGE[1]:g}. Cortes: mov. proprio &gt; {config.PM_THRESHOLD_ARCSEC}&Prime;/ano,
PM/&sigma; &ge; {config.PM_SIGNIF_MIN:g}, SNR W2 &ge; {config.W2SNR_MIN:g}, sem troca de primaria no pmcode,
sem flags de contaminacao, no maximo {config.N_AW_MAX} fonte(s) AllWISE no casamento. Sem objeto conhecido no SIMBAD.
Cada candidato foi conferido a olho nos recortes e submetido ao teste de movimento contra o AllWISE (epoca ~2010).</p>
<h2>O que o relatorio NAO afirma</h2>
<p>Sao candidatos, nao descobertas. Falta espectro ou fotometria adicional para confirmar a classe espectral.
O teste do AllWISE e raso: fonte fraca costuma cair em "sem fonte", que nao prova nada. Contraparte no Gaia ou Pan-STARRS nao exclui ana L.</p>
{corpo}
</body></html>"""


def selecionar(conn: sqlite3.Connection, incluir_duvidas: bool) -> pd.DataFrame:
    df = dados.carregar_candidatos(conn)
    aceitas = ["confirmado"] + (["duvida"] if incluir_duvidas else [])
    return df[df["decisao"].isin(aceitas)].sort_values(["decisao", "pm_signif"],
                                                      ascending=[True, False]).reset_index(drop=True)


def run(incluir_duvidas: bool = False) -> Path | None:
    with sqlite3.connect(str(config.SQLITE_PATH)) as conn:
        sel = selecionar(conn, incluir_duvidas)
    if sel.empty:
        print("Nenhum candidato confirmado. Revise a fila no app (streamlit run app/revisao.py).")
        return None
    print(f"{len(sel)} candidato(s) no relatorio.")

    entrada = sel[["source_id", "ra", "dec", "pmra", "pmdec", "meanobsmjd"]]
    for nome, fn in (("Gaia/Pan-STARRS", dados.cruzar_gaia_ps1), ("AllWISE", dados.cruzar_allwise)):
        try:
            sel = sel.merge(fn(entrada), on="source_id", how="left")
        except Exception as e:
            print(f"AVISO: sem cruzamento {nome}: {e}")
    for coluna in ("gaia_detectada", "ps1_detectada", "allwise_sep_prevista", "allwise_sep_atual",
                   "allwise_desloc_esperado"):
        if coluna not in sel:
            sel[coluna] = pd.NA
    if "allwise_status" not in sel:
        sel["allwise_status"] = "sem dados"
    sel["allwise_status"] = sel["allwise_status"].fillna("sem dados")

    imagens = {}
    for x in sel.itertuples():
        print(f"  recortes de {x.source_id}")
        imagens[x.source_id] = {c: baixar_recorte(x.ra, x.dec, c) for c, _ in CAMADAS}

    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    saida = PASTA_SAIDA / "relatorio.html"
    saida.write_text(montar_html(sel, imagens), encoding="utf-8")
    sel.assign(designacao=[nome_iau(r, d) for r, d in zip(sel["ra"], sel["dec"])]).drop(
        columns=["llm_triage_notes"], errors="ignore").to_csv(PASTA_SAIDA / "candidatos.csv", index=False)
    print(f"Relatorio: {saida}")
    return saida


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--duvidas", action="store_true", help="inclui os marcados como duvida")
    run(ap.parse_args().duvidas)
