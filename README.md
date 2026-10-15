# CodePet AI · Lume

Assistente local de programação com backend FastAPI, integração Ollama, pet desktop PySide6 e ponte para VS Code. **Entrega incremental 0.1:** o chat com DeepHat, o pet no Hyprland e o servidor MCP stdio foram executados no host; as dez fases do produto ainda não estão concluídas.

Lume usa uma silhueta coral de quatro pernas e olhos expressivos, com chapéu de mago azul. O asset vetorial e as animações são originais e substituíveis. O pet abre o chat do CodePet Tutor; o backend mantém a inferência fora da interface.

## Iniciar

Execute a partir da raiz deste repositório, em um terminal da sua sessão gráfica:

```bash
bash scripts/install.sh
```

O instalador usa a virtualenv local, respeita o `uv.lock`, preserva `.env` existente, instala dependências e aplica as migrações. A instalação inicial exige acesso ao índice de pacotes. O uso posterior sem internet exige `CODEPET_PROVIDER=ollama`.

```bash
# Terminal 1 — manter aberto
.venv/bin/python -m backend.app.main

# Terminal 2 — pet (duplo clique abre o chat)
.venv/bin/python -m apps.desktop.main
```

O backend escuta exclusivamente em `127.0.0.1:8765`. No modo Ollama, o servidor deve estar acessível em `127.0.0.1:11434`; não iniciamos outra instância nem baixamos modelos. No modo Codex CLI, instale `codex`, autentique com `codex login` e configure `CODEPET_PROVIDER=codex` no `.env`. Para usar os dois providers, configure `CODEPET_PROVIDER=hybrid`: o DeepHat responde primeiro e o Codex CLI acrescenta uma segunda opinião quando estiver autenticado.

`GET /health` confirma que o processo está vivo; `GET /ready` valida também o provider configurado e retorna HTTP 503 quando ele não está pronto.

```bash
.venv/bin/python scripts/doctor.py
ollama list
```

O modelo é descoberto por `/api/tags`: exatamente um nome contendo `DeepHat`, desconsiderando hífens e sublinhados. Se houver zero ou vários candidatos, configure **o nome exato instalado** em `CODEPET_MODEL` no `.env`. Neste host, `ollama list` retornou `hf.co/mradermacher/DeepHat-V1-7B-GGUF:Q5_K_M`; outro host pode ter um nome diferente.

`CODEPET_PROJECTS` é um mapa JSON de ID para diretório absoluto autorizado. O bootstrap configura `default` para este repositório. Para outro projeto, altere explicitamente o mapa. Reinicie o backend e o desktop após editar `.env`.

Consulte o [guia Arch/Wayland](docs/installation-arch.md) para requisitos gráficos, solução de problemas e instalação da extensão.

## Assistente por voz

O modo **assistente · Lume** oferece ativação por **“Lume”**, comandos para aplicativos, foco, notas e pesquisa no projeto. Ative **Ouvir “Lume”** no chat. **“Lume, mude para o Codex”** e **“Lume, quero modelo local DeepHat”** trocam o modelo das próximas perguntas, com a escolha visível e salva no seletor **Modelo**. O desktop usa DeepHat local por padrão; a escolha explícita não faz fallback para outro modelo. Veja [comandos, áudio e avaliação](docs/assistente-lume.md).

## Implementado

- API local autenticada, validação de origem/Host, limites de corpo, conexões e requisições.
- Descoberta Ollama, resposta por WebSocket, fila com uma inferência por vez, cancelamento e timeout.
- Tutor, copiloto, assistente e silencioso; prompts distinguem hipóteses de evidências.
- Skills locais (`SKILL.md`): Ponytail, Caveman e leitura de relatório Graphify ativos por padrão fora do modo assistente; explicar código, investigar erro e arquivos próprios em `~/.config/codepet-ai/skills/` também podem ser escolhidos. Veja o [guia de skills](docs/skills.md).
- Memória SQLite/SQLAlchemy com Alembic: conversas, preferências, tópicos, dificuldades, busca ranqueada, exercícios persistentes e revisão espaçada por projeto; consulta, edição, exclusão, exportação e retenção desativável.
- Ferramentas de leitura, busca limitada com ripgrep, status/diff Git, observação explícita de terminal, captura de tela opt-in, proposta inerte de patch e execução de pytest mediante aprovação específica, expirá­vel e de uso único.
- Eventos do editor, pausa que descarta contexto/cancela inferência e motor proativo opt-in com debounce, cooldown e deduplicação.
- Desktop: sprite SVG original com chapéu e animação em 120 ms: caminhada curta alternada com pausas suficientes para mostrar respiração, olhares, piscada, alongamento e bocejo; ao dormir, o corpo se achata. O corpo foi compactado, as pernas encurtadas e os braços pequenos são animados separadamente no repouso, caminhada, aceno e sono sem deformar o tronco. Uma pequena centelha percorre as mãos durante o repouso. O pet dá oi, puxa um notebook para a lateral, vira de perfil e digita com a tela voltada para ele, ou brinca de magia com um cajado ocasionalmente; depois retorna à pose normal. Essas animações aguardam quando ele está ocupado e ficam desativadas no modo silencioso. O tamanho padrão é escala 3,5 e continua ajustável no menu. Há balão, menu, arraste pelo compositor, pausa, velocidade, chat translúcido com texto claro, streaming e aprovação de testes. No Hyprland, a janela flutuante fica fixada nos workspaces do mesmo monitor. A máscara de entrada acompanha a silhueta e a pintura limpa cada quadro para evitar rastros no Wayland.
- Modo anti-procrastinação: meta pequena, sessões de 15/25/50 minutos, pausa de cinco minutos, pausa/retomada/conclusão e contador no desktop; o tutor muda para respostas curtas focadas no próximo passo. Veja o [guia do modo](docs/anti-procrastinacao.md).
- Extensão TypeScript compilada: seleção, linguagem e diagnósticos, token em SecretStorage, consentimento explícito e contexto automático desligado por padrão.
- Adaptador de servidor MCP stdio usando o SDK oficial v1; handshake, lista das onze ferramentas e uma leitura real foram validados no host.

