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

## A segunda opinião

O relatório existe para levar os que sobraram a um astrônomo, que pode confirmar com outras observações (um espectro, por exemplo) e, se for novo de verdade, publicar. A opinião em si ainda está por fazer: o projeto entrega a lista e as imagens, não um veredito externo.
