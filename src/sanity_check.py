import sys
import time
from astropy.coordinates import SkyCoord
from astroquery.ipac.irsa import Irsa
from astroquery.simbad import Simbad
import astropy.units as u

from config import CATWISE_TABLE, REDE_PRAZO_S, SANITY_TARGETS
from src.util import com_prazo
from src.proper_motion import add_pm_columns


def _retry(fn, servico: str, retries: int = 3, delay: float = 5.0):
    for attempt in range(retries):
        try:
            return com_prazo(fn, REDE_PRAZO_S)
        except Exception as e:
            if attempt < retries - 1:
                print(f"  {servico} retry {attempt+1}/{retries}: {e}")
                time.sleep(delay)
            else:
                raise
    return None


def simbad_query_retry(coord: SkyCoord, radius: u.Quantity):
    return _retry(lambda: Simbad.query_region(coord, radius=radius), "SIMBAD")


def resolve_via_simbad(ra: float, dec: float) -> dict | None:
    coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
    result = simbad_query_retry(coord, 120 * u.arcsec)
    if result is None:
        return None
    for row in result:
        main_id = str(row["main_id"])
        if "LUHMAN" in main_id.upper() or "WISEA" in main_id:
            return {"main_id": main_id, "ra": float(row["ra"]), "dec": float(row["dec"])}
    return None


def check_target(name: str, params: dict) -> dict:
    # SIMBAD so identifica o objeto. O cone fica nas coordenadas do config (epoca
    # CatWISE): a posicao do SIMBAD e J2000 e WISE 0855 anda ~125" ate 2015,
    # o que joga a fonte certa pra fora do cone de 120".
    simbad_info = resolve_via_simbad(params["ra"], params["dec"])

    coord = SkyCoord(ra=params["ra"] * u.deg, dec=params["dec"] * u.deg, frame="icrs")

    result = _retry(lambda: Irsa.query_region(
        coord,
        catalog=CATWISE_TABLE,
        spatial="Cone",
        radius=120 * u.arcsec,
        columns="source_id,ra,dec,w1mpro,w2mpro,w1snr,w2snr,"
        "pmra,pmdec,sigpmra,sigpmdec,par_pm,pmcode,ka,km",
    ), "IRSA")

    if result is None or len(result) == 0:
        return {"target": name, "found": False, "sources": 0}

    df = result.to_pandas()
    df = add_pm_columns(df)
    df = df.sort_values("pm_total", ascending=False)

    return {
        "target": name,
        "found": True,
        "simbad_id": simbad_info["main_id"] if simbad_info else None,
        "simbad_ra": simbad_info["ra"] if simbad_info else None,
        "simbad_dec": simbad_info["dec"] if simbad_info else None,
        "sources": len(df),
        "top_by_pm": df.head(5).to_dict("records"),
    }


def run():
    print("=" * 50)
    print("Fase 1 — Teste de sanidade")
    print("=" * 50)

    all_ok = True
    for i, (name, params) in enumerate(SANITY_TARGETS.items()):
        if i > 0:
            time.sleep(2)
        is_primary = name == "LUHMAN_16"
        print(f"\n--- {name} ---")
        try:
            result = check_target(name, params)
        except Exception as e:
            print(f"  ERRO: {e}")
            if is_primary:
                all_ok = False
            continue

        if not result["found"]:
            print(f"  Nenhuma fonte. Pulando.")
            if is_primary:
                all_ok = False
            continue

        if result["simbad_id"]:
            print(f"  SIMBAD: {result['simbad_id']} em ({result['simbad_ra']:.4f}, {result['simbad_dec']:.4f})")

        print(f"  Fontes: {result['sources']}")
        for src in result["top_by_pm"]:
            print(f"    PM={src['pm_total']:.4f}\"/yr  W1={src['w1mpro']:.2f}  "
                  f"W2={src['w2mpro']:.2f}  id={src['source_id']}")

        # Todo alvo com referencia e checado; so o primario (Luhman 16) aborta.
        # Os demais (ex: WISE 0855, so W2, fraco) viram aviso.
        if params.get("pm_total_ref") is not None:
            top_pm = result["top_by_pm"][0]["pm_total"]
            ref = params["pm_total_ref"]
            tol = params["pm_tolerance"]
            if abs(top_pm - ref) <= tol:
                print(f"  ✓ PM {top_pm:.4f} compativel c/ ref {ref} ±{tol}")
            elif is_primary:
                print(f"  ✗ PM {top_pm:.4f} fora de ref {ref} ±{tol}")
                all_ok = False
            else:
                print(f"  ! PM {top_pm:.4f} fora de ref {ref} ±{tol} (aviso, nao aborta)")

    print("\n" + "=" * 50)
    if all_ok:
        print("Fase 1: PASSOU")
    else:
        print("Fase 1: FALHOU")
        sys.exit(1)

    return all_ok


if __name__ == "__main__":
    run()
