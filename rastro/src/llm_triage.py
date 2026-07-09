import json
import re
import sqlite3
import os
import time
import pandas as pd
import httpx

from config import (
    SQLITE_PATH,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_API_KEY_ENV,
    LLM_API_KEY_FILE,
    LLM_API_KEY_FILE_PROVIDER,
    LLM_STRUCTURED,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    LLM_REQUEST_DELAY_S,
    LLM_BATCH_SIZE,
)

VEREDITOS = ("alta", "media", "baixa", "incerta")

# Schema do structured output (response_format json_schema).
TRIAGE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "triagem_candidato",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "veredito": {"type": "string", "enum": list(VEREDITOS)},
                "raciocinio": {"type": "string"},
            },
            "required": ["veredito", "raciocinio"],
        },
    },
}


def load_api_key() -> str:
    """Resolve a chave da API do provider LLM configurado.

    Ordem: env var (LLM_API_KEY_ENV) -> arquivo auth.json estilo opencode
    (data[LLM_API_KEY_FILE_PROVIDER]["key"]). Se LLM_API_KEY_ENV for None, o
    provider nao usa chave (ex: Ollama local) e retorna string vazia.
    """
    if LLM_API_KEY_ENV is None:
        return ""

    key = os.environ.get(LLM_API_KEY_ENV)
    if key:
        return key

    if LLM_API_KEY_FILE.exists():
        with open(LLM_API_KEY_FILE) as f:
            data = json.load(f)
        key = data.get(LLM_API_KEY_FILE_PROVIDER, {}).get("key")
        if key:
            return key

    raise ValueError(
        f"Chave da API nao encontrada. Defina a env var {LLM_API_KEY_ENV} ou "
        f"adicione o provider '{LLM_API_KEY_FILE_PROVIDER}' em {LLM_API_KEY_FILE}"
    )


def build_prompt(row: dict) -> str:
    return f"""Objeto com:
- W1 = {row['w1mpro']} mag, W2 = {row['w2mpro']} mag, cor W1-W2 = {row['cor_w1w2']:.2f}
- Movimento proprio total = {row['pm_total']:.4f} arcsec/ano
- Paralaxe estimada (par_pm) = {row['par_pm']} arcsec
- Codigo de qualidade da solucao de movimento (pmcode) = {row['pmcode']}
- Sem correspondencia em SIMBAD dentro de 5 arcsec

Isso e fotometricamente consistente com uma ana marrom/ana fria (tipo T ou Y)?
Ou os valores sugerem mais provavelmente um artefato instrumental ou uma
estrela de fundo comum mal medida?
""" + (_STRUCTURED_INSTRUCTION if LLM_STRUCTURED else _TEXT_INSTRUCTION)


_VEREDITO_LEGENDA = (
    "onde alta = bom candidato a ana marrom/fria, baixa = provavel artefato ou "
    "estrela de fundo mal medida, incerta = evidencia insuficiente, media = misto."
)

_STRUCTURED_INSTRUCTION = f"""
Classifique em 'veredito' (um de: alta, media, baixa, incerta), {_VEREDITO_LEGENDA}
Em 'raciocinio', explique de forma concisa (3 a 5 frases) o que levou ao veredito.
Se a evidencia for insuficiente, use 'incerta' e diga isso em vez de chutar."""

_TEXT_INSTRUCTION = f"""
Comece sua resposta com uma PRIMEIRA linha isolada exatamente no formato:
VEREDITO: <alta|media|baixa|incerta>
{_VEREDITO_LEGENDA}
Depois da primeira linha, explique o raciocinio que levou a esse veredito. Se
a evidencia for insuficiente pra opinar, use 'incerta' e diga isso
explicitamente em vez de arriscar um palpite."""


