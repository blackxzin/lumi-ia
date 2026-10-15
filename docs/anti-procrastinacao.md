# Modo anti-procrastinação

O Lume possui um modo de foco curto e gentil para transformar uma intenção vaga em uma ação concreta.

## Como usar

1. Abra o chat do pet.
2. Escreva uma meta pequena, por exemplo: `escrever o primeiro teste`.
3. Escolha 15, 25 ou 50 minutos.
4. Clique em **Começar foco**.

Durante a sessão, o contador fica visível, o chat usa respostas curtas e orientadas ao próximo passo e a extensão pode enviar somente o contexto autorizado. Ao terminar, o Lume sugere uma pausa de cinco minutos. A sessão pode ser pausada, retomada ou concluída antes do tempo.

O modo não bloqueia aplicativos, não encerra processos, não captura tela e não envia mensagens sozinho. Ele usa reforço positivo, check-ins explícitos e metas pequenas para reduzir a fricção de começar.

## Contrato técnico

- O protocolo de conversa usa `mode: "focus"`.
- A sessão é isolada por projeto e vive no backend enquanto ele estiver em execução.
- `GET /v1/focus/{project}` consulta o estado atual.
- `POST /v1/focus/{project}` aceita `start`, `pause`, `resume`, `complete` e `cancel`.
- O backend valida a meta, limita foco a 1–120 minutos e pausa a 1–30 minutos.
- A sessão não concede permissões novas às ferramentas nem permite execução autônoma.

Sessões concluídas entram no histórico SQLite e aparecem em **Progresso**, com total de sessões, minutos focados e última meta. Exercícios persistentes podem ser criados por `POST /v1/exercises/{project}` e revisados com notas de 0 a 5 em `POST /v1/exercises/{project}/{id}/review`; o próximo vencimento é calculado localmente por repetição espaçada simples.
