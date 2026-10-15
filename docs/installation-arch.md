# Instalação no Arch Linux / Hyprland

## Preparação

Requisitos: Python 3.12+, `uv`, Git, ripgrep e Ollama existente. Para construir a extensão: Node 22+ e npm. O Python do sistema nesta inspeção era 3.14.7; foi encontrado Python 3.12.14 já instalado pelo uv e usado na virtualenv. Não alteramos o Python do sistema.

Instale ferramentas que faltarem pelo seu gerenciador de pacotes. Exemplo, a executar conscientemente no host:

```bash
sudo pacman -S --needed uv git ripgrep nodejs npm espeak-ng whisper-cpp ggml-cpu grim bubblewrap
```

O PySide6 vem pelo extra Python `desktop`. Bibliotecas do host para Qt/Wayland/OpenGL devem estar disponíveis. Não misture arbitrariamente plugins Qt do sistema e de uma wheel de outra versão. Verifique `QT_PLUGIN_PATH`, `QT_QPA_PLATFORM_PLUGIN_PATH` e `QT_DEBUG_PLUGINS=1` se o carregamento falhar. PySide6 6.12 foi executado nesta sessão Hyprland.

```bash
bash scripts/install.sh
.venv/bin/python scripts/doctor.py
```

O instalador não usa sudo, não habilita serviços e não altera Hyprland. Se não houver Python 3.12, uv pode precisar baixá-lo. Uma instalação offline só é possível quando todas as wheels compatíveis já estiverem em cache.

## Ollama

```bash
ollama list
curl -sS http://127.0.0.1:11434/api/tags
```

Use o servidor existente. Descoberta não faz inferência, pull ou carregamento extra. Não suponha que DeepHat é multimodal. A aplicação envia somente texto.

Configure no `.env` um nome exato se a descoberta for ambígua. Ajuste `CODEPET_NUM_CTX` e `CODEPET_NUM_PREDICT` com medições; não presuma aceleração ROCm/Vulkan para a RX 580. O código funciona com a modalidade de execução que o Ollama existente realmente oferecer, inclusive CPU.

Para respostas pelo Codex CLI desta conta, instale o comando `codex`, execute `codex login` e configure `CODEPET_PROVIDER=codex` no `.env`. Para o modo híbrido, use `CODEPET_PROVIDER=hybrid`; o DeepHat gera a primeira resposta e o Codex acrescenta uma segunda opinião, com fallback local quando a conta online estiver indisponível. Opcionalmente, defina `CODEPET_CODEX_MODEL` para um modelo disponível; neste host foi validado `gpt-6-sol`. Reinicie backend e desktop. Estes modos enviam texto e contexto autorizado à conta online, dependem de internet e não usam o servidor MCP do CodePet para a geração. `codex login status` permite verificar a autenticação.

## Desktop e compositor

```bash
.venv/bin/python -m backend.app.main
# Em outro terminal da sessão Hyprland:
QT_QPA_PLATFORM=wayland .venv/bin/python -m apps.desktop.main
```

Inicialmente aparece apenas o pet. Duplo clique abre o chat; botão direito abre o menu. Arraste é solicitado ao compositor. No Hyprland 0.56.2 deste host, a aplicação usa `hyprctl` para tornar a janela flutuante, redimensioná-la, posicioná-la perto da borda inferior e fixá-la nos workspaces do monitor. Em outros compositores, a janela pode precisar de regras próprias.

O pet não ocupa uma camada layer-shell e não garante ficar acima de outras janelas. Ele anda dentro de uma janela pequena; a fixação acompanha a troca de workspace no mesmo monitor, sem atravessar monitores. A máscara de entrada e a limpeza de quadros foram verificadas visualmente neste Hyprland. `QT_QPA_PLATFORM=offscreen` testa criação/renderização, mas não substitui essa verificação no compositor.

Captura de tela opcional usa `grim` e permanece desabilitada por padrão. Para habilitar, instale `grim`, defina `CODEPET_SCREEN_CAPTURE=true` e reinicie o backend. A captura é uma ferramenta explícita e limitada; revise a imagem antes de enviá-la a qualquer provider online.

Para ouvir o Lume, deixe **Voz** marcada no chat. A síntese usa `espeak-ng` e a saída configurada no sistema. Para transcrição local, instale `whisper-cpp` e baixe um modelo uma vez:

```bash
mkdir -p ~/.local/share/whisper.cpp
curl -L --fail https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin \
  -o ~/.local/share/whisper.cpp/ggml-base.bin
```

O app detecta esse caminho automaticamente. Em outro local, defina `CODEPET_WHISPER_MODEL` antes de iniciar o desktop. O menu **Áudio** lista as fontes PipeWire/PulseAudio, incluindo monitores virtuais como `AudioRelayVirtualMic`; o padrão segue `pactl get-default-source`. No relay, a captura para durante a fala sintetizada para evitar que a resposta seja transcrita de volta.

Desmarcar **Voz**, cancelar ou iniciar outra pergunta interrompe a fala. A voz e a transcrição funcionam localmente, sem enviar áudio à internet.

## VS Code / VSCodium

```bash
cd apps/vscode-extension
npm install
npm test
code --extensionDevelopmentPath="$PWD"
# Se usa VSCodium, substitua code por codium.
```

Na janela de desenvolvimento, abra o projeto autorizado no `.env`, configure o token pelo comando CodePet e selecione código. Workspace remoto/container/SSH não é suportado nesta versão, pois o backend e a raiz precisam pertencer ao mesmo host.

Para distribuição, gere o VSIX com `npm run package`; testes com Extension Host real continuam pendentes. Os arquivos compilados em `dist` são gerados e não versionados.

## Diagnóstico

- `Connection refused`: backend ausente ou Ollama ausente no modo local; iniciar no host e verificar portas.
- Erro no modo Codex: executar `codex login status`, conferir `CODEPET_CODEX_MODEL` e conexão de internet.
- `Operation not permitted`: ambiente restrito bloqueia sockets; executar os comandos na sessão normal do usuário.
- Erro de modelo: configurar `CODEPET_MODEL` com resultado exato de `ollama list`.
- Erro de banco: executar `.venv/bin/alembic upgrade head` a partir da raiz antes do backend.
- Erro de projeto: comparar `CODEPET_PROJECTS`, a raiz aberta no editor e `codepet.project`.
- Erro de GUI: confirmar importação `PySide6`, sessão gráfica, bibliotecas e versão dos plugins.

Neste host, a instalação das dependências opcionais, a API Ollama, o cliente desktop Qt e o handshake MCP foram executados. Uma instalação limpa em outra máquina ainda deve ser validada; `scripts/install.sh` usa o `uv.lock` para reduzir diferenças entre ambientes.