def call_llm(prompt: str, api_key: str, max_retries: int = 5) -> tuple[str, str]:
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
    }
    if LLM_STRUCTURED:
        payload["response_format"] = TRIAGE_SCHEMA

    url = LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for attempt in range(max_retries):
        resp = httpx.post(url, headers=headers, json=payload, timeout=60)

        if resp.status_code == 429:
            # Cota diaria estourada (free tier): retry nao adianta ate resetar.
            # Falha rapido em vez de gastar todos os retries a toa.
            if "PerDay" in resp.text:
                raise RuntimeError(
                    "cota diaria do free tier esgotada para o modelo "
                    f"{LLM_MODEL} (reseta a meia-noite PT). Troque de modelo/"
                    "provider em config.py ou ative billing."
                )
            # Limite por minuto (RPM): espera a janela reabrir e tenta de novo.
            if attempt < max_retries - 1:
                wait = _retry_wait_seconds(resp)
                print(f"  429 rate limit; aguardando {wait:.0f}s e retentando "
                      f"({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue

        # Modelo nao suporta response_format: remove e refaz no modo texto.
        if resp.status_code == 400 and "response_format" in payload:
            print("  modelo nao suporta structured output; caindo pro modo texto")
            payload.pop("response_format")
            continue

        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return interpret_response(content)

    resp.raise_for_status()  # esgotou retries: propaga o ultimo erro


def interpret_response(content) -> tuple[str, str]:
    """Extrai (notas, score) da resposta.

    Modo structured: content e um JSON {veredito, raciocinio} -> usa direto.
    Modo texto (ou JSON quebrado/None): cai no parse do VEREDITO/keyword.
    """
    if content:
        try:
            data = json.loads(content)
            veredito = str(data.get("veredito", "")).lower()
            if veredito in VEREDITOS:
                return data.get("raciocinio", content), veredito
        except (json.JSONDecodeError, TypeError):
            pass
    text = content or ""
    return text, parse_score(text)


def _retry_wait_seconds(resp) -> float:
    reset = resp.headers.get("X-RateLimit-Reset")
    if reset:
        try:
            wait = float(reset) / 1000.0 - time.time()
            if wait > 0:
                return min(wait + 1.0, 70.0)
        except ValueError:
            pass
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after) + 1.0, 70.0)
        except ValueError:
            pass
    # Gemini manda o atraso no corpo (RetryInfo.retryDelay, ex: "56s").
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', resp.text)
    if m:
        return min(float(m.group(1)) + 1.0, 70.0)
    return 10.0


def parse_score(content: str) -> str:
    """Deriva o score do candidato a partir da resposta do modelo.

    Regra: 'alta' so pode vir do VEREDITO estruturado explicito. O fallback
    por keyword (usado quando o modelo ignora o formato) so pode rebaixar
    (baixa/incerta) ou ficar neutro (media), nunca promover a 'alta'. Isso
    evita falso positivo quando 'ana marrom'/'tipo T' aparece dentro de um
    raciocinio negativo, e respeita 'LLM = priorizacao, nunca veredito'.
    """
    # \W* tolera markdown/pontuacao entre o rotulo e o valor: "**Veredito:** Baixa".
    m = re.search(r"veredito\W*(alta|media|baixa|incerta)", content, re.IGNORECASE)
    if m:
        return m.group(1).lower()

    lower = content.lower()
    if any(w in lower for w in ["artefato", "ruido", "mal medida", "fundo", "improva"]):
        return "baixa"
    if "insuficiente" in lower or "nao e possivel" in lower:
        return "incerta"
    return "media"


def run():
    print("=" * 50)
    print("Fase 5 — Triagem LLM")
    print("=" * 50)

    api_key = load_api_key()
    print(f"Provider: {LLM_BASE_URL}")
    print(f"Modelo: {LLM_MODEL}")
    print(f"API key: {(api_key[:12] + '...') if api_key else '(sem chave)'}")

    conn = sqlite3.connect(str(SQLITE_PATH))
    df = pd.read_sql("SELECT * FROM candidatos_fase4 WHERE status = 'candidato'", conn)
    df = df.sort_values("pm_total", ascending=False).head(LLM_BATCH_SIZE)

    print(f"Candidatos a triar: {len(df)} (top {LLM_BATCH_SIZE} por PM)")

    df["llm_triage_score"] = None
    df["llm_triage_notes"] = None

    for n, (i, row) in enumerate(df.iterrows()):
        if n > 0 and LLM_REQUEST_DELAY_S:
            time.sleep(LLM_REQUEST_DELAY_S)
        print(f"\n--- Candidato {n+1}/{len(df)} (source_id={row['source_id']}) ---")
        prompt = build_prompt(row.to_dict())
        try:
            notes, score = call_llm(prompt, api_key)
            df.at[i, "llm_triage_notes"] = notes
            df.at[i, "llm_triage_score"] = score
            print(f"  Score: {score}")
            print(f"  Nota: {notes[:200]}...")
        except Exception as e:
            print(f"  ERRO: {e}")
            df.at[i, "llm_triage_notes"] = f"ERRO: {e}"
            df.at[i, "llm_triage_score"] = "erro"

    df.to_sql("candidatos_fase5", conn, if_exists="replace", index=False)
    conn.close()
    print(f"\nSalvo em {SQLITE_PATH} (tabela: candidatos_fase5)")

    print("\nResumo:")
    print(df["llm_triage_score"].value_counts().to_string())
    return df


if __name__ == "__main__":
    run()
