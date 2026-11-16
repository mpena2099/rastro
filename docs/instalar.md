# Instalar sem terminal

Para usar o Rastro no Windows ou no macOS sem digitar comandos. Tudo depois da instalação acontece no navegador: buscar candidatos, revisar, treinar e gerar o relatório.

O app nunca foi usado de verdade no Windows nem no macOS, embora os testes automáticos rodem nos dois a cada mudança. Se algo der errado, abra uma [issue](https://github.com/mpena2099/rastro/issues) com a mensagem que apareceu na janela.

## 1. Instale o Python

Baixe o Python 3.10 ou mais novo em [python.org/downloads](https://www.python.org/downloads/) e instale.

- **Windows:** na primeira tela do instalador, marque **"Add python.exe to PATH"** antes de clicar em **Install Now**. Sem isso, o iniciador não acha o Python.
- **macOS:** abra o arquivo `.pkg` baixado e siga as telas.

## 2. Baixe o Rastro

Na [página do projeto no GitHub](https://github.com/mpena2099/rastro), clique em **Code** e depois em **Download ZIP**. Descompacte o ZIP numa pasta sua, por exemplo `Documentos/rastro`. Evite deixar dentro de Downloads, que costuma ser limpa, e em pasta sincronizada com nuvem (OneDrive, iCloud), que atrapalha o banco de dados.

## 3. Abra com dois cliques

Dentro da pasta:

- **Windows:** clique duas vezes em `iniciar_rastro.bat`. Se aparecer o aviso azul "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**.
- **macOS:** clique com o botão direito em `iniciar_rastro.command` e escolha **Abrir** (na primeira vez, o clique duplo é bloqueado porque o arquivo veio da internet). Confirme em **Abrir** no aviso. Se o macOS disser que não tem permissão, abra o Terminal uma única vez e rode `chmod +x ` seguido do arquivo arrastado para a janela.

Na primeira vez, uma janela preta mostra a instalação das bibliotecas, que leva alguns minutos e precisa de internet. Depois o navegador abre sozinho no app. Das próximas vezes ele abre direto.

**Deixe essa janela aberta enquanto usa o app.** Fechar a janela fecha o app. Uma busca de candidatos já iniciada continua rodando mesmo assim.

## 4. Primeiro uso

1. Na página **Revisão**, clique em **Buscar mais candidatas** (duas vezes, para confirmar). A busca escolhe sozinha uma região do céu, baixa o CatWISE2020, filtra e descarta os objetos já conhecidos. Leva de minutos a algumas horas, conforme a região.
2. Enquanto isso, use a página **Treino**. Antes da primeira busca, ela usa os mesmos casos da [demo online](https://rastro-treino.streamlit.app).
3. Quando a busca terminar, os candidatos aparecem na **Revisão**.

A triagem por LLM (Fase 5) é opcional. Sem a chave da API configurada, a busca pula essa fase e os candidatos entram na fila como "sem triagem". A revisão visual funciona igual.

## Atualizar

Baixe o ZIP de novo e descompacte por cima da pasta antiga. A pasta `data/`, com as suas revisões, e a pasta `venv/` são mantidas. Se a nova versão pedir bibliotecas novas, apague o arquivo `venv/.instalado` antes de abrir: o iniciador reinstala.

## Se der errado

| O que aparece | O que fazer |
|---|---|
| "Python não encontrado" | Instale o Python (passo 1). No Windows, reinstale marcando "Add python.exe to PATH" |
| A instalação para com erro | Confira a internet e abra o iniciador de novo: ele retoma |
| O navegador não abre | Abra à mão o endereço que a janela mostra (`http://localhost:8501`) |
| A janela fecha sozinha logo ao abrir | Rode o iniciador pelo Terminal (ou Prompt de Comando) para ver a mensagem e mande-a numa [issue](https://github.com/mpena2099/rastro/issues) |
