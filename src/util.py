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
