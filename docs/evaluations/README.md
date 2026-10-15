# Avaliação do DeepHat local — 2026-10-12

Modelo instalado: `hf.co/mradermacher/DeepHat-V1-7B-GGUF:Q5_K_M`, Ollama local, Ryzen 5 4600G. Nenhum peso foi alterado e nenhum modelo foi baixado. Perguntas sintéticas; nenhuma memória pessoal entrou na avaliação.

## Comparação de desenvolvimento

As mesmas seis perguntas foram executadas uma vez por versão. Critérios foram escritos antes da execução; a classificação abaixo é uma revisão qualitativa do conteúdo feita pelo assistente, não uma pontuação automática independente.

| Configuração | Tempo mediano total | Caracteres médios | Casos que atenderam integralmente ao critério |
|---|---:|---:|---:|
| Prompt inicial, parâmetros gerais | 22,03 s | 364 | 1/6 |
| Prompt revisado, temperatura 0,2, até 192 tokens | 18,45 s | 370 | 2/6 |
| Mesmo ajuste + quatro exemplos curtos de conversa | 9,27 s | 169 | 5/6 |

A primeira geração em cada rodada pode incluir custo de carregar o modelo ou processar um prompt novo. Sem o primeiro caso, as medianas foram 20,48 s, 17,75 s e 6,94 s. São medidas de execuções únicas na mesma máquina, sem isolamento de carga ou intervalos de confiança; não representam uma garantia de velocidade.

- Saudação: antes oferecia funções não pedidas e dizia agir automaticamente; a versão final cumprimentou em poucas frases.
- Foco em Python: antes recomendava instalar `requests`; a versão final sugeriu executar um exemplo mínimo.
- NameError: correção técnica adequada nas três versões.
- Falta de contexto: antes inventava um comando `buscar erros`; a versão final pediu código e mensagem de erro.
- Ação executada: antes afirmou falsamente ter aberto o navegador; a versão final não alegou execução.
- Planejamento de relatório: melhorou a relevância, mas continuou genérico e com várias etapas. Não aprovado no critério de uma única ação inicial.

## Perguntas novas

Após os ajustes, três perguntas diferentes foram executadas sem novo ajuste posterior. Resultado: **2/3** critérios atendidos.

- Diferença entre `=` e `==`: correta.
- Memória sobre ontem: admitiu falta de informações, sem inventar acontecimentos; poderia ser mais direto sobre não possuir histórico de atividades.
- Retomar tarefa doméstica (louça): resposta incoerente e com várias ações. Falhou.

### Rechecagem após ajuste de instruções

Uma rodada adicional foi executada no DeepHat local depois de acrescentar instruções mais firmes para foco cotidiano e exemplos curtos para uma ação inicial e para `=`/`==`. O script usou novamente as três perguntas holdout; esta rechecagem é comparável em tema, mas não independente dos exemplos de foco adicionados.

| Caso | Primeiro token | Total | Revisão humana |
|---|---:|---:|---|
| Foco doméstico | 28,75 s | 34,82 s | Ainda falhou: sugeriu colocar a louça numa prateleira e fechar uma porta, sem saber se isso existe ou ajuda. Uma ação apenas não basta se ela for incoerente. |
| `=` e `==` | 1,27 s | 14,33 s | Correto e breve; explicou que `x` deve estar definido antes da comparação. |
| Memória de ontem | 1,05 s | 6,73 s | Honesto quanto à ausência de histórico. |

O filtro automático marcou 3/3 como aprovados, mas a revisão humana marcou o foco como falha. Isso demonstra que os sinais lexicais do script não substituem avaliação semântica. O ajuste melhorou os dois padrões de programação/honestidade observados nesta amostra, porém não resolveu de forma confiável tarefas gerais de foco. Para esse caso, a recomendação permanece usar uma instrução de foco baseada em contexto explícito ou revisão pelo provider Codex quando a resposta local soar estranha.

O DeepHat ficou mais útil para conversa curta e programação nesta amostra, mas continua falhando em tarefas gerais. A troca explícita para Codex é útil quando uma resposta local não atende. Os testes não sustentam afirmar que o modelo é infalível ou que todas as tarefas estão resolvidas.

## Evidências e reprodução

- `deephat-baseline.json`: respostas originais e prompt inicial.
- `deephat-tuned.json`: ajuste de prompt e geração, antes dos exemplos.
- `deephat-examples.json`: versão mantida, incluindo exemplos usados.
- `deephat-holdout.json`: perguntas novas e falhas preservadas.
- `scripts/evaluate_local_assistant.py`: avaliação reproduzível; `--profile tuned --holdout` roda as perguntas novas.

Os exemplos são mensagens sintéticas de demonstração e não são persistidos como memória. O orçamento de contexto inclui esses exemplos. A configuração só altera o modo assistente; tutor e copiloto mantêm suas opções de geração.
