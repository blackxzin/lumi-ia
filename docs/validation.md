# Atualização — assistente Lume, 2026-10-12

- 93 testes automatizados passaram após comandos, seleção de provider, foco, memória, cancelamento e ajustes de voz. Três testes live ficam pulados na execução padrão; dois deles foram executados separadamente e passaram.
- Ruff, lockfile uv, compilação/teste da extensão e `alembic check` aprovados. O metadata de `focus_plans.project` foi alinhado ao índice já existente na migração, sem alteração de dados.
- O Ollama real estava disponível com DeepHat Q5_K_M. Foram executadas três rodadas de seis perguntas e uma rodada de três perguntas novas. [Relatório completo](evaluations/README.md), incluindo respostas ruins preservadas.
- A mediana da pequena amostra de desenvolvimento caiu de 22,03 s para 9,27 s; 5/6 critérios foram atendidos. Em perguntas novas, 2/3. Não equivale a qualidade garantida fora desses casos.
- Os dois testes live Qt → backend → modelo passaram em 17,52 s: a interface interpretou a troca textual, enviou a pergunta ao provider escolhido e recebeu a resposta real de DeepHat e Codex. A captura humana do microfone não faz parte desses testes.
- Codex explícito pelo WebSocket respondeu em 4,51 s a uma pergunta curta, sem resposta adicional do DeepHat.
- Whisper real reconheceu áudio sintetizado com “Lume, abra o terminal”, “Lume, mude para o Codex” e “Lume, quero modelo local DeepHat”. Estes testes não substituem uma conversa humana no microfone.
- Dispositivos AudioRelay/PipeWire e microfone físico disponíveis. `espeak-ng` e o modelo local Whisper encontrados. A voz permanece sintética; nenhuma voz neural foi instalada.
- O encerramento do desktop por SIGINT foi validado com código 0 após encaminhar os sinais para a limpeza do Qt. Backend e desktop foram reabertos com a versão final.
- A interface foi renderizada e inspecionada em 720×700: seletor de modelo, ativação por nome e comandos visíveis. Controles que antes tinham texto cortado foram agrupados em menus; campos de texto e nível de áudio ganharam fundo legível.
- O desktop usa DeepHat por padrão, permite escolher Codex por voz/texto/UI e não troca automaticamente em caso de falha do provider escolhido. A escolha persiste, mantendo a mesma conversa.

---

# Evidências de validação — 2026-10-10

## Ambiente observado

- Python do sistema 3.14.7; virtualenv com Python 3.12.14.
- Hyprland 0.56.2 em Wayland; PySide6 6.12 executado com a janela real.
- Na validação histórica, Ollama respondeu em `127.0.0.1:11434` e `ollama list` retornou `hf.co/mradermacher/DeepHat-V1-7B-GGUF:Q5_K_M`; na inspeção atual, o endpoint estava indisponível.
- O diretório não é um repositório Git utilizável; nenhum commit foi criado.

## Verificações executadas

