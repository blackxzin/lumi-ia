# Roadmap incremental e critérios de avanço

| Fase | Entrega atual | Próximo critério |
|---|---|---|
| 1 Fundação | Backend e DeepHat real via Ollama com streaming; GUI Qt conectada | Medir recursos em uso contínuo e validar instalação limpa |
| 2 Pet | SVG original com chapéu e doze estados, menu, chat, pausa e preferências persistentes de tamanho/velocidade | Avaliar comportamento em outros compositores |
| 3 VS Code | Extensão TypeScript compilada, contexto opt-in, reconexão limitada, próximo passo e exercício | Extension Host real; fluxos B/C e pausa entre clientes |
| 4 Contexto | Leitura restrita, pesquisa limitada, Git e evidências | Casos reais de depuração, cache e seleção de contexto melhor |
| 5 MCP | Adaptador stdio oficial, onze ferramentas; handshake e leitura real testados novamente | Testar mais ferramentas via cliente MCP; conexão com ChatGPT não configurada |
| 6 Memória/professor | SQLite com migração, CRUD visual/exportação, preferências, progresso, busca lexical, exercícios persistentes e revisão espaçada | Embeddings opt-in e compactação |
| 7 Proativo | Eventos, repetição, debounce/cooldown e opt-in; modo anti-procrastinação com meta e sessões temporizadas | Ampliar check-ins opt-in sem gamificação compulsiva |
| 8 Visão/voz | TTS local, push-to-talk/STT opcional via `whisper` local e captura opt-in via `grim` | Avaliar voz de maior qualidade e visão multimodal |
| 9 OpenAI | Ponte opcional ao Codex CLI autenticado; sem provider direto da API | Consentimento por envio, orçamento/custos, provider API e roteamento por pergunta |
| 10 Estabilização | Instalador com lockfile, testes, CI, documentação, sandbox de testes e scripts de medição | Instalação limpa, métricas reais, VSIX e validações gráficas |

Os fluxos de Ollama, desktop e MCP foram exercitados neste host. A extensão ainda precisa de validação no Extension Host real; voz tem saída TTS local e o provider direto da API da OpenAI permanece fora do escopo. Nenhuma aprovação isolada equivale à aceitação completa dos oito fluxos.

Pendências técnicas adicionais:

- Distinguir métricas de progresso pedagógico de simples notas persistentes.
- Exibir histórico detalhado de sessões; revisão espaçada e exercícios persistentes já têm armazenamento e endpoints.
- Agrupar diagnósticos por identidade estável de sessão de editor e limpar contexto ao fechar arquivo; hoje é mantido o último contexto autorizado até nova coleta ou pausa.
- Levar resultados de testes e sugestões aceitas/rejeitadas para memória estruturada.
- Tratar limites e fairness da fila, reconexão automática com backoff e modos proativos por sessão.
- Separar credencial administrativa de clientes de contexto antes de ampliar confiança em plugins.
- Expandir auditoria durável sem reter código/segredos e política de tamanho/expiração da memória.
- Fazer distribuição autossuficiente das migrações e assets; a instalação local já usa lockfile, mas ainda é editável a partir deste checkout.
