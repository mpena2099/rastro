---
projeto: Rastro
subtítulo: Caçador de anãs frias / alto movimento próprio via CatWISE2020
versão: 0.1 — rascunho para revisão do Opus, antes da implementação
data: 2026-07-07
autor: Maurício, com apoio de pesquisa e redação do Claude (Sonnet 5)
status: NÃO IMPLEMENTADO — este é um documento de especificação
---

# Projeto Rastro — Especificação Técnica

## TL;DR (leia isto primeiro)

- **Objetivo:** construir um pipeline pessoal, em Python, que busca candidatos a anãs marrons/estrelas frias próximas ao Sol através de movimento próprio anômalo, usando o catálogo público **CatWISE2020**.
- **Achado importante desta pesquisa:** o CatWISE2020 **já contém movimento próprio calculado nativamente** por fonte (colunas `PMRA`/`PMDec`, ajuste de 12 épocas ao longo de 8 anos). Isso muda o desenho do pipeline: **não é necessário** fazer cross-match manual entre dois catálogos de época diferente para derivar PM — isso seria mais impreciso que usar o ajuste nativo do catálogo. Esse ponto corrige uma sugestão anterior (verbal, em conversa) que propunha cross-match manual entre CatWISE2020 e unWISE.
- **Novidade metodológica proposta aqui:** antes de procurar candidatos desconhecidos, o pipeline deve primeiro **redescobrir um objeto real e já conhecido** (WISE 0855-0714, a anã marrom mais fria conhecida, com movimento próprio de ~8,08 arcsec/ano) como teste de sanidade. Se o pipeline não conseguir "achar" esse objeto já catalogado, ele não deve ser usado para procurar objetos novos.
- **O que este documento NÃO é:** não é um roteiro de observação ao vivo, não envolve telescópio físico, não promete descoberta garantida. É mineração de dados de arquivo público.
- **Para quem vai implementar:** leia o documento inteiro antes de escrever código. Onde estiver marcado ⚠️ **CONFIRMAR ANTES DE USAR**, pare e valide contra a documentação oficial atual (as APIs de bibliotecas como `astroquery` mudam entre versões) antes de assumir que o valor sugerido aqui está correto.

---

## 1. Contexto e motivação

### 1.1 De onde veio a ideia

Maurício (desenvolvedor full-stack, experiência em Next.js/Supabase, automação residencial via Home Assistant, integração ESPHome/ESP32) tem um contato que é professor de astronomia e ficou curioso se seria possível, sozinho, usando dados públicos e LLMs como ferramenta de aceleração, encontrar um corpo celeste real.

### 1.2 Por que isso é realista (precedentes)

- **Frank Kiwy**, voluntário do projeto de ciência cidadã Backyard Worlds: Planet 9, descobriu **sozinho 34 novos sistemas binários de anãs ultrafrias** vasculhando dados públicos de imageamento infravermelho (WISE) à procura de objetos com movimento próprio característico não catalogado. Ele não é astrônomo profissional — é o precedente mais próximo do que este projeto tenta reproduzir em pequena escala.
- **WISE 0855-0714**, a anã marrom mais fria já catalogada, foi descoberta pelo astrônomo Kevin Luhman em 2013 exatamente pelo método que este projeto pretende automatizar: comparação de imagens WISE em múltiplas épocas, notando um movimento próprio anormalmente alto (~8 arcsec/ano) que destacava o objeto de fontes de fundo. Ou seja, o método não é uma invenção nossa — é o método real usado na descoberta mais notável dessa classe de objeto.
- O projeto de ciência cidadã **Active Asteroids** já usou um protótipo de assistente de IA para filtrar imagens de baixa probabilidade de mostrar atividade cometária, ajudando a identificar um objeto ativo inédito (2016 UU121) — um precedente direto de "IA faz triagem, humano confirma o resultado".

### 1.3 Definição honesta de sucesso

| Nível | Descrição | Deve ser prometido? |
|---|---|---|
| **Mínimo (esperado)** | Pipeline completo rodando ponta a ponta, reproduzindo a detecção de um objeto já conhecido (Fase 1 abaixo) | Sim — é o critério de aceite do projeto |
| **Bom** | Lista curta e defensável de candidatos não catalogados numa região real do céu, revisada e sem óbvios artefatos | Sim, com esforço razoável |
| **Moonshot (não prometido)** | Um candidato genuinamente novo, validado por segunda opinião e reportável | Não — é o horizonte, não a meta |

