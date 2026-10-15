# Assistente Lume

Abra o chat e escolha **assistente · Lume** no campo Modo. O botão **Comandos do Lume** mostra exemplos. Também é possível iniciar com:

```bash
.venv/bin/python -m backend.app.main
# Em outro terminal:
.venv/bin/python -m apps.desktop.main --assistant --show-chat
```

## Voz

Ative **Ouvir “Lume”** para conversar sem segurar o botão. O microfone só é ativado nessa sessão, nunca ao reiniciar. Diga o nome e o pedido na mesma frase. Dizer apenas “Lume” aceita um próximo pedido por até oito segundos; a detecção usa a transcrição local, então o tempo de processamento conta nesse intervalo. A grafia “Lumi”, que pode aparecer na transcrição, também é aceita.

O áudio é processado localmente por Whisper. Perguntas reconhecidas seguem para o modelo escolhido. A escuta pausa durante a resposta e a reprodução da voz; não há interrupção por voz enquanto a Lume fala. Use **Parar voz** ou **Cancelar** nesses casos. Diga **“Lume, pare de ouvir”** ou desmarque a opção para desligar o microfone e descartar a captura pendente.

**Áudio** permite escolher o microfone, a saída, a velocidade e a sensibilidade. O AudioRelay pode ser usado como entrada virtual. Caso o telefone não esteja transmitindo, escolha o microfone físico. A síntese continua usando `espeak-ng` em português; o texto falado evita código, links e rótulos de providers. O timbre não é uma voz neural.

## Escolher o modelo por voz ou texto

- **“Lume, mude para o Codex.”**
- **“Lume, quero modelo local DeepHat.”**
- **“Lume, use o DeepHat.”**

O seletor **Modelo** confirma a escolha e permite fazer a mesma troca com o mouse. A preferência fica salva. A conversa e a memória do projeto continuam disponíveis ao mudar de modelo. A mudança vale para as próximas perguntas; uma resposta em andamento mantém o modelo com que começou.

O desktop começa com **DeepHat · local** na ausência de preferência salva. Escolher DeepHat usa somente Ollama. Escolher Codex usa somente o Codex CLI autenticado e precisa de internet; a pergunta, o histórico e o contexto autorizado são enviados para essa conta. Falha do modelo escolhido gera um erro, sem trocar silenciosamente para outro. Clientes API antigos que omitem `provider` continuam usando `CODEPET_PROVIDER`.

No modo assistente, as skills automáticas de programação ficam fora do prompt para manter a conversa curta. Uma skill escolhida explicitamente continua funcionando. O DeepHat usa temperatura 0,2 e até 192 tokens por resposta nesse modo; o tutor local usa temperatura 0,2 e até 320 tokens, e o copiloto mantém o orçamento configurado. Exemplos de conversa orientam o tom e o reconhecimento de contexto ausente; não são respostas fixas nem retreinamento.

Em **Aprender → Exercício simples de programação**, a Lumi propõe uma tarefa curta de Python sem mostrar a solução. Digite uma resposta e envie; o chat abre um campo multilinha para colar o código e pede ao modelo um veredito e uma dica. Esse fluxo usa contexto curto da própria conversa, sem contexto do editor, memória de projeto ou skills genéricas. O Ollama mantém o modelo carregado por 15 minutos por padrão (`CODEPET_OLLAMA_KEEP_ALIVE_MINUTES` ajustável de 1 a 120), o que acelera as perguntas seguintes enquanto mantém o modelo na memória. O primeiro carregamento ainda pode demorar.

## Comandos disponíveis

| Pedido | Resultado |
|---|---|
| “Abra o navegador” | Pede ao navegador padrão para abrir a página inicial do Google |
| “Abra o terminal” | Inicia um terminal instalado no diretório do projeto |
| “Abra o VS Code” | Abre o projeto no VS Code ou VSCodium instalado |
| “Abra a pasta do projeto” | Abre o diretório autorizado no gerenciador de arquivos |
| “Abra o Discord” / “Abra o Spotify” | Abre qualquer aplicativo instalado pelo nome; busca no PATH e nos `.desktop` do XDG |
| “Iniciar foco de 25 minutos para estudar Python” | Inicia a sessão com a meta informada |
| “Pausar foco”, “retomar foco”, “concluir foco” | Atualiza a sessão pelo backend |
| “Como está meu foco?” | Consulta o contador e a meta |
| “Anote que preciso revisar os testes” | Guarda uma nota na memória do projeto |
| “Pesquise no projeto minha_funcao” | Busca esse texto nos arquivos autorizados e mostra caminhos e linhas |
| “Me distraí” | Pede ajuda para retomar a meta com uma ação pequena |
| “Que horas são?” | Responde o horário local |

Com voz, prefixe os pedidos com “Lume”. Digitando no modo assistente, o prefixo é opcional. Para aplicativos genéricos, diga o nome simples (ex.: “Lume, abra o OBS”); nomes com argumentos ou flags são rejeitados por segurança. A busca de arquivos é limitada a 200 arquivos candidatos e 30 ocorrências; não pesquisa todo o computador. Os comandos locais são reconhecidos diretamente no texto do usuário. Respostas dos modelos não disparam ações nem viram comandos de shell.

**Mais ações → Lembrete** permite escolher 15, 25 ou 50 minutos. Durante sessões ativas, a Lume faz um check-in curto no chat e, se a voz estiver ligada, em áudio. Check-ins não interrompem geração, transcrição ou fala e ficam suspensos no modo silencioso ou com observação pausada. Lembretes não são ativados automaticamente.

## Repetir a avaliação do DeepHat

```bash
.venv/bin/python scripts/evaluate_local_assistant.py --profile tuned --output /tmp/deephat-avaliacao.json
.venv/bin/python scripts/smoke_chat.py --mode assistant --provider ollama --prompt 'Me ajude a começar uma tarefa em cinco minutos.'
.venv/bin/python scripts/smoke_chat.py --mode assistant --provider codex --prompt 'Responda em uma frase: o que é uma variável?'
```

A avaliação usa seis perguntas sintéticas e registra respostas, primeiro token e tempo total. `--holdout` usa três perguntas diferentes. É uma amostra pequena para revisão humana, não uma garantia de qualidade. `baseline` usa os parâmetros gerais do Ollama com o prompt atual; o relatório histórico preserva o prompt anterior usado na comparação inicial.
