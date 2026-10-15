import * as vscode from 'vscode';
import * as fs from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { safeRelative } from './policy';

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel('CodePet Tutor');
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 5);
  status.text = '$(debug-pause) CodePet: contexto desligado';
  status.command = 'codepet.pause';
  status.show();
  let paused = false;
  let socket: WebSocket | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let generation = 0;
  let requesting = false;
  let healthRetry = 0;
  const session = randomUUID();
  const config = () => vscode.workspace.getConfiguration('codepet');
  const controllers = new Set<AbortController>();

  async function token(): Promise<string> {
    const value = await context.secrets.get('codepet.token');
    if (!value) throw new Error('Configure o token usando CodePet: Configurar token local.');
    return value;
  }

  async function api(route: string, body?: unknown): Promise<any> {
    const controller = new AbortController();
    controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch('http://127.0.0.1:8765' + route, {
        method: body === undefined ? 'GET' : 'POST',
        headers: {Authorization: 'Bearer ' + await token(), 'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal, redirect: 'error'
      });
      if (!response.ok) throw new Error('Backend rejeitou a requisição: ' + response.status);
      return await response.json();
    } finally {
      clearTimeout(timeout);
      controllers.delete(controller);
    }
  }

  async function apiWithRetry(route: string, body?: unknown): Promise<any> {
    let last: unknown;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const result = await api(route, body);
        healthRetry = 0;
        return result;
      } catch (error) {
        last = error;
        healthRetry += 1;
        if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)));
      }
    }
    throw last;
  }

  async function sendContext(explicit = false): Promise<boolean> {
    if (paused || !vscode.workspace.isTrusted || (!explicit && !config().get<boolean>('enabled'))) return false;
    const epoch = generation;
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.uri.scheme !== 'file') return false;
    const folder = vscode.workspace.getWorkspaceFolder(editor.document.uri);
    if (!folder) return false;
    const [root, realFile] = await Promise.all([fs.realpath(folder.uri.fsPath), fs.realpath(editor.document.uri.fsPath)]);
    const relative = safeRelative(root, editor.document.uri.fsPath);
    // Reject symlinks and folders which do not match the configured backend project.
    if (!relative || realFile !== editor.document.uri.fsPath) return false;
    const project = config().get<string>('project', 'default');
    const health = await apiWithRetry('/health');
    if (health.paused) { status.text = '$(debug-pause) CodePet: backend pausado'; return false; }
    if (health.roots?.[project] !== root) throw new Error('Raiz do workspace difere do projeto autorizado no backend.');
    const diagnostics = (explicit || config().get<boolean>('shareDiagnostics')) ? vscode.languages.getDiagnostics(editor.document.uri)
      .slice(0, 30).map(d => ({line: d.range.start.line + 1, message: d.message.slice(0, 2000),
        severity: ['error', 'warning', 'info', 'hint'][d.severity]})) : [];
    const selection = (explicit || config().get<boolean>('shareSelection')) ? editor.document.getText(editor.selection).slice(0, 8000) : '';
    if (paused || epoch !== generation) return false;
    const response = await apiWithRetry('/v1/editor', {v: 1, project, path: relative, language: editor.document.languageId,
      selection, selection_line: editor.selection.start.line + 1, diagnostics});
    if (paused || epoch !== generation || response.status === 'paused') return false;
    status.text = config().get<boolean>('enabled') ? '$(eye) CodePet: contexto ativo' : '$(check) CodePet: contexto enviado';
    if (!explicit && response.suggestion && config().get<boolean>('proactive') && config().get<string>('mode') !== 'silent') {
      const action = await vscode.window.showInformationMessage(response.suggestion.message, 'Analisar');
      if (action === 'Analisar') await ask('Explique o diagnóstico com base nas evidências, citando arquivo e linha.');
    }
    return true;
  }

  async function ask(prompt: string): Promise<void> {
    if (paused) throw new Error('Observação pausada. Retome antes de solicitar contexto.');
    if (socket || requesting) throw new Error('Já existe uma resposta em andamento. Aguarde ou cancele.');
    requesting = true;
    try {
    const approved = await vscode.window.showInformationMessage(
      'Enviar seleção e diagnósticos deste arquivo ao CodePet local para esta solicitação?',
      {modal: true}, 'Enviar');
    if (approved !== 'Enviar' || !await sendContext(true)) return;
    const secret = await token();
    const ws = new WebSocket('ws://127.0.0.1:8765/v1/chat');
    socket = ws;
    output.show(true);
    output.appendLine('\nVocê: ' + prompt);
    const timeout = setTimeout(() => ws.close(), 190000);
    ws.addEventListener('open', () => ws.send(JSON.stringify({v: 1, type: 'auth', token: secret})));
    ws.addEventListener('message', raw => {
      try {
        if (typeof raw.data !== 'string' || raw.data.length > 65536) { ws.close(); return; }
        const event = JSON.parse(raw.data);
        if (event.type === 'ready') ws.send(JSON.stringify({v: 1, type: 'chat', request_id: randomUUID(), session,
          project: config().get<string>('project', 'default'), prompt, mode: config().get<string>('mode', 'tutor'), use_editor: true}));
        if (event.type === 'token') output.append(event.content);
        if (['done', 'cancelled', 'error'].includes(event.type)) {
          output.appendLine(event.message || '\n');
          ws.close();
        }
      } catch { output.appendLine('Resposta inválida do backend.'); ws.close(); }
    });
    ws.addEventListener('error', () => output.appendLine('Falha na conexão local. Verifique o backend.'));
    ws.addEventListener('close', () => { clearTimeout(timeout); if (socket === ws) socket = undefined; });
    } finally { requesting = false; }
  }

  function guarded(fn: () => Promise<unknown>): () => Promise<void> {
    return async () => { try { await fn(); } catch (error) { void vscode.window.showErrorMessage(String(error)); } };
  }
  async function projectId(): Promise<string> {
    return config().get<string>('project', 'default');
  }
  function schedule(): void {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      void sendContext().catch(() => {
        status.text = '$(warning) CodePet: backend indisponível';
        if (healthRetry < 3) setTimeout(schedule, 2500);
      });
    }, 700);
  }
  context.subscriptions.push(output, status,
    vscode.commands.registerCommand('codepet.configureToken', guarded(async () => {
      const value = await vscode.window.showInputBox({prompt: 'CODEPET_TOKEN do .env local', password: true,
        validateInput: text => text.length >= 32 ? undefined : 'O token precisa ter pelo menos 32 caracteres.'});
      if (value) await context.secrets.store('codepet.token', value);
    })),
    vscode.commands.registerCommand('codepet.explain', guarded(() => ask('Explique a seleção em passos, usando o contexto fornecido.'))),
    vscode.commands.registerCommand('codepet.diagnose', guarded(() => ask('Analise os diagnósticos. Distinga hipótese de erro confirmado e cite arquivo e linha.'))),
    vscode.commands.registerCommand('codepet.nextStep', guarded(() => ask('Indique o menor próximo passo concreto para eu avançar agora.'))),
    vscode.commands.registerCommand('codepet.exercise', guarded(() => ask('Crie um exercício curto sobre o assunto atual e espere minha resposta.'))),
    vscode.commands.registerCommand('codepet.cancel', () => socket?.send(JSON.stringify({v: 1, type: 'cancel'}))),
    vscode.commands.registerCommand('codepet.progress', guarded(async () => {
      const data = await apiWithRetry('/v1/learning/' + encodeURIComponent(await projectId()));
      const focus = data.focus || {};
      const metrics = data.metrics?.events || {};
      void vscode.window.showInformationMessage(`Hoje: ${focus.today_sessions || 0} sessões · ${focus.minutes || 0} min totais · ${metrics.chat_completed || 0} respostas concluídas.`);
    })),
    vscode.commands.registerCommand('codepet.saveResult', guarded(async () => {
      const value = await vscode.window.showInputBox({prompt: 'O que você conseguiu ou aprendeu?', placeHolder: 'Ex.: corrigi o teste de autenticação'});
      if (!value?.trim()) return;
      await apiWithRetry('/v1/memory/' + encodeURIComponent(await projectId()), {kind: 'result', content: value.trim()});
      void vscode.window.showInformationMessage('Resultado guardado na memória da Lumi.');
    })),
    vscode.commands.registerCommand('codepet.pause', guarded(async () => {
      paused = true; generation++; if (timer) clearTimeout(timer);
      for (const controller of controllers) controller.abort();
      socket?.close();
      status.text = '$(debug-pause) CodePet: pausado localmente';
      await api('/v1/observation', {paused: true});
      status.text = '$(debug-pause) CodePet: observação pausada';
    })),
    vscode.commands.registerCommand('codepet.resume', guarded(async () => {
      await api('/v1/observation', {paused: false}); paused = false; schedule();
    })),
    vscode.window.onDidChangeActiveTextEditor(schedule),
    vscode.workspace.onDidOpenTextDocument(schedule),
    vscode.window.onDidChangeWindowState(schedule),
    vscode.window.onDidChangeTextEditorSelection(schedule),
    vscode.workspace.onDidChangeTextDocument(schedule),
    vscode.languages.onDidChangeDiagnostics(schedule),
    vscode.workspace.onDidChangeConfiguration(event => { if (event.affectsConfiguration('codepet')) schedule(); }),
    {dispose: () => { generation++; paused = true; if (timer) clearTimeout(timer); socket?.close();
      for (const controller of controllers) controller.abort(); }}
  );
}