A maioria dos candidatos que sobrarem no fim do funil vai cair em "já catalogado", "artefato instrumental" ou "confusão de fonte". Isso é esperado e normal, inclusive em pipelines profissionais — o valor entregue nas fases iniciais é o pipeline funcionar corretamente, não o achado em si.

---

## 2. Escopo e não-escopo

**Está dentro do escopo:**
- Mineração de dados públicos já coletados (arquivo, não observação em tempo real)
- Um pipeline pessoal, rodado localmente, sem necessidade de infraestrutura cara
- Uso de LLM como camada de triagem/apoio ao julgamento, nunca como fonte de verdade

**Está fora do escopo (por ora):**
- Qualquer forma de observação ao vivo com telescópio físico
- Publicação formal ou reporte oficial de descoberta (isso viria depois, com o professor envolvido)
- Robustez de nível "produto" (retries elaborados, filas de processamento distribuído, etc.) — este é um projeto de fim de semana pessoal, não uma infraestrutura de produção
- Qualquer suposição sobre nome exato de tabela/coluna que não tenha sido confirmada contra a documentação oficial no momento da implementação

---

## 3. Fundamentação técnica: por que CatWISE2020 e não outra coisa

O CatWISE2020 é derivado de dados combinados WISE + NEOWISE coletados entre 2010 e 2018 (8 anos, 12 épocas), contendo **1.890.715.640 fontes**. O ponto chave para este projeto: o catálogo foi construído especificamente para ter movimento próprio mais preciso que seu predecessor — as medições de movimento no CatWISE2020 são precisas a um nível de ~20 mas/ano para fontes com W1~15 mag, e ~100 mas/ano para W1~17 mag, o que representa uma melhoria de 12 vezes sobre o AllWISE. Isso significa: **usar o campo de movimento próprio já calculado do CatWISE2020 é estritamente melhor** do que tentar derivar isso manualmente comparando duas catalogações de época diferente — o catálogo já fez o ajuste estatístico de 12 pontos ao longo de 8 anos, o que é muito mais robusto que uma diferença simples entre dois pontos.

### 3.1 Correção em relação à conversa anterior

Em conversa anterior, foi sugerido cross-match manual entre CatWISE2020 e unWISE (época anterior) para calcular PM. **Isso está superado por esta pesquisa**: o CatWISE2020 já entrega PM nativo e mais preciso. O pipeline abaixo reflete essa correção.

---

## 4. Arquitetura geral do pipeline

```
Fase 0: Setup e teste de conectividade
   │
Fase 1: Teste de sanidade — redescobrir WISE 0855-0714 (objeto conhecido)
   │        (se falhar aqui, PARAR e debugar antes de prosseguir)
   ▼
Fase 2: Query real ao CatWISE2020 numa região definida do céu,
        já filtrando por PM + qualidade via ADQL (server-side)
   ▼
Fase 3: Filtragem adicional de qualidade / remoção de artefatos conhecidos
   ▼
Fase 4: Cross-match contra SIMBAD/VizieR — descartar o que já é catalogado
   ▼
Fase 5: Triagem assistida por LLM (priorização, não veredito)
   ▼
Fase 6: Validação visual humana (blink de imagem)
   ▼
Fase 7: Segunda opinião (professor de astronomia)
```

---

## 5. Ambiente e dependências

```bash
python3 -m venv rastro-env
source rastro-env/bin/activate
pip install astropy astroquery pandas numpy matplotlib
```

`requirements.txt` sugerido:
```
astropy>=6.0
astroquery>=0.4.7
pandas>=2.0
numpy>=1.26
matplotlib>=3.8
```

⚠️ **CONFIRMAR ANTES DE USAR:** a API do `astroquery.ipac.irsa` muda entre versões (é um pacote de deploy contínuo — releases automáticos vão direto pro PyPI). Antes de escrever qualquer código de produção, rode `pip show astroquery` e confira cada assinatura de método (`query_region`, `query_tap`, `list_catalogs`) contra a documentação da versão instalada em https://astroquery.readthedocs.io/.

---

## 6. Estrutura de diretório sugerida

