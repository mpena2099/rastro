"""Antes e depois de mandar um confirmado para fora: conferencia, envio e resposta.

Logica pura (testada offline em tests/test_units.py), usada pela fila. O principio vem do
Vagalume: o usuario nao deve depender de ninguem para saber se pode enviar. Se os dados
decidem, o app decide; "confira voce" so fica na tela quando os dados nao bastam.
"""

import json
import sqlite3
from datetime import date

import numpy as np
import pandas as pd

from app import dados
from config import CATALOGOS_ANAS, CATALOGOS_ANAS_LOCAIS, SIMBAD_RADIUS_ARCSEC

URL_PROJETO = "https://github.com/mpena2099/rastro"
PROCEDENCIA = ("Found with the Rastro search pipeline (proper motion in CatWISE2020; "
               f"{URL_PROJETO}).")
NIVEIS = ("ok", "atencao", "bloqueia")
ICONES = {"ok": "✅", "atencao": "⚠️", "bloqueia": "❌"}
_DO_CHECKLIST = {"ok": "ok", "atencao": "atencao", "problema": "bloqueia"}
MJD_J2000 = 51544.5


def raio_mesmo_objeto(pm_total: float, meanobsmjd: float | None = None) -> float:
    """Ate que distancia uma fonte de catalogo pode ser o mesmo objeto, em arcsec.

    Cada catalogo usa a sua epoca, de J2000 ate hoje: o objeto pode ter andado o PM vezes os
    anos desde 2000 (dos dois lados da epoca do CatWISE), mais 2" de erro de posicao.
    """
    anos = 16.0 if meanobsmjd is None else max((float(meanobsmjd) - MJD_J2000) / 365.25, 11.0)
    return float(pm_total) * anos + 2.0


def pendencias(r: dict, vizier: pd.DataFrame | None, enviado: bool = False) -> list[dict]:
    """Itens da conferencia de um confirmado, cada um com nivel ok, atencao ou bloqueia."""
    def item(nivel, titulo, texto):
        return {"nivel": nivel, "titulo": titulo, "texto": texto}

    itens = []
    if r.get("decisao") != "confirmado":
        itens.append(item("bloqueia", "Revisão", "Ainda não está confirmado na revisão."))
    else:
        itens.append(item("ok", "Revisão", "Confirmado por você na revisão visual."))

    for c in dados.checklist(r):
        itens.append(item(_DO_CHECKLIST[c["estado"]], c["titulo"], c["explicacao"]))

    n_listas = len(CATALOGOS_ANAS) + len(CATALOGOS_ANAS_LOCAIS)
    if r.get("status", "candidato") == "candidato":
        itens.append(item("ok", "Já catalogado?",
                          f"Não está no SIMBAD a até {SIMBAD_RADIUS_ARCSEC}\" nem nas {n_listas} "
                          "listas de anãs da Fase 4 (inclui as 3.086 do Backyard Worlds em "
                          "Schneider+2026)."))
    else:
        itens.append(item("bloqueia", "Já catalogado?",
                          f"Já é conhecido: {r.get('simbad_match_id') or r.get('catalogo_match')}."))

    itens.append(_item_vizier(r, vizier))
    if enviado:
        itens.append(item("atencao", "Envio", "Já foi enviado: aguarde a resposta antes de reenviar."))
    return itens


def _item_vizier(r: dict, vizier: pd.DataFrame | None) -> dict:
    titulo = "Busca no VizieR"
    if vizier is None:
        return {"nivel": "atencao", "titulo": titulo,
                "texto": "Falta a busca no VizieR (botão abaixo): é onde aparece um catálogo novo "
                         "que ainda não entrou nas listas da Fase 4."}
    raio = raio_mesmo_objeto(r.get("pm_total") or 0.0, r.get("meanobsmjd"))
    anas = vizier[vizier["lista_anas"].astype(bool)]
    perto = anas[anas["dist_arcsec"] <= raio]
    if not perto.empty:
        a = perto.iloc[0]
        return {"nivel": "bloqueia", "titulo": titulo,
                "texto": f"Já aparece em {a.catalogo} ({str(a.descricao)[:70]}) a "
                         f"{a.dist_arcsec:.1f}\". Isso cabe no quanto o objeto andou desde 2000 "
                         f"(até {raio:.0f}\"), então é o mesmo objeto, já publicado."}
    gerais = len(vizier) - len(anas)
    texto = (f"Nenhuma lista de anãs ou de movimento próprio até {raio:.0f}\" (o quanto ele "
             "andou desde 2000).")
    if not anas.empty:
        a = anas.iloc[0]
        texto += (f" A mais próxima, {a.catalogo}, está a {a.dist_arcsec:.1f}\": longe demais "
                  "para ser o mesmo objeto.")
    if gerais:
        texto += (f" Aparece em {gerais} catálogo(s) gerais (posição e brilho, como AllWISE e "
                  "Gaia), o que é normal.")
    if vizier.attrs.get("parcial"):
        return {"nivel": "atencao", "titulo": titulo,
                "texto": texto + " A busca foi limitada (VizieR de Estrasburgo fora do ar): "
                                 "repita quando ele voltar."}
    return {"nivel": "ok", "titulo": titulo, "texto": texto}


