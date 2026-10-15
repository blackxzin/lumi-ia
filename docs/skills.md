# Skills locais do CodePet

Uma skill é um arquivo `SKILL.md` com instruções para uma tarefa. O CodePet a inclui no prompt do DeepHat apenas quando você a escolhe no chat. Isso não altera os pesos do modelo nem concede acesso a ferramentas. As permissões para ler arquivos ou executar testes continuam separadas.

O projeto inclui **Explicar código** (`explain-code`), **Investigar erro** (`debug-error`), **Ponytail** (`ponytail`), **Caveman** (`caveman`) e **Graphify (relatório)** (`graphify`). Ponytail busca a solução correta mais enxuta; Caveman reduz a verbosidade sem sacrificar precisão. São adaptações curtas das skills instaladas neste host, adequadas ao contexto de um modelo local de 7B. O chat lista as skills recebidas do backend em `GET /v1/skills`.

**Skills automáticas** é o padrão: Ponytail, Caveman e Graphify entram juntas em toda pergunta, inclusive quando o cliente não envia o campo `skill`. O evento `state` do WebSocket e a barra de status do chat mostram quais foram usadas. Você ainda pode escolher uma skill específica ou **Sem skill**; isso substitui o trio nessa pergunta.

Graphify lê até 2.000 caracteres de `graphify-out/GRAPH_REPORT.md` dentro do projeto autorizado quando está ativa. Se o relatório não existir, o pet só deve mencionar a ausência em perguntas que dependam do grafo. O CodePet ainda não gera nem atualiza um grafo; isso exige uma ferramenta Graphify externa. O relatório passa pelo mesmo bloqueio de caminhos sensíveis e links simbólicos usado para os outros arquivos de projeto.

Para criar uma skill sua, faça um diretório em `~/.config/codepet-ai/skills/` com um identificador curto e um `SKILL.md`. Por exemplo:

```text
~/.config/codepet-ai/skills/revisar-testes/SKILL.md
```

```md
---
name: Revisar testes
description: Encontra lacunas nos testes existentes.
---
Examine os testes citados na pergunta. Aponte casos ausentes com base no código fornecido. Separe observações de hipóteses. Sugira um teste pequeno por vez.
```

O diretório pode ser alterado por `CODEPET_SKILLS_DIR`. Identificadores aceitam letras minúsculas, números, `_` e `-`, começando por letra. Cada arquivo tem limite de 4 KiB, com até 2.400 caracteres de instruções. Diretórios e arquivos simbólicos são ignorados. Reinicie ou reconecte o chat para atualizar a lista; o backend lê os arquivos novamente a cada consulta.

Este é um subconjunto simples do formato `SKILL.md` usado em outros assistentes: `name`, `description` e instruções em Markdown. Skills que dependem de scripts, recursos anexos, comandos de shell ou ferramentas próprias não funcionam automaticamente no CodePet. Revise e adapte uma skill antes de copiá-la; o modelo local só recebe o texto da skill selecionada e as evidências já autorizadas no chat.
