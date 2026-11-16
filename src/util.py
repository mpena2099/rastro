"""Utilitarios de rede compartilhados pelo pipeline e pelo app."""

import threading


def com_prazo(fn, segundos: float):
    """fn() com prazo de relogio; TimeoutError se passar dele.

    Para chamadas de rede sem timeout confiavel (IRSA TAP, CDS XMatch, SIMBAD): uma
    conexao morta parava a fase ou a pagina sem aviso. Roda em thread daemon: a que
    travou fica para tras sem segurar o fim do processo.
    """
    saida = {}

    def alvo():
        try:
            saida["valor"] = fn()
        except BaseException as e:  # repassa qualquer erro para quem chamou
            saida["erro"] = e

    t = threading.Thread(target=alvo, daemon=True)
    t.start()
    t.join(segundos)
    if t.is_alive():
        raise TimeoutError(f"sem resposta em {segundos:.0f} s")
    if "erro" in saida:
        raise saida["erro"]
    return saida.get("valor")


# ---------------------------------------------------------------- CDS fora do ar
VIZIER_ESPELHO = None  # servidor do espelho quando o VizieR do CDS esta fora


def _responde(url: str, prazo_s: float = 15.0) -> bool:
    import httpx
    try:
        return httpx.get(url, timeout=prazo_s, follow_redirects=True).status_code == 200
    except httpx.HTTPError:
        return False


def usar_espelhos_cds():
    """Se o CDS de Estrasburgo nao entrega consultas, aponta SIMBAD e VizieR para espelhos.

    Mesmo esquema do Vagalume. O VizieR de Harvard nao tem o Gaia DR3 e devolve 0 linhas sem
    erro, o que esconderia contrapartes; so o espelho do IDIA (Africa do Sul) e usado, e antes
    se confere que ele devolve fontes do Gaia DR3 numa regiao conhecida.
    """
    from astroquery.simbad import conf as simbad_conf
    from astroquery.vizier import VizierClass, conf as vizier_conf

    if not _responde(f"https://{simbad_conf.server}/simbad/sim-id?Ident=Vega&output.format=ASCII"):
        simbad_conf.server = "simbad.harvard.edu"
        print("  SIMBAD do CDS fora do ar: usando o espelho de Harvard.")

    if _responde(f"https://{vizier_conf.server}/viz-bin/votable?-source=I/239/hip_main&-out.max=1"):
        return
    espelho = "vizier.idia.ac.za"
    try:
        from astropy import units as u
        from astropy.coordinates import SkyCoord
        r = com_prazo(lambda: VizierClass(columns=["Source"], row_limit=1, timeout=60,
                                          vizier_server=espelho).query_region(
            SkyCoord(300 * u.deg, 35 * u.deg), radius=3 * u.arcmin, catalog="I/355/gaiadr3"), 90)
        if not len(r) or not len(r[0]):
            raise ValueError("espelho sem Gaia DR3")
    except Exception as e:
        print(f"  VizieR do CDS fora do ar e o espelho {espelho} nao serve ({type(e).__name__}).")
        return
    # o astroquery le conf.server uma vez, no default do __init__
    global VIZIER_ESPELHO
    VIZIER_ESPELHO = espelho
    VizierClass.__init__.__kwdefaults__["vizier_server"] = espelho
    print(f"  VizieR do CDS fora do ar: usando o espelho {espelho}.")


def xmatch_no_ar(prazo_s: float = 8.0) -> bool:
    """False se o XMatch do CDS nao responde (qualquer resposta HTTP conta como no ar)."""
    import httpx
    from astroquery.xmatch import XMatch
    try:
        httpx.get(XMatch.URL, timeout=prazo_s)
        return True
    except httpx.HTTPError:
        return False


def vizier_no_ar(prazo_s: float = 8.0) -> bool:
    """VizieR em uso (o do CDS ou o espelho) responde."""
    from astroquery.vizier import conf
    return _responde(f"https://{VIZIER_ESPELHO or conf.server}/", prazo_s)


def vizier_por_posicoes(ra, dec, catalogo: str, raio_arcsec: float, colunas=(), lote: int = 200,
                        prazo_s: float = 180, todas_colunas: bool = False):
    """Fontes de um catalogo do VizieR perto de cada posicao, sem o XMatch (que nao tem espelho).

    Uma consulta por lote de posicoes. Devolve DataFrame com 'idx' (posicao na entrada),
    'dist_arcsec' e as colunas pedidas. todas_colunas pede "**": no espelho do IDIA, o
    Pan-STARRS (II/349/ps1) so devolve fontes assim; com colunas escolhidas vem vazio.
    """
    import numpy as np
    import pandas as pd
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astroquery.vizier import Vizier

    ra, dec = np.asarray(ra, dtype=float), np.asarray(dec, dtype=float)
    partes = []
    for i in range(0, len(ra), lote):
        alvo = SkyCoord(ra[i:i + lote] * u.deg, dec[i:i + lote] * u.deg)
        pedidas = ["**", "_q", "_r"] if todas_colunas else ["_q", "_r", *colunas]
        r = com_prazo(lambda: Vizier(columns=pedidas, row_limit=-1, timeout=120)
                      .query_region(alvo, radius=raio_arcsec * u.arcsec, catalog=catalogo), prazo_s)
        for t in r.values():
            d = t.to_pandas()
            d["idx"] = d["_q"].astype(int) - 1 + i
            # sem unidade, o _r vem na unidade do raio pedido (arcsec)
            d["dist_arcsec"] = (t["_r"].quantity.to(u.arcsec).value
                                if t["_r"].unit is not None else d["_r"].astype(float))
            partes.append(d[["idx", "dist_arcsec", *colunas]])
    if not partes:
        return pd.DataFrame({"idx": pd.Series(dtype=int), "dist_arcsec": pd.Series(dtype=float),
                             **{c: pd.Series(dtype=float) for c in colunas}})
    return pd.concat(partes, ignore_index=True)


usar_espelhos_cds()
