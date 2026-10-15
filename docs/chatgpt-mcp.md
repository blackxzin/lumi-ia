# CodePet MCP no ChatGPT

O servidor CodePet usa transporte MCP `stdio` e já foi testado localmente. O ChatGPT web não inicia servidores locais diretamente. A [documentação da OpenAI](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt) orienta usar [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) para conectar um servidor privado, sem publicar o backend na internet.

## Preparar o CodePet

Mantenha o backend ativo (`.venv/bin/python -m backend.app.main`). O script `scripts/run-mcp.sh` muda para a raiz do projeto, carrega a configuração local pelo processo Python e inicia o MCP. Use o caminho absoluto do script como comando do túnel; espaços no caminho exigem aspas na configuração do cliente.

## Configurar o túnel

1. Confirme no ChatGPT web que sua conta/workspace permite modo de desenvolvedor e conexão MCP. Conforme a [disponibilidade atual](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt), suporte MCP completo está em beta para Business e Enterprise/Edu; Pro pode conectar ferramentas de leitura/busca em modo de desenvolvedor.
2. Em [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels), crie um túnel e associe o workspace ChatGPT que vai usá-lo. Você precisa de um `tunnel_id`, uma chave de API de execução e das permissões de túnel indicadas na [documentação oficial](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
3. Instale o `tunnel-client` pelo link oferecido nessa página. No terminal local, configure a chave conforme as instruções do cliente e inicialize um perfil `stdio` com `--mcp-command` apontando para o caminho absoluto de `scripts/run-mcp.sh`. Exemplo, substituindo os marcadores:

   ```bash
   tunnel-client init \
     --sample sample_mcp_stdio_local \
     --profile codepet \
     --tunnel-id SEU_TUNNEL_ID \
     --mcp-command '"/home/polar/projeto anti foco/scripts/run-mcp.sh"'
   tunnel-client doctor --profile codepet --explain
   tunnel-client run --profile codepet
   ```

   Guarde a chave em um gerenciador de segredos ou no mecanismo recomendado pelo cliente; não a coloque neste repositório nem em um comando compartilhado. Mantenha backend e túnel ativos durante o uso.
4. No [ChatGPT Plugins](https://chatgpt.com/plugins), escolha **Add custom MCP server → Tunnel**, selecione o túnel, revise as permissões e crie a conexão. Abra um chat novo, selecione o plugin CodePet e peça, por exemplo, para listar diagnósticos de um projeto autorizado. A [documentação oficial](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) descreve esses passos e o diagnóstico do túnel.

O projeto **não contém** o `tunnel-client` nem acesso à sua conta ChatGPT. O teste local confirma o protocolo e as ferramentas; o uso dentro do ChatGPT só estará confirmado depois de o túnel conectar e uma chamada real funcionar no chat. Ao usar ferramentas de leitura, o conteúdo solicitado atravessará o túnel para o ChatGPT. O backend continua limitado a `127.0.0.1`; não publique a porta 8765 diretamente.
