# Relatório e segunda opinião

A Fase 7 é manual, como a Fase 6: depois da revisão visual, você gera um relatório dos candidatos confirmados e o envia a um astrônomo para uma segunda opinião.

## O relatório (Fase 7)

É uma página com recortes, números, resultado do AllWISE, a sua nota e links. Abre offline e dá pra anexar num e-mail. A página diz o que a lista não afirma: são candidatos, não descobertas.

No app, o botão "Gerar relatório" monta a página HTML com os confirmados (ou confirmados e dúvidas, se marcar a caixa) e o botão "Baixar relatório" entrega o arquivo. Leva alguns segundos por candidato, para baixar os recortes.

Sem o app, o mesmo relatório sai pelo terminal, junto com um `candidatos.csv`, em `data/relatorio/`:

```bash
python src/relatorio.py            # só os confirmados
python src/relatorio.py --duvidas  # confirmados e dúvidas
```

## Antes de pedir a opinião: já foi publicado?

O relatório da Fase 7 consulta o VizieR inteiro em volta de cada candidato e destaca os catálogos de anãs ou de movimento próprio, com a distância. A Fase 4 só cruza as listas conhecidas, e é assim que se acha um catálogo novo que ainda não entrou nelas. O mesmo botão "Já foi publicado?" está na barra lateral do app de revisão (veja [Revisão e treino](revisao.md#na-barra-lateral)).

## Enviar a um astrônomo: conferência e acompanhamento

Cada candidato confirmado ganha, na página de revisão, o painel "Enviar a um astrônomo". Ele responde sozinho se o candidato pode ir para fora, com o que já está no banco:

- **Pode enviar** só quando todos os itens estão ok: a sua confirmação, o checklist (movimento, AllWISE, Gaia, cor e Pan-STARRS), a ausência no SIMBAD e nas listas de anãs da Fase 4, e a busca no VizieR.
- **Ainda não envie** mostra o primeiro item que falta, com o motivo. Um item que bloqueia (por exemplo, o AllWISE mostra a fonte parada) desliga o botão de envio.
- **A busca no VizieR** decide pela distância: uma lista de anãs mais perto do que o objeto andou desde 2000 (movimento próprio vezes os anos, mais 2") é o mesmo objeto, já publicado; mais longe que isso, é outro objeto. O resultado fica gravado no banco. Com o VizieR de Estrasburgo fora do ar, a busca vai ao espelho, fica limitada às listas de anãs e a catálogos gerais, e o item pede para repetir depois.

O painel também traz um **resumo em inglês**, pronto para colar no e-mail ou no formulário: posição, movimento próprio com o erro, magnitudes e cor do WISE, o teste do AllWISE, Gaia, Pan-STARRS, as buscas feitas, o link do WiseView e uma linha de procedência ("Found with the Rastro search pipeline...").

Depois de enviar, escreva para quem ou onde foi e clique em "Marquei como enviado hoje". O filtro **Envio** da barra lateral separa os confirmados a enviar, os enviados, os aceitos e os recusados. Para cada enviado sem resposta, o app confere uma vez por dia se o objeto já aparece no SIMBAD como anã e avisa. Quando a resposta chegar, registre se foi aceito ou recusado, o que disseram e o identificador externo (o nome no catálogo, por exemplo).

O destino ainda está em aberto. Os projetos Backyard Worlds (Planet 9, Cool Neighbors e Binaries) estão hoje sem dados no Zooniverse, e não há confirmação de que o formulário deles aceite achados feitos fora do site. O caminho mais seguro é perguntar à equipe no fórum Talk do projeto, ou escrever direto a um autor de lista recente de anãs, como Karpov et al. (2025) ou Schneider et al. (2026).

## A segunda opinião

O relatório existe para levar os que sobraram a um astrônomo, que pode confirmar com outras observações (um espectro, por exemplo) e, se for novo de verdade, publicar. A opinião em si ainda está por fazer: o projeto entrega a lista e as imagens, não um veredito externo.