## Limitações atuais

- PySide6 e MCP foram instalados e exercitados. No Hyprland 0.56.2 deste host, o pet flutua próximo ao canto inferior, anda dentro de uma janela de 360×190 px e a transparência foi verificada por captura real. O posicionamento usa a API de despacho do Hyprland; outros compositores precisam de adaptação.
- O DeepHat respondeu por streaming ao backend e ao cliente Qt neste host. A qualidade das respostas, o consumo total de RAM/VRAM e a operação em todos os estados do compositor ainda exigem avaliação.
- Captura de tela é opcional via `grim` (`CODEPET_SCREEN_CAPTURE=true`) e o terminal só é recebido por observação explícita do cliente. Visão multimodal e embeddings reais continuam fora do núcleo; o provider direto da OpenAI API também não faz parte deste projeto.
- O chat oferece voz local em português brasileiro via `espeak-ng`. A caixa **Voz** liga/desliga a leitura das respostas; a síntese começa após o streaming terminar e não bloqueia a janela. **Segure para falar** e o relay aceitam `whisper` ou `whisper-cli` (`whisper-cpp`) com um modelo local. No Arch, as fontes PipeWire/PulseAudio aparecem nas configurações de áudio, inclusive monitores virtuais como `AudioRelayVirtualMic`.
- Opcionalmente, `CODEPET_PROVIDER=codex` faz o Lume responder pelo Codex CLI autenticado neste usuário (`codex login status`). `CODEPET_PROVIDER=hybrid` mantém o DeepHat como primeira resposta e acrescenta uma segunda opinião do Codex CLI; se a conta online estiver indisponível, o texto local permanece utilizável. `CODEPET_CODEX_MODEL` escolhe um modelo específico; vazio usa o padrão do CLI. Os modos `codex` e `hybrid` precisam de internet e enviam a pergunta e o contexto autorizado à conta do Codex. Para voltar ao DeepHat local, use `CODEPET_PROVIDER=ollama` e reinicie backend e desktop. O CLI roda em diretório temporário, com sandbox `read-only`, sem configuração pessoal ou sessões persistidas; o CodePet rejeita eventos de ferramenta que detectar. Isso não equivale a isolar completamente um CLI com acesso ao usuário do sistema.
- O tutor não executa ferramentas autonomamente nem aplica patches. O desktop reconhece comandos explícitos do usuário para abrir aplicativos (fixos como navegador e terminal, ou qualquer app instalado pelo nome), controlar foco, guardar notas e pesquisar no projeto; respostas do modelo não disparam essas ações. Ferramentas são chamadas explicitamente pela UI, API ou servidor MCP. Não há shell irrestrito. O modo anti-procrastinação também não bloqueia aplicativos nem realiza ações fora do projeto autorizado.
- Recuperação de memória combina busca lexical ranqueada e recência por projeto, com orçamento de caracteres; não há embeddings nem retreinamento. `num_ctx` e `num_predict` limitam a inferência Ollama; a estimativa textual não é um tokenizer exato.
- A extensão compila, possui comandos de próximo passo/exercício e tenta reconectar ao backend; os fluxos de seleção e diagnóstico ainda precisam de validação manual no Extension Host real.

## VS Code

Requer VS Code/VSCodium compatível com VS Code **1.101+**, Node 22+ no Extension Host e um workspace local confiável.