def pode_enviar(itens: list[dict]) -> bool:
    return all(i["nivel"] == "ok" for i in itens)


def proximo_passo(itens: list[dict]) -> str:
    """O primeiro item que bloqueia, senao a primeira atencao; vazio se esta tudo ok."""
    for nivel in ("bloqueia", "atencao"):
        for i in itens:
            if i["nivel"] == nivel:
                return f"{i['titulo']}: {i['texto']}"
    return ""


# ---------------------------------------------------------------- resumo em ingles
def resumo_ingles(r: dict, vizier: pd.DataFrame | None) -> str:
    """Texto curto e factual para o contato, com os valores do CatWISE2020 e dos cruzamentos."""
    def num(chave):
        v = r.get(chave)
        try:
            return None if v is None or pd.isna(v) else float(v)
        except (TypeError, ValueError):
            return None

    ra, dec = num("ra"), num("dec")
    mjd = num("meanobsmjd")
    epoca = f", epoch {2000 + (mjd - MJD_J2000) / 365.25:.1f}" if mjd else ""
    linhas = [f"Brown dwarf candidate, CatWISE2020 source {r.get('source_id')}",
              f"Position (CatWISE2020{epoca}): RA {ra:.6f}, Dec {dec:+.6f} deg"]
    pmra, pmdec = num("pmra"), num("pmdec")
    spra, spdec = num("sigpmra"), num("sigpmdec")
    if pmra is not None and pmdec is not None:
        erro = (lambda s: f" +/- {s * 1000:.0f}" if s is not None else "")
        linhas.append(f"Proper motion: pmRA {pmra * 1000:.0f}{erro(spra)}, pmDec "
                      f"{pmdec * 1000:.0f}{erro(spdec)} mas/yr (total {num('pm_total') * 1000:.0f} "
                      f"mas/yr, {num('pm_signif'):.1f} sigma)")
    w1, w2 = num("w1mpro"), num("w2mpro")
    if w1 is not None and w2 is not None:
        linhas.append(f"Photometry: W1 = {w1:.2f}, W2 = {w2:.2f}, W1-W2 = {w1 - w2:.2f} mag")
    allwise = {"consistente": "the AllWISE (2010) source is where the proper motion predicts",
               "parado": "the AllWISE (2010) source is at the current position (no motion)",
               "ambiguo": "AllWISE (2010) is ambiguous (sources near both positions)"}
    linhas.append("Motion check: " + allwise.get(r.get("allwise_status"),
                                                 "no AllWISE (2010) test (too faint or no data)"))
    g = num("gaia_g")
    if r.get("gaia_detectada") is None or (isinstance(r.get("gaia_detectada"), float)
                                           and np.isnan(r.get("gaia_detectada"))):
        linhas.append("Gaia DR3: not checked")
    elif g is None:
        linhas.append('Gaia DR3: no counterpart within 3"')
    else:
        linhas.append(f'Gaia DR3: counterpart within 3", G = {g:.2f}')
    bandas = [f"{b} = {num('ps1_' + b):.2f}" for b in ("r", "z", "y") if num("ps1_" + b) is not None]
    if bandas:
        linhas.append("Pan-STARRS DR1: " + ", ".join(bandas))
    elif r.get("ps1_detectada") is not None:
        linhas.append('Pan-STARRS DR1: not detected within 2"')
    n_listas = len(CATALOGOS_ANAS) + len(CATALOGOS_ANAS_LOCAIS)
    linhas.append(f'Not in SIMBAD within {SIMBAD_RADIUS_ARCSEC}" nor in {n_listas} published '
                  "ultracool dwarf lists (including Schneider et al. 2026).")
    if vizier is not None:
        anas = vizier[vizier["lista_anas"].astype(bool)]
        alcance = "selected VizieR catalogues" if vizier.attrs.get("parcial") else "all of VizieR"
        linhas.append(f"VizieR search ({alcance}): "
                      + ("no dwarf or proper-motion list nearby" if anas.empty else
                         "; ".join(f'{a.catalogo} at {a.dist_arcsec:.1f}"' for a in anas.itertuples())))
    if ra is not None and dec is not None:
        linhas.append(f"WiseView: {dados.link_wiseview(ra, dec)}")
    linhas.append(PROCEDENCIA)
    return "\n".join(linhas)


# ---------------------------------------------------------------- banco: VizieR e envio
_SCHEMA_VIZIER = """
CREATE TABLE IF NOT EXISTS vizier_consulta (
    source_id TEXT PRIMARY KEY,
    consultado_em TEXT,
    parcial INTEGER,
    achados TEXT
)"""

