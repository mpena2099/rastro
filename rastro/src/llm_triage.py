import json
import sqlite3
import os
import pandas as pd
import httpx

from config import (
    SQLITE_PATH,
    OPENROUTER_API_KEY_PATH,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    LLM_BATCH_SIZE,
)


def load_openrouter_key() -> str:
    if not OPENROUTER_API_KEY_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo de auth nao encontrado: {OPENROUTER_API_KEY_PATH}"
        )
    with open(OPENROUTER_API_KEY_PATH) as f:
        data = json.load(f)
    key = data.get("openrouter", {}).get("key")
    if not key:
        raise ValueError("Chave OpenRouter nao encontrada no auth.json")
    return key


def build_prompt(row: dict) -> str:
    return f"""Objeto com:
- W1 = {row['w1mpro']} mag, W2 = {row['w2mpro']} mag, cor W1-W2 = {row['cor_w1w2']:.2f}
- Movimento proprio total = {row['pm_total']:.4f} arcsec/ano
- Paralaxe estimada (par_pm) = {row['par_pm']} arcsec
- Codigo de qualidade da solucao de movimento (pmcode) = {row['pmcode']}
- Sem correspondencia em SIMBAD dentro de 5 arcsec

Isso e fotometricamente consistente com uma ana marrom/ana fria (tipo T ou Y)?
Ou os valores sugerem mais provavelmente um artefato instrumental ou uma
estrela de fundo comum mal medida? Responda com o raciocinio, nao so a
conclusao. Se a evidencia for insuficiente pra opinar, diga isso
explicitamente em vez de arriscar um palpite."""


def call_openrouter(prompt: str, api_key: str) -> tuple[str, str]:
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]

    score = "media"
    lower = content.lower()
    if any(w in lower for w in ["ana marrom", "ana fria", "tipo t", "tipo y", "candidata"]):
        score = "alta"
    elif any(
        w in lower
        for w in ["artefato", "ruido", "mal medida", "fundo", "improva"]
    ):
        score = "baixa"
    elif "insuficiente" in lower or "nao e possivel" in lower:
        score = "incerta"

    return content, score


def run():
    print("=" * 50)
    print("Fase 5 — Triagem LLM (OpenRouter)")
    print("=" * 50)

    api_key = load_openrouter_key()
    print(f"Modelo: {LLM_MODEL}")
    print(f"API key: {api_key[:12]}...")

    conn = sqlite3.connect(str(SQLITE_PATH))
    df = pd.read_sql("SELECT * FROM candidatos_fase4 WHERE status = 'candidato'", conn)
    df = df.sort_values("pm_total", ascending=False).head(LLM_BATCH_SIZE)

    print(f"Candidatos a triar: {len(df)} (top {LLM_BATCH_SIZE} por PM)")

    df["llm_triage_score"] = None
    df["llm_triage_notes"] = None

    for i, row in df.iterrows():
        print(f"\n--- Candidato {i+1}/{len(df)} (source_id={row['source_id']}) ---")
        prompt = build_prompt(row.to_dict())
        try:
            notes, score = call_openrouter(prompt, api_key)
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