```bash
cd apps/vscode-extension
npm install
npm test
code --extensionDevelopmentPath="$PWD"
```

Na nova janela: abra um diretório autorizado, execute `CodePet: Configurar token local` e informe o valor de `CODEPET_TOKEN` do seu `.env` **somente nesse campo protegido**. Não coloque o token em `settings.json`.

Configure `codepet.project` para o ID correspondente. A extensão verifica se a raiz do workspace coincide com a raiz autorizada. Selecione código e execute `CodePet: Explicar seleção` ou `CodePet: Analisar diagnóstico`. A resposta aparece no painel de saída **CodePet Tutor**.

Eventos automáticos exigem `codepet.enabled`; seleção e diagnósticos têm permissões separadas. Proatividade exige `CODEPET_PROACTIVE=true` no backend e `codepet.proactive=true` na extensão. Modo `silent` suprime as notificações na extensão. Não há captura automática de tela.

## Memória e permissões

No desktop: **Guardar nota**, **Memória** e **Executar testes**. Administração completa pela CLI:

```bash
.venv/bin/python scripts/codepetctl.py remember --project default --kind difficulty --content 'Tenho dificuldade com recursão'
.venv/bin/python scripts/codepetctl.py list --project default
.venv/bin/python scripts/codepetctl.py edit --project default --id 1 --kind topic --content 'Recursão revisada'
.venv/bin/python scripts/codepetctl.py export --project default > memoria-exportada.json
.venv/bin/python scripts/codepetctl.py delete --project default --id 1
.venv/bin/python scripts/codepetctl.py pause
.venv/bin/python scripts/codepetctl.py resume
```

`CODEPET_RETENTION=false` impede novas gravações e recuperação de memória após reiniciar. Dados antigos permanecem até exclusão explícita. SQLite não é criptografado; exportações também contêm dados privados.

Busca de memória: `GET /v1/memory/{project}/search?q=termo`. Exercícios: `POST /v1/exercises/{project}` com `prompt`, `answer` e `topic`, depois `POST /v1/exercises/{project}/{id}/review` com `rating` de 0 a 5. O terminal é observado somente de forma explícita por `POST /v1/terminal`; não há coleta silenciosa.

Executar testes significa executar código do projeto com as permissões do usuário. A confirmação mostra comando e diretório; o backend não concede aprovação por solicitação do modelo. O ambiente filho não recebe o token CodePet nem as variáveis de configuração do backend. Isso **não é uma sandbox de execução de código**.

## MCP

Instale o extra `mcp` e configure um cliente MCP confiável para executar, com este repositório como diretório de trabalho:

```bash
.venv/bin/python -m backend.app.mcp.server
```

O backend deve estar rodando. São expostas onze ferramentas com schemas tipados; a política real permanece centralizada no backend. `get_screen_context` exige captura opt-in via `CODEPET_SCREEN_CAPTURE=true`; `get_terminal_output` lê somente observações enviadas explicitamente por clientes. `propose_code_patch` apenas devolve uma proposta.

Este servidor MCP stdio foi testado com um cliente MCP local (handshake, lista de ferramentas e leitura autenticada). Ele **não está conectado automaticamente ao ChatGPT**; o provider Codex CLI é uma integração separada para respostas do pet, não uma conexão MCP com o ChatGPT web.

Para conectar ao ChatGPT web, veja [o guia do túnel MCP](docs/chatgpt-mcp.md). O lançador `scripts/run-mcp.sh` funciona mesmo quando o cliente inicia em outro diretório.

Para `run_project_tests`, a primeira chamada retorna `approval_required`, comando, diretório e ID. Um humano pode aprovar com a CLI usando `approve --id ID`; a segunda chamada MCP repete os mesmos argumentos incluindo `approval_id`. Não existe ferramenta MCP de aprovação. O TTL é de 120 segundos e a aprovação é consumida uma única vez.

## Verificação

```bash
.venv/bin/pytest -q
.venv/bin/ruff check backend apps/desktop scripts tests migrations
.venv/bin/alembic check
uv lock --check
npm test --prefix apps/vscode-extension

# Geração real, opt-in, servidor Ollama necessário:
CODEPET_LIVE=1 .venv/bin/pytest tests/e2e/test_live_ollama.py -q

# Fluxo real pelo backend, com primeira resposta e latência total:
.venv/bin/python scripts/smoke_chat.py

# RAM/CPU de um processo e VRAM global AMD, quando os contadores existirem:
.venv/bin/python scripts/measure.py PID --seconds 2
```

Os testes padrão de protocolo usam um provider de teste identificado como tal. Eles **não demonstram qualidade de respostas do DeepHat**. Veja [evidências e aceitação](docs/validation.md), [arquitetura](docs/architecture.md), [segurança](docs/security.md) e [roadmap](docs/roadmap.md).