```
rastro/
├── requirements.txt
├── config.py                  # coordenadas do campo, limiares, paths
├── src/
│   ├── sanity_check.py        # Fase 1
│   ├── fetch_field.py         # Fase 2
│   ├── quality_filter.py      # Fase 3
│   ├── known_catalog_match.py # Fase 4
│   ├── llm_triage.py          # Fase 5
│   └── proper_motion.py       # função utilitária compartilhada
├── data/
│   ├── raw/                   # resultado bruto das queries (nunca reconsultar 2x)
│   └── candidates/            # tabelas intermediárias por fase
└── notebooks/
    └── inspecao_visual.ipynb  # Fase 6
```

---

## 7. Schema de dados (contrato entre fases)

Toda tabela intermediária deve manter, no mínimo, estas colunas (nomes exatos do CatWISE2020, confirmados na documentação oficial de colunas):

| Coluna | Tipo | Descrição |
|---|---|---|
| `source_id` | int | identificador único da fonte |
| `ra`, `dec` | double (deg) | posição J2000 |
| `w1mpro`, `w2mpro` | real (mag) | magnitude banda 1 e 2 |
| `w1snr`, `w2snr` | real | razão sinal-ruído por banda |
| `PMRA`, `PMDec` | real (arcsec/ano) | movimento próprio nativo do catálogo |
| `sigPMRA`, `sigPMDec` | real (arcsec/ano) | incerteza do movimento próprio |
| `par_pm`, `par_pmSig` | real (arcsec) | estimativa crua de paralaxe e incerteza |
| `pmcode` | char | formato ABCCC: A = nº de componentes no grupo de blend, B = Y/N se um secundário substituiu o primário, CCC = distância (0.01") entre as soluções com e sem movimento |
| `ka`, `km` | int | código de uso de astrometria/movimento (0-3; 3 = ambas as varreduras usadas) |
| `w1flg`, `w2flg` | int | flag de qualidade da abertura padrão (0 = nominal, sem contaminação) |
| `ab_flags` | char | bitmask de contaminação por artefato (unWISE) — ⚠️ ver §9.3 |
| `cc_flags` | char | flag de contaminação herdado do AllWISE — ⚠️ ver §9.3 |
| `n_aw` | int | número de fontes AllWISE dentro de 2.75″ (indicador de confusão) |
| `MeanObsMJD` | double | época média de observação |

Colunas derivadas que o pipeline deve calcular/adicionar:

| Coluna | Descrição |
|---|---|
| `pm_total` | `sqrt(PMRA² + PMDec²)`, em arcsec/ano |
| `cor_w1w2` | `w1mpro - w2mpro` |
| `status` | um de: `candidato`, `conhecido`, `artefato_suspeito`, `descartado` |
| `simbad_match_id` | preenchido na Fase 4, se houver correspondência |
| `llm_triage_score` | preenchido na Fase 5 |
| `llm_triage_notes` | texto livre da avaliação da LLM |
| `human_review_notes` | preenchido na Fase 6 |

---

## 8. Fase 0 — Setup e teste de conectividade

**Objetivo:** confirmar que o ambiente local consegue se conectar aos serviços externos (isso não pode ser testado no ambiente sandbox usado para escrever este documento, que não tem acesso de rede a domínios de arquivo astronômico — precisa ser validado na máquina real de quem for implementar).

```python
from astroquery.ipac.irsa import Irsa

# 1. Testar conectividade básica
print(Irsa.list_catalogs(filter="wise"))

# 2. Localizar o nome exato da tabela do CatWISE2020 -- NÃO assumir, confirmar aqui
print(Irsa.list_catalogs(filter="catwise"))
```

**Critério de aceite da Fase 0:** as duas chamadas acima retornam resultado sem erro, e o nome exato da tabela do CatWISE2020 foi identificado e anotado em `config.py`.

---

## 9. Fase 1 — Teste de sanidade: redescobrir um objeto conhecido

Esta é a fase mais importante deste documento do ponto de vista de engenharia. **Nenhuma busca por candidatos novos deve começar antes desta fase passar.**

### 9.1 Alvo de validação: WISE 0855-0714

| Propriedade | Valor | Fonte |
|---|---|---|
| Designação | WISE J085510.83-071442.5 | Luhman (2014) |
| RA (J2000) | 133.795125° | convertido via astropy nesta sessão a partir de 08h55m10.83s |
| Dec (J2000) | -7.245139° | convertido via astropy nesta sessão a partir de -07°14'42.5" |
| Latitude galáctica | b ≈ 23.35° | calculado via astropy nesta sessão |
| Movimento próprio total | ≈ 8,08 arcsec/ano (μα ≈ -8,05, μδ ≈ +0,66 a +0,70 arcsec/ano, conforme a referência) | Luhman (2014); Wright et al. (2014) |
| Distância | ≈ 2,2-2,3 pc (≈ 7,4 anos-luz) | literatura |
| Temperatura efetiva | ≈ 250-276 K (a anã marrom mais fria conhecida) | literatura |
| Magnitude W1 | ≈ 19,3-19,9 (**muito fraca**) | literatura |

⚠️ **Ponto de atenção real:** W0855 é extremamente fraco em W1 (~19,3-19,9 mag). A profundidade de completude a 90% do CatWISE2020 é W1=17,7 mag — ou seja, **este objeto está abaixo do limite de completude nominal do catálogo**, e pode não aparecer de forma confiável na consulta padrão, dependendo da profundidade de coadição na posição específica dele. Isso não invalida o teste, mas significa que o resultado esperado é: *"o objeto aparece com fotometria ruidosa/incerta, mas o movimento próprio ainda deve ser detectável e próximo do valor de referência"* — não espere magnitudes limpas.

**Plano B se W0855 não aparecer de forma utilizável:** usar **Luhman 16** (WISE 1049-5319), a binária de anãs marrons L7.5+T0.5, terceiro sistema mais próximo do Sol, também descoberta por Luhman via movimento próprio no WISE, e consideravelmente mais brilhante que W0855. Antes de usá-lo como alvo de validação, confirme magnitude e movimento próprio atualizados via `astroquery.simbad` (não foram verificados numericamente nesta sessão de pesquisa, então não devem ser tomados como dado fixo neste documento).

### 9.2 Código do teste de sanidade

```python
from astropy.coordinates import SkyCoord
from astroquery.ipac.irsa import Irsa
import astropy.units as u

alvo_conhecido = SkyCoord(ra=133.795125*u.deg, dec=-7.245139*u.deg, frame="icrs")

resultado = Irsa.query_region(
    alvo_conhecido,
    catalog="catwise_2020",  # ajustar conforme confirmado na Fase 0
    spatial="Cone",
    radius=10*u.arcsec,
    columns="source_id,ra,dec,w1mpro,w2mpro,w1snr,w2snr,PMRA,PMDec,sigPMRA,sigPMDec,par_pm,pmcode,ka,km"
)
print(resultado)
```

### 9.3 Critério de aceite da Fase 1

- [ ] A consulta retorna ao menos uma fonte dentro do raio de busca
- [ ] O `PMRA`/`PMDec` calculado (`pm_total = sqrt(PMRA² + PMDec²)`) está na faixa de **6 a 10 arcsec/ano** (margem generosa em torno do valor de referência de ~8,08, considerando o ruído esperado dado o objeto ser fraco)
- [ ] Se nenhuma fonte aparecer, ou o PM estiver muito fora dessa faixa: **parar, documentar o resultado real observado, e debugar antes de prosseguir** — não seguir para a Fase 2 com um pipeline não validado

---

## 10. Fase 2 — Query real numa região do céu

### 10.1 Campo escolhido

Critério: longe do plano galáctico, para reduzir confusão de fontes. Verificado via astropy nesta sessão:

```
RA = 150,0°, Dec = +20,0°  →  latitude galáctica b ≈ 50,26°
```

Este ponto está bem afastado do plano (confusão de campo começa a ser problema perto de |b| < 15-20°).

⚠️ **Ponto de atenção crítico de escala:** o CatWISE2020 tem quase 1,9 bilhão de fontes distribuídas em ~41.253 graus quadrados de céu. Mesmo em latitude galáctica alta, um campo de 5°×5° (25 graus quadrados) pode facilmente conter dezenas de milhares a centenas de milhares de fontes. **Baixar tudo sem filtro é impraticável e desnecessário.** A abordagem correta é filtrar por movimento próprio e qualidade **no servidor**, via `query_tap` com ADQL — não com `query_region`, que não suporta filtro por valor de coluna, apenas por posição.

### 10.2 Recomendação de tamanho de campo

Comece com um campo pequeno para o primeiro teste ponta a ponta (ex: **1°×1°**) antes de escalar para 5°×5° ou maior. Isso mantém os resultados administráveis enquanto o pipeline ainda está sendo debugado.

### 10.3 Query ADQL (server-side filtering)

```python
from astroquery.ipac.irsa import Irsa

query = """
SELECT source_id, ra, dec, w1mpro, w2mpro, w1snr, w2snr,
       PMRA, PMDec, sigPMRA, sigPMDec, par_pm, par_pmSig,
       pmcode, ka, km, w1flg, w2flg, ab_flags, cc_flags, n_aw,
       MeanObsMJD
FROM catwise_2020
WHERE ra BETWEEN 149.5 AND 150.5
  AND dec BETWEEN 19.5 AND 20.5
  AND ka = 3 AND km = 3
  AND SQRT(POWER(PMRA,2) + POWER(PMDec,2)) > 0.15
"""

resultado = Irsa.query_tap(query).to_table()
resultado.write("data/raw/campo1_filtrado.csv", format="csv", overwrite=True)
```

**Notas técnicas importantes:**
- `ra BETWEEN`/`dec BETWEEN` é uma caixa simples em coordenadas equatoriais — funciona bem longe dos polos e longe do wraparound RA=0°/360°. O campo escolhido (RA≈150°) está seguro nesse sentido. **Não reutilizar esta abordagem simplificada perto dos polos ou de RA=0h sem ajuste.**
- `ka = 3 AND km = 3` exige que **ambas** as varreduras (ascendente e descendente) tenham contribuído pra solução — o código de uso mais confiável disponível.
- O limiar de 0,15 arcsec/ano (150 mas/ano) é um ponto de partida, não uma verdade absoluta — espere iterar esse número depois de ver a distribuição real dos dados.
- ⚠️ **CONFIRMAR ANTES DE USAR:** funções `SQRT`/`POWER` são ADQL 2.0 padrão e devem funcionar na maioria dos serviços TAP, mas confirme com uma query pequena de teste antes de rodar em escala — nem todo serviço TAP implementa o mesmo subconjunto de ADQL.
- ⚠️ **CONFIRMAR ANTES DE USAR:** o nome exato da tabela (`catwise_2020` aqui é um palpite razoável, não confirmado) deve vir do resultado de `Irsa.list_catalogs(filter="catwise")` na Fase 0.
- O parâmetro `row_limit` do módulo tem default de **500 linhas** — isso pode truncar silenciosamente o resultado. Adicionar `TOP N` explícito na query ADQL (ex: `SELECT TOP 5000 ...`) e/ou ajustar a configuração do módulo antes de rodar em escala.

### 10.4 Critério de aceite da Fase 2

- [ ] Query executa sem erro e retorna um número de linhas administrável (dezenas a poucas centenas, não dezenas de milhares — se vier isso, o filtro de qualidade/PM precisa ser mais restritivo)
- [ ] Resultado salvo em `data/raw/`, nunca reconsultado do zero

---

## 11. Fase 3 — Filtragem adicional de qualidade e remoção de artefatos

### 11.1 Por que esta fase existe

O erro mais clássico em busca de movimento próprio por imagem é confundir **fantasma óptico/artefato de difração perto de estrela brilhante** com um objeto real em movimento. O CatWISE2020 já inclui flags pensados exatamente pra isso.

### 11.2 Flags conhecidas e verificadas

A flag de qualidade de abertura padrão (`w1flg`/`w2flg`) tem semântica confirmada na documentação oficial:

| Valor | Condição |
|---|---|
| 0 | nominal — sem contaminação |
| 1 | confusão de fonte — outra fonte cai dentro da abertura de medição |
| 2 | pixels ruins ou fatais na abertura |
| 4 | flag de bit não-zero disparada |
| 8 | corrupção — todos os pixels inutilizáveis |
| 16 | saturação |
| 32 | limite superior (95% de confiança) |

Filtro recomendado: `w1flg == 0 AND w2flg == 0` (nominal, sem contaminação conhecida).

⚠️ **CONFIRMAR ANTES DE USAR:** `ab_flags` (bitmask de artefato unWISE) e `cc_flags` (herdado do AllWISE) existem especificamente para sinalizar artefatos de difração e outras contaminações, mas a semântica exata de bits **não foi verificada nesta sessão de pesquisa** — consulte o `CatWISE2020README_IRSA.txt` (linkado na página de definições de colunas do IRSA) antes de implementar um filtro baseado nesses campos.

### 11.3 Código

```python
import pandas as pd

df = pd.read_csv("data/raw/campo1_filtrado.csv")

df["pm_total"] = (df["PMRA"]**2 + df["PMDec"]**2)**0.5
df["cor_w1w2"] = df["w1mpro"] - df["w2mpro"]

filtrado = df[
    (df["w1flg"] == 0) &
    (df["w2flg"] == 0) &
    (df["n_aw"] <= 1)  # evita campos com múltiplas fontes AllWISE próximas (confusão)
].copy()

filtrado.to_csv("data/candidates/fase3_filtrado.csv", index=False)
```

### 11.4 Critério de aceite da Fase 3

- [ ] Lista reduzida, cada linha com justificativa de por que passou no filtro
- [ ] Nenhuma fonte com flag de saturação ou corrupção restante

---

## 12. Fase 4 — Cross-match contra catálogos conhecidos

**Objetivo:** descartar tudo que já tem designação catalogada de alto movimento próprio ou é uma anã já conhecida.

```python
from astroquery.simbad import Simbad
from astropy.coordinates import SkyCoord
import astropy.units as u
import time

resultados_simbad = []
for _, candidato in filtrado.iterrows():
    coord = SkyCoord(ra=candidato["ra"]*u.deg, dec=candidato["dec"]*u.deg)
    r = Simbad.query_region(coord, radius=5*u.arcsec)
    resultados_simbad.append(r)
    time.sleep(1)  # não sobrecarregar o serviço — cortesia básica com serviço público gratuito
```

**Nota de engenharia:** para poucas dezenas de candidatos, uma consulta por vez com `time.sleep` é aceitável. Se o volume crescer (centenas+), vale investigar o serviço de cross-match em lote (`astroquery.xmatch`), que existe especificamente para não sobrecarregar o SIMBAD com muitas consultas individuais.

### 12.1 Critério de aceite da Fase 4

- [ ] Cada candidato tem um veredito explícito: `conhecido` (com ID SIMBAD) ou `sem correspondência catalogada`
- [ ] Apenas candidatos sem correspondência avançam para a Fase 5

---

## 13. Fase 5 — Triagem assistida por LLM

**Papel da LLM aqui: priorização, nunca veredito final.**

Template de prompt sugerido (preencher com os valores reais de cada candidato):

```
Objeto com:
- W1 = {w1mpro} mag, W2 = {w2mpro} mag, cor W1-W2 = {cor_w1w2}
- Movimento próprio total = {pm_total} arcsec/ano
- Paralaxe estimada (par_pm) = {par_pm} arcsec (se disponível)
- pmcode = {pmcode} (ABCCC: A = componentes no blend, B = troca de primário, CCC = deslocamento entre soluções)
- Sem correspondência em SIMBAD dentro de 5 arcsec

Isso é fotometricamente consistente com uma anã marrom/anã fria (tipo L, T ou Y)?
Ou os valores sugerem mais provavelmente um artefato instrumental ou uma
estrela de fundo comum mal medida? Responda com o raciocínio, não só a
conclusão. Se a evidência for insuficiente pra opinar, diga isso
explicitamente em vez de arriscar um palpite.
```

### 13.1 Critério de aceite da Fase 5

- [ ] Cada candidato remanescente tem uma nota de triagem e uma prioridade relativa
- [ ] Nenhuma conclusão da LLM é tratada como confirmação — é apenas ordenação de esforço humano

---

## 14. Fase 6 — Validação visual humana

- Inspecionar a imagem real de cada candidato final (blink entre épocas, se possível via as ferramentas de imagem do IRSA)
- Checar especificamente se o candidato está perto de uma estrela brilhante (risco de fantasma de difração)
- Só candidatos que sobrevivem à inspeção visual manual avançam

### 14.1 Critério de aceite da Fase 6

- [ ] Lista final pequena (idealmente poucas unidades), cada uma com nota de inspeção visual documentada

---

## 15. Fase 7 — Segunda opinião

Levar a lista final (já filtrada, já com triagem de LLM, já inspecionada visualmente) para o contato professor de astronomia do Maurício. Este é o ponto em que o papel dele deixa de ser hipotético e vira validação real de um resultado concreto.

---

## 16. Armadilhas conhecidas (consolidado)

| Armadilha | Onde mitigar |
|---|---|
| Fantasma de difração perto de estrela brilhante | Fase 3 (flags) + Fase 6 (inspeção visual) |
| Confusão de fonte em campo denso | Fase 3 (`n_aw`) |
| Limiar de PM mal calibrado (ruído ou lista vazia) | Fase 2 — esperar iterar |
| Truncamento silencioso por `row_limit` | Fase 2 — usar `TOP N` explícito |
| Nome de tabela/coluna incorreto assumido sem checar | Fase 0 — sempre confirmar via `list_catalogs`/documentação |
| Objeto de validação fraco demais pra aparecer limpo | Fase 1 — ter plano B (Luhman 16) |

---

## 17. Perguntas em aberto para a revisão do Opus

Estas são decisões que este documento **não** resolveu sozinho, e que se beneficiam de uma segunda opinião antes da implementação:

1. O limiar inicial de PM (0,15 arcsec/ano) é um chute educado — faz sentido validar contra a distribuição real de PM em uma amostra do CatWISE2020 antes de fixar esse número?
2. A estratégia de armazenamento entre sessões (CSV simples, como especificado aqui) é suficiente, ou um SQLite local traria benefício real dado o volume esperado (dezenas a centenas de linhas, não milhões)?
3. A semântica exata de `ab_flags`/`cc_flags` (não verificada nesta sessão) é importante o bastante para valer uma sessão de pesquisa dedicada antes da Fase 3, ou o filtro por `w1flg`/`w2flg` + inspeção visual manual (Fase 6) já é suficiente mitigação?
4. Vale a pena, antes de tudo, testar o pipeline no Plano B (Luhman 16) em paralelo ao WISE 0855-0714, dado que este último está abaixo da profundidade de completude nominal do catálogo?

---

## 18. Notas para a LLM implementadora

- Não assuma nomes exatos de tabela/coluna que estejam marcados ⚠️ neste documento sem confirmar contra a documentação oficial atual primeiro.
- Se a Fase 1 (teste de sanidade) falhar, **não prossiga** para as fases seguintes — documente o resultado real obtido e pare para debug.
- Se encontrar uma decisão de projeto que este documento não resolve e que afeta materialmente o resultado (não é só estilo de código), pare e pergunte ao Maurício em vez de assumir.
- Este documento foi escrito com pesquisa verificada (buscas na web e um cálculo local via astropy para coordenadas/latitude galáctica), mas **sem acesso de rede aos serviços reais do IRSA/SIMBAD/VizieR** no ambiente onde foi escrito — nenhuma das queries aqui foi executada de ponta a ponta contra o serviço real. Trate os exemplos de código como ponto de partida bem fundamentado, não como testado.

---

## 19. Referências e fontes usadas nesta especificação

- Documentação de colunas do CatWISE2020 (IRSA/Caltech) — nomes de coluna, flags de qualidade, precisão de movimento próprio
- Eisenhardt et al. (2020) e Marocco et al. (2020) — papers de definição do CatWISE2020
- Documentação do `astroquery.ipac.irsa` (astroquery.readthedocs.io) — API de `query_region`, `query_tap`, `list_catalogs`
- Luhman (2014) e Wright et al. (2014) — descoberta e refinamento de parâmetros de WISE 0855-0714
- Wikipedia (WISE 0855-0714) — dados de contexto (distância, temperatura, constelação)
- Publicações do Zooniverse — precedente de Frank Kiwy (Backyard Worlds) e do protótipo de IA do projeto Active Asteroids
- Cálculos de coordenadas (conversão sexagesimal → decimal, latitude galáctica) feitos localmente via `astropy` durante a redação deste documento, não extraídos de nenhuma fonte externa

---

*Fim do documento. Próximo passo sugerido: revisão pelo Opus, com atenção especial à seção 17 (perguntas em aberto) antes de liberar para implementação.*
