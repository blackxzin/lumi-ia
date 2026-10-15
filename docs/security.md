# Segurança e privacidade

## Fronteira de confiança

O backend é um serviço de usuário local, não multiusuário e não remoto. O launcher fixa `127.0.0.1`. Não o publique com reverse proxy nem altere o bind sem um novo projeto de segurança.

O token aleatório nasce em `.env` com permissão `0600`, é usado pelo desktop, extensão e adaptador MCP e nunca entra em query strings. Clientes que possuem o token têm autoridade administrativa, inclusive para gerenciar memória e conceder aprovações. **A separação de aprovação protege o modelo e suas ferramentas, não um cliente local comprometido.** Não dê esse token a plugins desconhecidos.

O middleware rejeita origens de navegador, Host inesperado, corpos HTTP acima de 64 KiB e mais de 120 requisições/minuto no processo. Não há CORS permissivo. WebSocket autentica em cinco segundos, limita conexões, frames, requisições simultâneas e repetição por conexão. O runtime padrão é de um processo; não use vários workers, pois fila, pausa, rate limit e aprovações são locais ao processo.

## Arquivos e execução

Cada projeto precisa de uma raiz absoluta existente. Leitura exige caminho relativo; bloqueia `..`, componentes ocultos, symlinks, diretórios excluídos, arquivos privados comuns, binários e arquivos acima de 64 KiB. A leitura percorre descritores com `O_NOFOLLOW`, evitando a troca de symlink entre validação e abertura. Esta implementação é Linux; portabilidade Windows está pendente.

A busca examina até 200 arquivos e 30 ocorrências, com prazo e limites de saída. O diff exige um único arquivo autorizado e desabilita drivers externos/textconv. Os comandos são listas fixas com `create_subprocess_exec`, nunca strings entregues a um shell. Saída é truncada em 32 KiB; processos têm timeout, grupo próprio e encerramento de filhos.

`run_project_tests` é sensível: exige uma aprovação de ação específica, com hash dos argumentos, TTL de 120 s e consumo único. Por padrão usa Bubblewrap, com rede desabilitada, `/tmp` temporário e apenas o projeto montado para escrita. Se Bubblewrap não estiver disponível, o teste não roda; `CODEPET_TEST_SANDBOX=none` é um opt-out explícito e inseguro. Não aprove projetos desconhecidos sem revisão.

Patches são propostas inertes. Não há ferramentas para instalação de pacotes, comandos arbitrários, alteração de arquivos ou rede externa. Conteúdo de arquivo, terminal ou LLM não pode conceder aprovação. Auditoria de ferramentas registra nome, projeto e resultado via logger `codepet.audit`, sem conteúdo de código ou credenciais. Por padrão vai ao stderr; retenção/rotação de auditoria em arquivo ainda não existe.

## Memória e observação

SQLite local contém texto não criptografado. `.codepet` é criado com permissão restrita quando o diretório não existe. Use permissões de diretório e criptografia de disco conforme necessário. Exclusão pela API é lógica no SQLite; não é uma promessa de apagamento forense ou remoção de backups.

Desativar retenção bloqueia novas gravações e recuperação; não apaga dados existentes. Consultas e mutações incluem projeto. Clientes autenticados podem acessar qualquer projeto configurado: isolamento de contexto não é isolamento de usuários.

Pausar descarta contexto do editor, reinicia os contadores proativos e cancela gerações ativas/na fila. Novos eventos são ignorados até retomar. Perguntas manuais continuam possíveis, sem contexto do editor. A extensão cancela envios em andamento quando a pausa é solicitada por ela e sempre consulta o estado do backend antes de novos envios.

Captura de tela é opt-in via `grim` e `CODEPET_SCREEN_CAPTURE=true`; o PNG fica apenas na resposta autenticada, com limite de tamanho, e não é salvo pelo backend. O terminal não é vasculhado: clientes precisam enviar explicitamente uma observação limitada para `POST /v1/terminal`, que fica apenas no runtime. A fala usa `espeak-ng` local com argumentos diretos, sem shell nem envio de texto para serviço externo. O provider Ollama aceita somente origem HTTP loopback e ignora proxies de ambiente.

Com `CODEPET_PROVIDER=codex` ou `hybrid`, o texto da pergunta, histórico selecionado, skills e contexto autorizado seguem para o Codex CLI e sua conta online. No modo híbrido, o DeepHat responde primeiro e o mesmo contexto é enviado ao Codex para a segunda opinião. O processo usa `--sandbox read-only`, `--ephemeral`, `--ignore-user-config` e um diretório temporário, sem variáveis `CODEPET_*`. O CodePet interrompe a geração se receber eventos de ferramenta, mas isso **não garante** que uma ferramenta não tenha começado antes da detecção; o CLI tem acesso aos arquivos que o usuário pode ler. Habilite estes providers apenas sabendo que eles não possuem o isolamento rígido do provider Ollama local. Nenhuma chave OpenAI é armazenada pelo CodePet.

## Ameaças restantes

- Bloqueio por nomes de arquivos não identifica todo segredo colocado dentro de código permitido. Revise a seleção antes de compartilhar.
- Prompt de segurança reduz ambiguidades, mas não garante que o LLM ignore toda injeção. Não expor execução autônoma limita o impacto.
- Um processo do mesmo usuário pode ler arquivos e segredos do usuário; o token não isola processos comprometidos.
- Busca lexical substitui embeddings neste núcleo; conexão MCP com ChatGPT web e provider direto OpenAI API continuam opcionais/fora do escopo. Captura de tela e terminal exigem habilitação/observação explícitas.