| Verificação | Resultado |
|---|---|
| `.venv/bin/pytest -q` | 59 aprovados, 2 pulados (testes de geração real opt-in) |
| `.venv/bin/ruff check backend apps/desktop scripts tests migrations` | Aprovado |
| `npm test --prefix apps/vscode-extension` | Compilação TypeScript e teste de política aprovado |
| `CODEPET_LIVE=1 .venv/bin/pytest tests/e2e/test_live_ollama.py -q` | Geração DeepHat real aprovada |
| `.venv/bin/python scripts/smoke_chat.py` | Streaming real pelo backend; primeiro token 10,58 s, total 19,58 s numa execução |
| `CODEPET_DESKTOP_LIVE=1 QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/e2e/test_desktop_live.py -q` | Cliente Qt recebeu resposta real por WebSocket; execução de aproximadamente 89 s |
| Servidor MCP stdio | Handshake, lista de 11 ferramentas e `read_project_file` por backend ativo aprovados novamente; não há conexão configurada ao ChatGPT |
| Voz local | `espeak-ng` com `pt-br` gerou e reproduziu uma frase pelo processo Qt, encerrando com código 0; chat acumula os tokens e fala apenas ao receber `done` |
| Codex CLI | `codex login status` confirmou a conta; `codex exec --json --sandbox read-only --ephemeral --ignore-user-config` respondeu uma frase real. O backend reiniciado anunciou `Codex CLI (gpt-6-sol)` em `/v1/model`; uma chamada autenticada pelo WebSocket retornou `done` e “Sou Lume, seu tutor de programação.” Provider passou em testes com CLI simulado, inclusive bloqueio de eventos de ferramenta. O resultado chega ao chat após a conclusão do CLI, sem streaming de tokens intermediários. |
| Janela Hyprland + captura restrita à janela | Pet flutuante 360×190 perto da borda inferior; caminhada sem trilhas brancas, saudação e sequência do notebook (frente → perfil digitando → frente) observadas. Sprite padrão reduzido para escala 4,5; notebook lateral com tela voltada ao pet e balão compacto verificados em renderização Qt offscreen. Cajado e remoção de faíscas também validados. |
| Chat translúcido Qt offscreen | Fundo externo totalmente transparente, painel translúcido e texto claro confirmados por inspeção de pixels. A aparência no compositor ainda depende do tema e do fundo da área de trabalho. |
| Skills locais | Catálogo `SKILL.md`, seleção no chat, validação de ID, orçamento de contexto e inclusão no prompt do provider validados com provider simulado. Ponytail, Caveman e leitura limitada de relatório Graphify também testados. Uma requisição WebSocket real sem escolha manual informou as três skills no evento `state` e recebeu `done` e texto do DeepHat. Uma saudação real `oi` recebeu resposta pertinente após remover evidências nulas e histórico irrelevante desse caso. A aderência a limites exatos de extensão ainda não é garantida. |

Os testes do pet verificam que a posição anterior volta a ser transparente após caminhar e que quadros de caminhada, piscada e sono são distintos. Também foi corrigida uma colisão entre o método de evento do chat e `QWidget.event`, que impedia a abertura real da janela. Os testes padrão usam um provider simulado; só os testes opt-in e o smoke exercitam DeepHat. Um aviso de depreciação do Starlette TestClient permanece sem afetar as aprovações.

## Fluxos de aceitação

| Fluxo | Estado e limite |
|---|---|
| A Pet → DeepHat → streaming | Componentes reais validados: pet Hyprland, cliente Qt/WebSocket e DeepHat. A interação manual completa ainda merece teste de uso continuado. |
| B Seleção VS Code → explicação | Extensão compila e política de caminhos passa; falta carregá-la no Extension Host e pedir explicação real. |
| C Erro real → diagnóstico | Esquema e contexto testados; falta conferir um diagnóstico real no editor e a resposta do modelo. |
| D Erro repetido → sugestão | Debounce, repetição, silêncio e cooldown testados; falta medir ruído na integração real. |
| E Memória em outra sessão | Persistência após reabrir SQLite e isolamento por projeto validados em teste. |
| F Testes após aprovação | Processo pytest real após aprovação específica e de uso único validado no backend; falta repetir pela interface desktop. |
| G Pausa | Backend ignora eventos e remove contexto/cancela geração em teste; captura de tela permanece opt-in e depende de Wayland/grim. |
| H Sem internet | Não há provider externo obrigatório; falta repetir a geração real com a rede desligada. |

Não foi medida ainda a RAM/VRAM/CPU do conjunto durante uma sessão longa. `scripts/measure.py` oferece amostragem de processo e contadores de VRAM quando disponíveis; os números de latência acima descrevem apenas uma execução, sem garantia de desempenho constante. O provider direto da API da OpenAI permanece fora do escopo.