_SCHEMA_ENVIO = """
CREATE TABLE IF NOT EXISTS envio (
    source_id TEXT PRIMARY KEY,
    destino TEXT,
    enviado_em TEXT,
    respondido_em TEXT,
    aceito INTEGER,
    resposta TEXT,
    identificador TEXT,
    checado_em TEXT
)"""


def salvar_vizier(conn: sqlite3.Connection, source_id: str, achados: pd.DataFrame) -> None:
    conn.execute(_SCHEMA_VIZIER)
    conn.execute("INSERT OR REPLACE INTO vizier_consulta VALUES (?, ?, ?, ?)",
                 (source_id, date.today().isoformat(), int(bool(achados.attrs.get("parcial"))),
                  achados.to_json(orient="records")))
    conn.commit()


def ler_vizier(conn: sqlite3.Connection, source_id: str) -> pd.DataFrame | None:
    conn.execute(_SCHEMA_VIZIER)
    linha = conn.execute("SELECT parcial, achados FROM vizier_consulta WHERE source_id = ?",
                         (source_id,)).fetchone()
    if linha is None:
        return None
    df = pd.DataFrame(json.loads(linha[1]), columns=["catalogo", "descricao", "dist_arcsec",
                                                     "lista_anas"])
    df["lista_anas"] = df["lista_anas"].astype(bool)
    df.attrs["parcial"] = bool(linha[0])
    return df


def ler_envios(conn: sqlite3.Connection) -> pd.DataFrame:
    conn.execute(_SCHEMA_ENVIO)
    return pd.read_sql("SELECT * FROM envio", conn)


def marcar_enviado(conn: sqlite3.Connection, source_id: str, destino: str,
                   enviado_em: str | None = None) -> None:
    conn.execute(_SCHEMA_ENVIO)
    conn.execute("INSERT OR REPLACE INTO envio (source_id, destino, enviado_em) VALUES (?, ?, ?)",
                 (source_id, destino.strip(), enviado_em or date.today().isoformat()))
    conn.commit()


def registrar_resposta(conn: sqlite3.Connection, source_id: str, aceito: bool, resposta: str = "",
                       identificador: str = "", respondido_em: str | None = None) -> None:
    conn.execute(_SCHEMA_ENVIO)
    conn.execute("UPDATE envio SET respondido_em = ?, aceito = ?, resposta = ?, identificador = ? "
                 "WHERE source_id = ?",
                 (respondido_em or date.today().isoformat(), int(aceito), resposta.strip(),
                  identificador.strip(), source_id))
    conn.commit()


def desfazer_envio(conn: sqlite3.Connection, source_id: str) -> None:
    conn.execute(_SCHEMA_ENVIO)
    conn.execute("DELETE FROM envio WHERE source_id = ?", (source_id,))
    conn.commit()


def marcar_checado(conn: sqlite3.Connection, source_id: str) -> None:
    conn.execute(_SCHEMA_ENVIO)
    conn.execute("UPDATE envio SET checado_em = ? WHERE source_id = ?",
                 (date.today().isoformat(), source_id))
    conn.commit()


def situacao_envio(decisao: str, envio: dict | None) -> str:
    """'a enviar', 'enviado', 'aceito', 'recusado' ou '' (nao confirmado e nunca enviado)."""
    if not envio or not envio.get("enviado_em"):
        return "a enviar" if decisao == "confirmado" else ""
    aceito = envio.get("aceito")
    if aceito is None or (isinstance(aceito, float) and np.isnan(aceito)):
        return "enviado"
    return "aceito" if int(aceito) else "recusado"


# ---------------------------------------------------------------- confirmacao publica
OTIPOS_ANA = dados.OTIPOS_ULTRAFRIAS


def ja_no_simbad(ra: float, dec: float, pm_total: float, meanobsmjd: float | None = None):
    """(nome, otype) do objeto do SIMBAD que pode ser o candidato, ou None.

    Para os enviados: se o objeto aparecer no SIMBAD perto da posicao, alguem o publicou.
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.simbad import Simbad

    from src.util import com_prazo
    raio = raio_mesmo_objeto(pm_total, meanobsmjd)
    s = Simbad()
    s.add_votable_fields("otype")
    t = com_prazo(lambda: s.query_region(SkyCoord(ra, dec, unit="deg"), radius=raio * u.arcsec), 60)
    if t is None or len(t) == 0:
        return None
    df = t.to_pandas()
    if "otype" not in df:
        return None
    # so objeto do tipo ana conta: uma estrela de fundo perto da posicao nao e o candidato
    anas = df[df["otype"].astype(str).str.strip().isin(OTIPOS_ANA)]
    if anas.empty:
        return None
    linha = anas.iloc[0]
    nome = "main_id" if "main_id" in anas else anas.columns[0]
    return str(linha[nome]).strip(), str(linha["otype"]).strip()
