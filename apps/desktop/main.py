import argparse
import json
import signal
import sys
import time
from datetime import datetime
from urllib.parse import quote
from uuid import uuid4

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from apps.desktop.assistant import (
    HELP,
    WakeGate,
    addressed_text,
    launch_application,
    launch_generic,
    parse_command,
)
from apps.desktop.chat.transport import BackendClient
from apps.desktop.pet.hyprland import HyprlandPlacement
from apps.desktop.pet.widget import PetWindow
from apps.desktop.shortcuts import GlobalShortcutPortal
from apps.desktop.voice.input import PushToTalk
from apps.desktop.voice.tts import LocalSpeaker
from backend.app.core.config import Settings


class DragHandle(QLabel):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)


class MemoryDialog(QDialog):
    """Visual CRUD surface for the project's notes."""

    def __init__(self, parent, items, refresh, edit_item, delete_item):
        super().__init__(parent)
        self.setWindowTitle("Memória do projeto")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        self.items = QListWidget(self)
        self.populate(items)
        layout.addWidget(self.items, 1)
        actions = QHBoxLayout()
        edit = QPushButton("Editar")
        edit.clicked.connect(lambda: edit_item(self, self.items.currentItem()))
        remove = QPushButton("Excluir")
        remove.clicked.connect(lambda: delete_item(self, self.items.currentItem()))
        refresh_button = QPushButton("Atualizar")
        refresh_button.clicked.connect(refresh)
        actions.addWidget(edit)
        actions.addWidget(remove)
        actions.addWidget(refresh_button)
        actions.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)

    def populate(self, items):
        self.items.clear()
        for item in items:
            row = QListWidgetItem(f"{item['kind']}  ·  {item['content']}")
            row.setData(Qt.ItemDataRole.UserRole, item)
            self.items.addItem(row)


class VoiceSettingsDialog(QDialog):
    def __init__(self, parent, devices, selected_device, outputs, selected_output, speed, volume, silence, sensitivity, auto_send):
        super().__init__(parent)
        self.setWindowTitle("Configurações de áudio")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.microphone = QComboBox(self)
        self.microphone.addItem(f"Padrão · {devices[0][1] if devices else 'indisponível'}", "")
        default_id = devices[0][0] if devices else ""
        for device_id, label in devices:
            if device_id == default_id:
                continue
            self.microphone.addItem(label, device_id)
        selected = self.microphone.findData(selected_device)
        if selected >= 0:
            self.microphone.setCurrentIndex(selected)
        self.output = QComboBox(self)
        self.output.addItem(f"Padrão do sistema · {outputs[0][1] if outputs else 'indisponível'}", "")
        for device_id, label in outputs:
            if device_id == (outputs[0][0] if outputs else ""):
                continue
            self.output.addItem(label, device_id)
        output_index = self.output.findData(selected_output)
        if output_index >= 0:
            self.output.setCurrentIndex(output_index)
        self.speed = QComboBox(self)
        for value in (110, 130, 155, 175, 200):
            self.speed.addItem(f"{value} palavras/min", value)
        self.speed.setCurrentIndex(max(0, self.speed.findData(speed)))
        self.volume = QComboBox(self)
        for value in (50, 75, 100, 125, 150, 175, 200):
            self.volume.addItem(f"{value}%", value)
        self.volume.setCurrentIndex(max(0, self.volume.findData(volume)))
        self.silence = QComboBox(self)
        for value in (0.7, 1.1, 1.5, 2.0):
            self.silence.addItem(f"{value:g} s", value)
        silence_index = self.silence.findData(silence)
        self.silence.setCurrentIndex(max(0, silence_index))
        self.sensitivity = QComboBox(self)
        for value, label in ((250, "Alta"), (420, "Normal"), (650, "Baixa"), (900, "Muito baixa")):
            self.sensitivity.addItem(label, value)
        self.sensitivity.setCurrentIndex(max(0, self.sensitivity.findData(sensitivity)))
        self.auto_send = QCheckBox("Enviar automaticamente após a fala", self)
        self.auto_send.setChecked(auto_send)
        form.addRow("Microfone", self.microphone)
        form.addRow("Saída da voz do Lume", self.output)
        form.addRow("Velocidade da voz", self.speed)
        form.addRow("Volume da voz", self.volume)
        form.addRow("Detectar pausa após", self.silence)
        form.addRow("Sensibilidade do microfone", self.sensitivity)
        form.addRow("Relay", self.auto_send)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class FocusDashboardDialog(QDialog):
    def __init__(self, parent, progress, history):
        super().__init__(parent)
        self.setWindowTitle("Painel de progresso")
        self.resize(560, 440)
        layout = QVBoxLayout(self)
        stats = progress.get("focus", {})
        layout.addWidget(QLabel(
            f"{stats.get('sessions', 0)} sessões concluídas  ·  "
            f"{stats.get('minutes', 0)} minutos focados  ·  "
            f"{stats.get('today_sessions', 0)} hoje  ·  "
            f"{len(progress.get('exercises_due', []))} exercícios para revisar"
        ))
        first_token = progress.get("metrics", {}).get("first_token_latency_ms", {})
        if first_token:
            layout.addWidget(QLabel(
                f"Primeiro token: média {first_token.get('average', 0) / 1000:.1f}s · "
                f"última {first_token.get('last', 0) / 1000:.1f}s"
            ))
        active = progress.get("active_focus", {})
        if active.get("status") in {"running", "paused", "break"}:
            layout.addWidget(QLabel(f"Sessão atual: {active.get('goal', 'sem meta')} · {active.get('status')}"))
        layout.addWidget(QLabel(f"Última meta: {stats.get('last_goal') or 'nenhuma'}"))
        self.history = QListWidget(self)
        for item in history:
            started = item.get("started", "")[:16].replace("T", " ")
            self.history.addItem(f"{started}  ·  {item.get('focus_minutes', 0)} min  ·  {item.get('goal', '')}")
        if not history:
            self.history.addItem("Ainda não há sessões registradas.")
        layout.addWidget(self.history, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)


class ChatWindow(QWidget):
    def __init__(self, client: BackendClient, settings: Settings):
        super().__init__()
        self.client, self.settings = client, settings
        self.preferences = QSettings("CodePet", "Lume")
        self.session = str(uuid4())
        self.busy = False
        self.paused = False
        self.wake_gate = WakeGate()
        self._shutting_down = False
        self.answer_parts: list[str] = []
        self.exercise_workflow = "idle"
        self.focus_state: dict = {"status": "idle"}
        self.focus_deadline = 0.0
        self.focus_timer = QTimer(self)
        self.focus_timer.setInterval(1000)
        self.focus_timer.timeout.connect(self.update_focus_clock)
        self.focus_timer.start()
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.focus_reminder)
        self.speaker = LocalSpeaker(self)
        self.voice_input = PushToTalk(self)
        self.setWindowTitle("CodePet AI · Lume")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(720, 700)
        self.setMinimumSize(560, 540)
        self.setStyleSheet("""
            QWidget { color: #edf5ff; font-family: "Noto Sans", "Inter", sans-serif; }
            QFrame#chatPanel { background: rgba(9, 15, 27, 236); border: 1px solid rgba(150, 190, 235, 115); border-radius: 22px; }
            QFrame#header { background: rgba(22, 34, 55, 150); border: 1px solid rgba(130, 175, 225, 70); border-radius: 16px; }
            QFrame#brandMark { background: #e98a55; border: 3px solid #ffc978; border-radius: 16px; }
            QLabel#brandGlyph { color: #182438; font-size: 20px; font-weight: 800; background: transparent; }
            QLabel#eyebrow { color: #9eb9d8; font-size: 10px; font-weight: 700; letter-spacing: 1px; background: transparent; }
            QLabel#title { color: #ffffff; font-size: 22px; font-weight: 800; background: transparent; }
            QLabel#subtitle { color: #adc2da; font-size: 11px; background: transparent; }
            QFrame#statusChip { background: rgba(13, 27, 42, 210); border: 1px solid rgba(104, 191, 190, 105); border-radius: 11px; }
            QLabel#statusDot { color: #72dbd4; font-size: 13px; background: transparent; }
            QLabel#status { color: #c8f5ef; font-size: 11px; background: transparent; }
            QFrame#contextBar { background: rgba(17, 28, 45, 170); border: 1px solid rgba(135, 173, 215, 65); border-radius: 16px; }
            QLabel#fieldLabel { color: #89a6c6; font-size: 10px; font-weight: 700; background: transparent; }
            QComboBox { color: #f5f9ff; background: rgba(29, 46, 70, 225); border: 1px solid rgba(166, 202, 239, 105); border-radius: 9px; padding: 8px 30px 8px 10px; min-height: 18px; }
            QComboBox:hover { border-color: #72dbd4; background: rgba(39, 61, 89, 235); }
            QComboBox::drop-down { width: 25px; border: 0px; }
            QComboBox QAbstractItemView { color: #ffffff; background: #17263d; border: 1px solid #5d83ad; selection-background-color: #356596; padding: 5px; }
            QCheckBox { color: #c5d5e8; spacing: 8px; background: transparent; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 5px; border: 1px solid #6f8eaf; background: rgba(12, 22, 37, 180); }
            QCheckBox::indicator:hover { border-color: #72dbd4; }
            QCheckBox::indicator:checked { border-color: #72dbd4; background: #2d8d91; }
            QFrame#historyPanel { background: rgba(6, 12, 22, 185); border: 1px solid rgba(139, 181, 225, 75); border-radius: 16px; }
            QLabel#sectionTitle { color: #dceaff; font-size: 12px; font-weight: 700; background: transparent; }
            QLabel#sectionHint { color: #7794b6; font-size: 10px; background: transparent; }
            QTextEdit#history { color: #f8fbff; background: transparent; border: 0px; padding: 8px 12px 12px 12px; selection-background-color: #356596; font-size: 13px; line-height: 1.25; }
            QFrame#composer { background: rgba(18, 32, 51, 230); border: 1px solid rgba(176, 211, 241, 120); border-radius: 15px; }
            QLineEdit#prompt { color: #ffffff; background: transparent; border: 0px; padding: 11px 12px; selection-background-color: #356596; font-size: 13px; }
            QLineEdit#prompt::placeholder { color: #87a0bd; }
            QLineEdit { color: #edf5ff; background: #1d2e46; border: 1px solid #6f8eaf; border-radius: 6px; padding: 6px; }
            QProgressBar { background: #14243a; border: 1px solid #6f8eaf; border-radius: 4px; max-height: 12px; }
            QProgressBar::chunk { background: #72dbd4; }
            QMenu { background: #17263d; color: #edf5ff; border: 1px solid #6f8eaf; padding: 5px; }
            QMenu::item { padding: 8px 16px; }
            QMenu::item:selected { background: #356596; }
            QPushButton { color: #eff7ff; background: rgba(31, 51, 76, 225); border: 1px solid rgba(155, 194, 232, 100); border-radius: 9px; padding: 8px 12px; min-height: 18px; }
            QPushButton:hover { background: rgba(54, 83, 117, 240); border-color: #72dbd4; }
            QPushButton:pressed { background: rgba(27, 72, 86, 245); padding-top: 9px; }
            QPushButton:disabled { color: #6d8199; background: rgba(26, 37, 52, 145); border-color: rgba(100, 125, 150, 55); }
            QPushButton#sendButton { color: #112537; background: #72dbd4; border: 0px; border-radius: 10px; font-weight: 800; padding: 9px 18px; }
            QPushButton#sendButton:hover { background: #9bf0e4; }
            QPushButton#sendButton:pressed { background: #4fb8b4; }
            QPushButton#windowButton, QPushButton#closeButton { background: transparent; border: 0px; color: #a9c2dc; font-size: 18px; min-width: 30px; min-height: 30px; padding: 0px; }
            QPushButton#windowButton:hover { background: rgba(128, 172, 220, 65); color: #ffffff; }
            QPushButton#closeButton:hover { background: #ad5962; color: #ffffff; }
            QFrame#utilityBar { background: transparent; border: 0px; }
            QScrollBar { background: transparent; width: 10px; margin: 4px 1px 4px 0px; }
            QScrollBar::handle { background: rgba(143, 184, 225, 125); border-radius: 5px; min-height: 28px; }
            QScrollBar::handle:hover { background: #72dbd4; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)
        panel = QFrame(self)
        panel.setObjectName("chatPanel")
        outer.addWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)

        header_panel = QFrame(panel)
        header_panel.setObjectName("header")
        header_layout = QHBoxLayout(header_panel)
        header_layout.setContentsMargins(12, 10, 10, 10)
        header_layout.setSpacing(11)
        mark = QFrame(header_panel)
        mark.setObjectName("brandMark")
        mark.setFixedSize(48, 48)
        mark_layout = QVBoxLayout(mark)
        mark_layout.setContentsMargins(0, 0, 0, 0)
        glyph = QLabel("✦", mark)
        glyph.setObjectName("brandGlyph")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark_layout.addWidget(glyph)
        header_layout.addWidget(mark)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(1)
        eyebrow = QLabel("ASSISTENTE LOCAL  •  CODEPET AI", header_panel)
        eyebrow.setObjectName("eyebrow")
        title_stack.addWidget(eyebrow)
        title = DragHandle("Lume", header_panel)
        title.setObjectName("title")
        title.setCursor(Qt.CursorShape.SizeAllCursor)
        title_stack.addWidget(title)
        subtitle = QLabel("Seu companheiro para entender, criar e depurar código.", header_panel)
        subtitle.setObjectName("subtitle")
        title_stack.addWidget(subtitle)
        header_layout.addLayout(title_stack, 1)
        status_chip = QFrame(header_panel)
        status_chip.setObjectName("statusChip")
        status_layout = QHBoxLayout(status_chip)
        status_layout.setContentsMargins(10, 5, 10, 5)
        status_layout.setSpacing(5)
        self.status_dot = QLabel("●", status_chip)
        self.status_dot.setObjectName("statusDot")
        self.status = QLabel("Conectando…", status_chip)
        self.status.setObjectName("status")
        status_layout.addWidget(self.status_dot)
        status_layout.addWidget(self.status)
        header_layout.addWidget(status_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        minimize = QPushButton("−", header_panel)
        minimize.setObjectName("windowButton")
        minimize.setToolTip("Minimizar chat")
        minimize.clicked.connect(self.showMinimized)
        header_layout.addWidget(minimize)
        close = QPushButton("×", header_panel)
        close.setObjectName("closeButton")
        close.setToolTip("Fechar chat")
        close.clicked.connect(self.hide)
        header_layout.addWidget(close)
        layout.addWidget(header_panel)

        context_bar = QFrame(panel)
        context_bar.setObjectName("contextBar")
        context_layout = QGridLayout(context_bar)
        context_layout.setContentsMargins(12, 10, 12, 10)
        context_layout.setHorizontalSpacing(8)
        context_layout.setVerticalSpacing(6)
        self.project = QComboBox()
        self.project.addItems(list(settings.projects))
        self.mode = QComboBox()
        self.mode.addItems(["tutor", "copilot", "silent"])
        self.mode.addItem("anti-procrastinação", "focus")
        self.mode.addItem("assistente · Lume", "assistant")
        self.skill = QComboBox()
        self.skill.addItem("Skills automáticas", "auto")
        self.skill.addItem("Sem skill", None)
        self.skill.setToolTip("Ponytail, Caveman e Graphify ativos por padrão")
        self.context = QCheckBox("Usar contexto autorizado do editor")
        self.voice = QCheckBox("Voz")
        self.voice.setChecked(self.speaker.available)
        self.voice.setEnabled(self.speaker.available)
        self.voice.setToolTip("Voz local em português (espeak-ng), reproduzida após cada resposta")
        for column, (caption, widget) in enumerate(
            (("PROJETO", self.project), ("MODO", self.mode), ("SKILL", self.skill))
        ):
            field = QFrame(context_bar)
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(3)
            label = QLabel(caption, field)
            label.setObjectName("fieldLabel")
            field_layout.addWidget(label)
            field_layout.addWidget(widget)
            context_layout.addWidget(field, 0, column)
        context_layout.addWidget(self.context, 1, 0, 1, 2)
        context_layout.addWidget(self.voice, 1, 2)
        layout.addWidget(context_bar)

        focus_bar = QFrame(panel)
        focus_bar.setObjectName("contextBar")
        focus_layout = QHBoxLayout(focus_bar)
        focus_layout.setContentsMargins(12, 8, 12, 8)
        focus_layout.setSpacing(7)
        self.focus_goal = QLineEdit(focus_bar)
        self.focus_goal.setPlaceholderText("Meta pequena: o que você vai fazer agora?")
        self.focus_goal.setToolTip("Uma tarefa concreta para a sessão, de preferência em uma frase")
        focus_layout.addWidget(self.focus_goal, 1)
        self.focus_length = QComboBox(focus_bar)
        for minutes in (15, 25, 50):
            self.focus_length.addItem(f"{minutes} min", minutes)
        self.focus_length.setCurrentIndex(1)
        self.focus_length.setToolTip("Duração da sessão de foco")
        focus_layout.addWidget(self.focus_length)
        self.focus_action = QPushButton("Começar foco", focus_bar)
        self.focus_action.clicked.connect(self.focus_start_or_resume)
        focus_layout.addWidget(self.focus_action)
        self.focus_pause = QPushButton("Pausar", focus_bar)
        self.focus_pause.clicked.connect(self.focus_pause_or_complete)
        self.focus_pause.setEnabled(False)
        focus_layout.addWidget(self.focus_pause)
        self.focus_status = QLabel("Anti-procrastinação: pronto", focus_bar)
        self.focus_status.setObjectName("sectionHint")
        self.focus_status.setMinimumWidth(165)
        focus_layout.addWidget(self.focus_status)
        layout.addWidget(focus_bar)

        history_panel = QFrame(panel)
        history_panel.setObjectName("historyPanel")
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(10, 8, 10, 8)
        history_layout.setSpacing(3)
        history_heading = QHBoxLayout()
        section_title = QLabel("Conversa", history_panel)
        section_title.setObjectName("sectionTitle")
        section_hint = QLabel("respostas em streaming", history_panel)
        section_hint.setObjectName("sectionHint")
        history_heading.addWidget(section_title)
        history_heading.addWidget(section_hint)
        history_heading.addStretch(1)
        history_layout.addLayout(history_heading)
        self.history = QTextEdit()
        self.history.setObjectName("history")
        self.history.setReadOnly(True)
        self.history.setAcceptRichText(False)
        self.history.setPlaceholderText("Quando você perguntar, a conversa aparecerá aqui.")
        self.history.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        history_layout.addWidget(self.history, 1)
        layout.addWidget(history_panel, 1)

        composer = QFrame(panel)
        composer.setObjectName("composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(5, 5, 5, 5)
        composer_layout.setSpacing(5)
        self.prompt = QLineEdit(composer)
        self.prompt.setObjectName("prompt")
        self.prompt.setPlaceholderText("O que você está tentando entender?")
        self.prompt.returnPressed.connect(self.ask)
        composer_layout.addWidget(self.prompt, 1)
        self.talk_button = QPushButton("Segure para falar", composer)
        self.talk_button.setEnabled(self.voice_input.available)
        self.talk_button.setToolTip(
            "Entrada local opcional: requer um microfone e o executável whisper."
        )
        self.talk_button.pressed.connect(self.voice_input.start)
        self.talk_button.released.connect(self.voice_input.stop)
        composer_layout.addWidget(self.talk_button)
        self.voice_level = QProgressBar(composer)
        self.voice_level.setRange(0, 100)
        self.voice_level.setTextVisible(False)
        self.voice_level.setFixedWidth(58)
        self.voice_level.setToolTip("Nível do microfone")
        composer_layout.addWidget(self.voice_level)
        self.transcript_hint = QLabel("", composer)
        self.transcript_hint.setObjectName("sectionHint")
        composer_layout.addWidget(self.transcript_hint)
        self.voice_relay = QCheckBox("Relay de voz", composer)
        self.voice_relay.setToolTip("Conversa mãos-livres: ouve, envia e fala a resposta; só grava fora da reprodução.")
        self.voice_relay.setEnabled(self.voice_input.available and self.speaker.available)
        composer_layout.addWidget(self.voice_relay)
        self.stop_speech_button = QPushButton("Parar voz", composer)
        self.stop_speech_button.setVisible(False)
        self.stop_speech_button.clicked.connect(self.speaker.stop)
        composer_layout.addWidget(self.stop_speech_button)
        send_button = QPushButton("Enviar  ↵", composer)
        send_button.setObjectName("sendButton")
        send_button.setMinimumWidth(105)
        send_button.clicked.connect(self.ask)
        composer_layout.addWidget(send_button)
        layout.addWidget(composer)

        assistant_bar = QHBoxLayout()
        self.wake_mode = QCheckBox('Ouvir “Lume”')
        self.wake_mode.setToolTip(
            'Ativa o microfone nesta sessão. Diga “Lume” e seu pedido. '
            'Áudio é transcrito localmente; perguntas seguem o provider escolhido.'
        )
        self.wake_mode.setEnabled(self.voice_input.available and self.speaker.available)
        self.wake_mode.toggled.connect(self.toggle_wake_mode)
        assistant_bar.addWidget(self.wake_mode)
        assistant_bar.addWidget(QLabel("Modelo:"))
        self.provider_choice = QComboBox()
        self.provider_choice.addItem("DeepHat · local", "ollama")
        self.provider_choice.addItem("Codex · online", "codex")
        self.provider_choice.setToolTip("A escolha vale para as próximas perguntas. Codex envia a conversa e o contexto autorizado à conta online.")
        assistant_bar.addWidget(self.provider_choice)
        assistant_help = QPushButton("Comandos do Lume")
        assistant_help.clicked.connect(lambda: QMessageBox.information(self, "Assistente Lume", HELP))
        assistant_bar.addWidget(assistant_help)
        assistant_bar.addStretch(1)
        layout.addLayout(assistant_bar)

        primary_actions = QHBoxLayout()
        primary_actions.setSpacing(6)
        self.pause_button = QPushButton("Pausar observação")
        self.pause_button.clicked.connect(self.pause)
        primary_actions.addWidget(self.pause_button)
        more_actions = QPushButton("Mais ações")
        more_menu = QMenu(more_actions)
        more_actions.setMenu(more_menu)
        for label, callback in [
            ("Etapas", self.edit_focus_steps),
            ("Me distraí", self.gentle_recovery),
            ("Histórico de foco", self.show_focus_history),
            ("Revisar foco", self.review_focus),
            ("Lembrete", self.configure_reminder),
            ("Áudio", self.configure_voice),
            ("Cancelar", self.cancel),
            ("Nova conversa", self.new_session),
            ("Reconectar", client.connect_backend),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            if label in {"Áudio", "Cancelar"}:
                primary_actions.addWidget(button)
            else:
                more_menu.addAction(label, callback)
                button.deleteLater()
        primary_actions.addWidget(more_actions)
        layout.addLayout(primary_actions)

        secondary_actions = QHBoxLayout()
        secondary_actions.setSpacing(6)
        learning_actions = QPushButton("Aprender")
        learning_menu = QMenu(learning_actions)
        learning_actions.setMenu(learning_menu)
        for label, callback in [
            ("Memória", self.memory),
            ("Guardar nota", self.remember),
            ("Próximo passo", lambda: self.quick_prompt("Qual é o menor próximo passo concreto para esta tarefa?")),
            ("Criar exercício", lambda: self.quick_prompt("Crie um exercício curto sobre o assunto atual e espere minha resposta.")),
            ("Exercício simples de programação", self.start_programming_exercise),
            ("Exercícios", self.exercises),
            ("Resumir", lambda: self.quick_prompt("Resuma o que aprendemos e indique uma ação para praticar.")),
            ("Progresso", self.learning_progress),
            ("Executar testes", self.tests),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            if label in {"Memória", "Guardar nota", "Próximo passo"}:
                secondary_actions.addWidget(button)
            else:
                learning_menu.addAction(label, callback)
                button.deleteLater()
        secondary_actions.addWidget(learning_actions)
        layout.addLayout(secondary_actions)
        self.voice.toggled.connect(self.on_voice_toggled)
        self.voice_input.failure.connect(self.on_voice_failure)
        self.voice_input.text_ready.connect(self.on_voice_transcript)
        self.voice_input.level_changed.connect(self.voice_level.setValue)
        self.voice_input.recording_changed.connect(self.on_recording_changed)
        self.speaker.speech_finished.connect(self.resume_voice_relay)
        self.speaker.speech_started.connect(lambda: self.stop_speech_button.setVisible(True))
        self.speaker.speech_finished.connect(lambda: self.stop_speech_button.setVisible(False))
        self.voice_relay.toggled.connect(self.toggle_voice_relay)
        client.event.connect(self.handle_backend_event)
        client.failure.connect(self.failure)
        client.ready.connect(self.on_ready)
        self.project.currentTextChanged.connect(self.load_focus)
        self.project.currentTextChanged.connect(lambda: self.save_preferences())
        self.mode.currentIndexChanged.connect(lambda: self.save_preferences())
        self.context.toggled.connect(lambda: self.save_preferences())
        self.focus_length.currentIndexChanged.connect(lambda: self.save_preferences())
        self.focus_goal.textChanged.connect(lambda: self.save_preferences())
        self.load_preferences()
        self.provider_choice.currentIndexChanged.connect(lambda: self.save_preferences())
        reminder = self.preferences.value("reminder_minutes", 0, type=int)
        if reminder in (15, 25, 50):
            self.reminder_timer.start(reminder * 60_000)
        self.shortcut_chat = QShortcut(QKeySequence("Ctrl+Shift+Space"), self)
        self.shortcut_chat.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_chat.activated.connect(self.toggle_chat)
        self.shortcut_voice = QShortcut(QKeySequence("Ctrl+Shift+V"), self)
        self.shortcut_voice.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_voice.activated.connect(self.toggle_relay_shortcut)
        self.global_shortcuts = GlobalShortcutPortal(self.on_global_shortcut, self)
        if not self.global_shortcuts.start():
            self.set_status("Portal de atalhos globais indisponível", "paused")

    def on_ready(self):
        if self.provider_choice.currentData() == "codex":
            source = "Codex CLI · online"
        else:
            source = "DeepHat · local"
        capture = "captura opt-in" if self.settings.screen_capture else "captura desligada"
        self.set_status(f"Conectado · {source} · {capture}", "ready")
        self.client.rest("GET", "/v1/skills", None, self.load_skills)
        self.load_focus()

    def mode_value(self) -> str:
        return self.mode.currentData() or self.mode.currentText()

    def load_preferences(self):
        source = self.preferences.value("chat_provider", "ollama")
        self.provider_choice.setCurrentIndex(max(0, self.provider_choice.findData(source)))
        project = self.preferences.value("project", "")
        project_index = self.project.findText(project)
        if project_index >= 0:
            self.project.setCurrentIndex(project_index)
        mode = self.preferences.value("mode", "tutor")
        mode_index = self.mode.findData(mode)
        if mode_index < 0:
            mode_index = self.mode.findText(mode)
        if mode_index >= 0:
            self.mode.setCurrentIndex(mode_index)
        if self.preferences.contains("voice"):
            self.voice.setChecked(self.preferences.value("voice", type=bool))
        self.context.setChecked(self.preferences.value("context", False, type=bool))
        minutes = self.preferences.value("focus_minutes", 25, type=int)
        length_index = self.focus_length.findData(minutes)
        if length_index >= 0:
            self.focus_length.setCurrentIndex(length_index)
        self.focus_goal.setText(self.preferences.value("focus_goal", ""))
        self.voice_input.device_name = self.preferences.value("voice_device", "")
        self.voice_input.silence_seconds = self.preferences.value("voice_silence", 1.1, type=float)
        self.voice_input.sensitivity = self.preferences.value("voice_sensitivity", 420, type=int)
        self.speaker.speed = self.preferences.value("voice_speed", 155, type=int)
        self.speaker.volume = self.preferences.value("voice_volume", 100, type=int)
        self.speaker.output_device = self.preferences.value("voice_output", "")
        if not self.speaker.output_device:
            self.speaker.output_device = self.speaker.recommended_output_device()

    def save_preferences(self):
        self.preferences.setValue("chat_provider", self.provider_choice.currentData())
        self.preferences.setValue("project", self.project.currentText())
        self.preferences.setValue("mode", self.mode_value())
        self.preferences.setValue("voice", self.voice.isChecked())
        self.preferences.setValue("context", self.context.isChecked())
        self.preferences.setValue("focus_minutes", self.focus_length.currentData())
        self.preferences.setValue("focus_goal", self.focus_goal.text())
        self.preferences.sync()

    def load_focus(self, _project: str = ""):
        if not self.client.authenticated:
            return
        path = "/v1/focus/" + quote(self.project.currentText(), safe="")
        self.client.rest("GET", path, None, self.set_focus_state)

    def set_focus_state(self, data: dict):
        self.focus_state = data
        remaining = int(data.get("remaining_seconds", 0))
        self.focus_deadline = time.monotonic() + remaining if data.get("status") in {"running", "break"} else 0
        self.update_focus_clock()

    def update_focus_clock(self):
        status = self.focus_state.get("status", "idle")
        if status in {"running", "break"} and self.focus_deadline:
            remaining = max(0, int(self.focus_deadline - time.monotonic() + 0.999))
            if remaining == 0:
                self.load_focus()
            self.focus_state["remaining_seconds"] = remaining
        remaining = int(self.focus_state.get("remaining_seconds", 0))
        minutes, seconds = divmod(remaining, 60)
        if status == "running":
            self.focus_status.setText(f"Foco ativo · {minutes:02d}:{seconds:02d}")
            self.focus_action.setText("Retomar")
            self.focus_action.setEnabled(False)
            self.focus_pause.setText("Pausar")
            self.focus_pause.setEnabled(True)
        elif status == "paused":
            self.focus_status.setText(f"Foco pausado · {minutes:02d}:{seconds:02d}")
            self.focus_action.setText("Retomar")
            self.focus_action.setEnabled(True)
            self.focus_pause.setText("Concluir")
            self.focus_pause.setEnabled(True)
        elif status == "break":
            self.focus_status.setText(f"Pausa merecida · {minutes:02d}:{seconds:02d}")
            self.focus_action.setText("Começar outro")
            self.focus_action.setEnabled(False)
            self.focus_pause.setText("Concluir")
            self.focus_pause.setEnabled(True)
        elif status == "completed":
            self.focus_status.setText("Sessão concluída · boa")
            self.focus_action.setText("Começar foco")
            self.focus_action.setEnabled(True)
            self.focus_pause.setText("Concluir")
            self.focus_pause.setEnabled(False)
        else:
            self.focus_status.setText("Anti-procrastinação: pronto")
            self.focus_action.setText("Começar foco")
            self.focus_action.setEnabled(True)
            self.focus_pause.setEnabled(False)

    def focus_start_or_resume(self):
        status = self.focus_state.get("status")
        action = "resume" if status == "paused" else "start"
        goal = self.focus_goal.text().strip()
        if action == "start" and not goal:
            self.focus_goal.setFocus()
            self.set_status("Defina uma meta pequena para começar", "paused")
            return
        if action == "start":
            self.mode.setCurrentIndex(self.mode.findData("focus"))
        payload = {"action": action, "goal": goal, "focus_minutes": self.focus_length.currentData(), "break_minutes": 5}
        path = "/v1/focus/" + quote(self.project.currentText(), safe="")
        self.client.rest("POST", path, payload, self.focus_started)

    def focus_started(self, data: dict):
        self.set_focus_state(data)
        self.set_status("Foco ativo. Só o próximo passo.", "busy")

    def edit_focus_steps(self):
        goal = self.focus_goal.text().strip() or str(self.focus_state.get("goal", "")).strip()
        if not goal:
            self.set_status("Defina uma meta antes de criar etapas", "paused")
            return
        project = quote(self.project.currentText(), safe="")
        path = f"/v1/focus/{project}/steps?goal={quote(goal, safe='')}"

        def loaded(data):
            dialog = QDialog(self)
            dialog.setWindowTitle("Etapas da tarefa")
            layout = QVBoxLayout(dialog)
            items = QListWidget(dialog)
            for entry in data.get("steps", []):
                text = entry.get("text", "") if isinstance(entry, dict) else entry
                done = entry.get("done", False) if isinstance(entry, dict) else False
                row = QListWidgetItem(text)
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
                row.setCheckState(Qt.CheckState.Checked if done else Qt.CheckState.Unchecked)
                items.addItem(row)
            layout.addWidget(items)
            controls = QHBoxLayout()
            add = QPushButton("Adicionar etapa")
            remove = QPushButton("Remover selecionada")
            add.clicked.connect(lambda: self.add_focus_step(items))
            remove.clicked.connect(lambda: items.takeItem(items.currentRow()) if items.currentRow() >= 0 else None)
            controls.addWidget(add)
            controls.addWidget(remove)
            layout.addLayout(controls)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            steps = [{"text": items.item(index).text().strip(),
                      "done": items.item(index).checkState() == Qt.CheckState.Checked}
                     for index in range(items.count()) if items.item(index).text().strip()]
            self.client.rest("PUT", f"/v1/focus/{project}/steps", {"goal": goal, "steps": steps},
                             lambda _: self.set_status(f"{len(steps)} etapas salvas", "ready"))

        self.client.rest("GET", path, None, loaded)

    def add_focus_step(self, items):
        text, accepted = QInputDialog.getText(self, "Nova etapa", "O que você fará?")
        if accepted and text.strip() and items.count() < 20:
            row = QListWidgetItem(text.strip())
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
            row.setCheckState(Qt.CheckState.Unchecked)
            items.addItem(row)

    def show_focus_history(self):
        project = quote(self.project.currentText(), safe="")

        def show(data):
            lines = [f"{item['started'][:16].replace('T', ' ')} · {item['focus_minutes']} min · {item['goal']}"
                     for item in data.get("items", [])]
            QMessageBox.information(self, "Histórico de foco", "\n".join(lines) if lines else "Ainda não há sessões salvas.")

        self.client.rest("GET", f"/v1/focus/{project}/history", None, show)

    def review_focus(self):
        goal = self.focus_goal.text().strip() or str(self.focus_state.get("goal", "")).strip()
        if not goal:
            QMessageBox.information(self, "Revisar foco", "Comece uma sessão antes de registrar um resultado.")
            return
        outcome, accepted = QInputDialog.getMultiLineText(
            self, "Revisar foco", "O que você conseguiu nesta sessão?", ""
        )
        if not accepted or not outcome.strip():
            return
        next_step, accepted = QInputDialog.getText(self, "Próximo passo", "Qual é o próximo passo?", text="")
        if not accepted:
            return
        project = quote(self.project.currentText(), safe="")
        self.client.rest("POST", f"/v1/focus/{project}/review",
                         {"outcome": outcome.strip(), "next_step": next_step.strip()},
                         lambda _data: self.focus_status.setText("Resultado salvo · próximo passo registrado"))

    def gentle_recovery(self):
        goal = self.focus_goal.text().strip() or str(self.focus_state.get("goal", "")).strip()
        prompt = (f"Me distraí da meta: {goal}. Sem julgamento, me ajude a retomar com uma única ação pequena "
                  "que eu possa fazer nos próximos dois minutos.")
        self.mode.setCurrentIndex(self.mode.findData("focus"))
        self.prompt.setText(prompt)
        self.ask()

    def configure_reminder(self):
        current = self.preferences.value("reminder_minutes", 0, type=int)
        options = ["Desligado", "15 minutos", "25 minutos", "50 minutos"]
        values = [0, 15, 25, 50]
        index = values.index(current) if current in values else 0
        choice, accepted = QInputDialog.getItem(self, "Lembretes de foco", "Lembrar durante sessões ativas:", options, index, False)
        if accepted:
            minutes = values[options.index(choice)]
            self.preferences.setValue("reminder_minutes", minutes)
            self.reminder_timer.stop()
            if minutes:
                self.reminder_timer.start(minutes * 60_000)
            self.set_status("Lembretes ativados" if minutes else "Lembretes desligados", "ready")

    def configure_voice(self):
        devices = self.voice_input.input_devices()
        outputs = self.speaker.output_devices()
        dialog = VoiceSettingsDialog(
            self,
            devices,
            self.preferences.value("voice_device", ""),
            outputs,
            self.speaker.output_device,
            self.speaker.speed,
            self.speaker.volume,
            self.voice_input.silence_seconds,
            self.voice_input.sensitivity,
            self.preferences.value("voice_auto_send", False, type=bool),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.microphone.currentData()
        self.voice_input.device_name = selected or ""
        self.speaker.output_device = dialog.output.currentData() or ""
        self.speaker.speed = int(dialog.speed.currentData())
        self.speaker.volume = int(dialog.volume.currentData())
        self.voice_input.silence_seconds = float(dialog.silence.currentData())
        self.voice_input.sensitivity = int(dialog.sensitivity.currentData())
        self.preferences.setValue("voice_device", self.voice_input.device_name)
        self.preferences.setValue("voice_silence", self.voice_input.silence_seconds)
        self.preferences.setValue("voice_sensitivity", self.voice_input.sensitivity)
        self.preferences.setValue("voice_speed", self.speaker.speed)
        self.preferences.setValue("voice_volume", self.speaker.volume)
        self.preferences.setValue("voice_output", self.speaker.output_device)
        self.preferences.setValue("voice_auto_send", dialog.auto_send.isChecked())
        self.set_status("Configurações de áudio salvas", "ready")

    def focus_reminder(self):
        if (self.focus_state.get("status") == "running" and not self.busy
                and not self.paused and self.mode_value() != "silent"
                and not self.speaker.speaking and self.voice_input.process is None
                and not (self.voice_input.active and self.voice_input.last_voice_at)):
            goal = self.focus_state.get("goal", "sua tarefa")
            self.assistant_reply(f'Como está indo com “{goal}”? Faça só o próximo passo ou uma pausa.')

    def toggle_chat(self):
        self.show() if self.isHidden() else self.hide()

    def on_global_shortcut(self, action: str):
        if action == "registered":
            self.shortcut_chat.setEnabled(False)
            self.shortcut_voice.setEnabled(False)
            self.set_status("Atalhos globais ativos · Ctrl+Shift+Espaço / Ctrl+Shift+V", "ready")
            return
        if action == "unavailable":
            self.shortcut_chat.setEnabled(True)
            self.shortcut_voice.setEnabled(True)
            self.set_status("O portal não registrou atalhos; disponíveis com o app ativo", "paused")
            return
        if action == "toggle-chat":
            self.toggle_chat()
        elif action == "toggle-relay":
            self.toggle_relay_shortcut()

    def toggle_relay_shortcut(self):
        self.voice_relay.setChecked(not self.voice_relay.isChecked())

    def toggle_voice_relay(self, enabled: bool):
        if enabled:
            self.voice.setChecked(True)
            self.resume_voice_relay()
        else:
            self.wake_mode.setChecked(False)
            self.wake_gate.reset()
            self.voice_input.shutdown()
            self.set_status("Relay de voz desligado", "ready")

    def toggle_wake_mode(self, enabled: bool):
        self.wake_gate.reset()
        if enabled:
            self.mode.setCurrentIndex(self.mode.findData("assistant"))
            self.voice_relay.setChecked(True)
            if self.voice_relay.isChecked():
                self.set_status('Ouvindo localmente · diga “Lume” e seu pedido', "ready")
        else:
            self.voice_relay.setChecked(False)

    def on_voice_transcript(self, text: str):
        if self._shutting_down or self.busy:
            return
        if self.wake_mode.isChecked():
            text = self.wake_gate.accept(text)
            if text is None:
                self.transcript_hint.setText('Aguardando “Lume”…')
                QTimer.singleShot(250, self.resume_voice_relay)
                return
            if not text:
                self.transcript_hint.setText("Estou ouvindo. Pode falar seu pedido.")
                QTimer.singleShot(250, self.resume_voice_relay)
                return
        self.prompt.setText(text)
        self.transcript_hint.setText("Transcrição pronta — revise e envie")
        if self.wake_mode.isChecked() or (
            self.voice_relay.isChecked() and self.preferences.value("voice_auto_send", False, type=bool)
        ):
            self.ask()

    def on_recording_changed(self, recording: bool):
        self.transcript_hint.setText("Ouvindo…" if recording else "Transcrevendo…")

    def resume_voice_relay(self):
        if (not self._shutting_down and self.voice_relay.isChecked() and not self.busy
                and not self.speaker.speaking and not self.voice_input.active):
            if not self.voice_input.start():
                self.voice_relay.setChecked(False)

    def on_voice_failure(self, message: str):
        if message == "Nenhuma fala detectada." and self.voice_relay.isChecked():
            self.transcript_hint.setText('Aguardando “Lume”…' if self.wake_mode.isChecked() else "Aguardando fala…")
            QTimer.singleShot(250, self.resume_voice_relay)
            return
        fatal = any(
            marker in message.lower()
            for marker in (
                "falha ao acessar o microfone",
                "não consegui abrir o microfone",
                "pipewire encerrou a captura",
                "não consegui iniciar a transcrição local",
                "transcrição falhou",
            )
        )
        if fatal and self.voice_relay.isChecked():
            self.voice_relay.setChecked(False)
        self.set_status(message, "error")
        if self.voice_relay.isChecked() and not self.busy and not fatal:
            QTimer.singleShot(1200, self.resume_voice_relay)

    def focus_pause_or_complete(self):
        action = "pause" if self.focus_state.get("status") == "running" else "complete"
        path = "/v1/focus/" + quote(self.project.currentText(), safe="")
        self.client.rest("POST", path, {"action": action}, self.focus_finished_action)

    def focus_finished_action(self, data: dict):
        self.set_focus_state(data)
        if data.get("status") == "completed":
            self.set_status("Sessão concluída. Faça uma pausa.", "ready")

    def set_status(self, text: str, tone: str = "ready"):
        colors = {
            "ready": "#72dbd4",
            "busy": "#f6c85f",
            "paused": "#e7a96b",
            "error": "#ff7d83",
        }
        color = colors.get(tone, colors["ready"])
        self.status.setText(text)
        self.status_dot.setStyleSheet(f"color: {color};")

    def on_voice_toggled(self, enabled: bool):
        self.save_preferences()
        if not enabled:
            if self.voice_relay.isChecked():
                self.voice_relay.setChecked(False)
            self.speaker.stop()

    def load_skills(self, data: dict):
        selected = self.skill.currentData()
        self.skill.clear()
        self.skill.addItem("Skills automáticas", "auto")
        self.skill.addItem("Sem skill", None)
        for item in data.get("items", []):
            self.skill.addItem(item["name"], item["id"])
            self.skill.setItemData(
                self.skill.count() - 1, item["description"], Qt.ItemDataRole.ToolTipRole
            )
        for index in range(self.skill.count()):
            if self.skill.itemData(index) == selected:
                self.skill.setCurrentIndex(index)
                break

    def append(self, text: str):
        self.history.moveCursor(QTextCursor.MoveOperation.End)
        self.history.insertPlainText(text)
        self.history.ensureCursorVisible()

    def failure(self, message: str):
        self.busy = False
        if self.exercise_workflow == "grading":
            self.exercise_workflow = "answering"
        elif self.exercise_workflow == "generating":
            self.exercise_workflow = "idle"
        self.answer_parts.clear()
        self.speaker.stop()
        self.set_status(message, "error")
        if self.voice_relay.isChecked():
            QTimer.singleShot(1000, self.resume_voice_relay)

    def handle_backend_event(self, event: dict):
        kind = event["type"]
        if kind == "token":
            self.append(event["content"])
            self.answer_parts.append(event["content"])
        elif kind in {"done", "cancelled", "error"}:
            self.busy = False
            spoken = "".join(self.answer_parts)
            if kind == "done" and self.exercise_workflow == "generating":
                self.exercise_workflow = "answering"
                self.transcript_hint.setText("Mande sua solução; a Lumi vai revisar e dar uma dica.")
            elif kind == "done" and self.exercise_workflow == "grading":
                self.exercise_workflow = "idle"
            elif kind in {"cancelled", "error"}:
                if self.exercise_workflow == "grading":
                    self.exercise_workflow = "answering"
                elif self.exercise_workflow == "generating":
                    self.exercise_workflow = "idle"
            if kind == "done" and self.voice.isChecked() and spoken.strip():
                self.speaker.say(spoken)
                QTimer.singleShot(700, self.resume_voice_relay)
            elif kind == "done" and self.voice_relay.isChecked():
                QTimer.singleShot(250, self.resume_voice_relay)
            elif kind in {"cancelled", "error"} and self.voice_relay.isChecked():
                QTimer.singleShot(700, self.resume_voice_relay)
            self.answer_parts.clear()
            self.append(
                "\n" + (event.get("message", "Cancelado." if kind == "cancelled" else "")) + "\n"
            )
            self.set_status(
                "Observação pausada" if self.paused else "Pronto",
                "paused" if self.paused else "ready",
            )
        elif kind == "state":
            names = ", ".join(event.get("skills", []))
            source = "Codex" if event.get("provider") == "codex" else "DeepHat" if event.get("provider") == "ollama" else "modelo configurado"
            self.set_status(
                f"{source} · pensando com {names}…" if names else f"{source} · pensando…", "busy"
            )
        elif kind == "queued":
            self.set_status("Pensando… Cancelar permanece disponível.", "busy")

    def ask(self):
        if self.busy or not self.prompt.text().strip():
            return
        text = self.prompt.text().strip()
        if self.exercise_workflow == "answering":
            solution, accepted = QInputDialog.getMultiLineText(
                self, "Sua solução", "Cole ou escreva sua solução para a Lumi revisar:", text
            )
            if not accepted or not solution.strip():
                return
            text = solution.strip()
        if len(text) > 8000:
            self.failure("Pergunta limitada a 8000 caracteres")
            return
        addressed = addressed_text(text)
        command_text = addressed if addressed is not None else text
        command = parse_command(command_text)
        if command and command.action != "provider" and not (
            addressed is not None or self.mode_value() == "assistant" or self.wake_mode.isChecked()
        ):
            command = None
        if command is not None:
            self.voice_input.shutdown()
            self.prompt.clear()
            self.append("\nVocê: " + text + "\n")
            self.run_assistant_command(command)
            return
        if not self.client.authenticated:
            if self.exercise_workflow == "generating":
                self.exercise_workflow = "idle"
            elif self.exercise_workflow == "grading":
                self.exercise_workflow = "answering"
            self.set_status("Backend desconectado. Use Reconectar para conversar.", "error")
            QTimer.singleShot(700, self.resume_voice_relay)
            return
        self.busy = True
        self.voice_input.shutdown()
        self.transcript_hint.setText("")
        self.speaker.stop()
        self.answer_parts.clear()
        self.append("\nVocê: " + text + "\nLume: ")
        self.prompt.clear()
        outgoing_prompt = command_text or text
        if self.exercise_workflow == "answering":
            outgoing_prompt = (
                "Minha solução para o exercício de programação anterior é:\n"
                + text
                + "\nAvalie a solução com cuidado. Responda em português com: veredito (correta ou precisa de ajuste), "
                "um acerto e, se houver erro, uma dica mínima antes de revelar a solução. Não invente requisitos "
                "que não estavam no enunciado."
            )
            self.exercise_workflow = "grading"
        self.client.send(
            {
                "v": 1,
                "type": "chat",
                "request_id": str(uuid4()),
                "session": self.session,
                "project": self.project.currentText(),
                "prompt": outgoing_prompt,
                "mode": "exercise" if self.exercise_workflow in {"generating", "grading"} else self.mode_value(),
                "provider": self.provider_choice.currentData(),
                "skill": None if self.exercise_workflow in {"generating", "grading"} else self.skill.currentData(),
                "use_editor": False if self.exercise_workflow in {"generating", "grading"} else self.context.isChecked(),
            }
        )

    def assistant_reply(self, text: str):
        self.busy = False
        self.append("\nLume: " + text + "\n")
        self.set_status(text.splitlines()[0][:120], "ready")
        if self.voice.isChecked() and self.mode_value() != "silent":
            self.voice_input.shutdown()
            self.speaker.say(text)
        QTimer.singleShot(700, self.resume_voice_relay)

    def run_assistant_command(self, command):
        action = command.action
        project = self.project.currentText()
        path = quote(project, safe="")
        if action == "provider":
            self.provider_choice.setCurrentIndex(self.provider_choice.findData(command.value))
            name = "Codex online" if command.value == "codex" else "DeepHat local"
            self.assistant_reply(f"Selecionei {name} para as próximas perguntas.")
        elif action == "open":
            labels = {"browser": "navegador", "editor": "VS Code", "terminal": "terminal", "files": "pasta do projeto"}
            started = launch_application(command.value, self.settings.projects[project])
            self.assistant_reply(
                f"Pedi ao sistema para abrir {labels[command.value]}." if started
                else "Não consegui iniciar o aplicativo. Confira se ele está instalado."
            )
        elif action == "open_generic":
            started, display = launch_generic(command.value)
            self.assistant_reply(
                f"Pedi ao sistema para abrir {display}." if started
                else f"Não encontrei \"{command.value}\" instalado. Confira o nome ou instale o aplicativo."
            )
        elif action == "unsupported":
            self.assistant_reply("Não reconheci esse aplicativo. Tente o nome simples, como \"Discord\" ou \"Spotify\".")
        elif action == "help":
            self.assistant_reply(HELP)
        elif action == "time":
            self.assistant_reply(datetime.now().strftime("Agora são %H:%M."))
        elif action == "stop_listening":
            self.voice_relay.setChecked(False)
            self.assistant_reply("Microfone desligado. Para voltar, ative Ouvir Lume.")
        elif not self.client.authenticated:
            self.assistant_reply("Preciso do backend conectado para esse pedido. Use Reconectar.")
        elif action == "recover":
            self.gentle_recovery()
        elif action == "remember":
            if len(command.value) > 4000:
                self.assistant_reply("A nota precisa ter até 4000 caracteres.")
                return
            self.busy = True
            self.client.rest("POST", f"/v1/memory/{path}", {"kind": "topic", "content": command.value},
                             lambda _: self.assistant_reply("Nota guardada na memória deste projeto."))
        elif action == "search":
            if len(command.value) > 120:
                self.assistant_reply("Pesquise um trecho de até 120 caracteres.")
                return
            self.busy = True
            self.client.rest("POST", "/v1/tools", {"name": "search_project", "project": project, "query": command.value},
                             self.assistant_search_result)
        elif action == "focus_status":
            self.busy = True

            def show_focus(data):
                self.set_focus_state(data)
                self.assistant_reply(self.focus_status.text() + ". " + data.get("goal", ""))

            self.client.rest("GET", f"/v1/focus/{path}", None, show_focus)
        elif action.startswith("focus_"):
            verb = action.removeprefix("focus_")
            goal = command.value or self.focus_goal.text().strip()
            if verb == "start" and (not goal or len(goal) > 240 or not 1 <= command.minutes <= 120):
                self.assistant_reply("Diga uma meta de até 240 caracteres e um tempo de 1 a 120 minutos. Exemplo: iniciar foco de 25 minutos para estudar Python.")
                return
            self.busy = True

            def updated(data):
                self.set_focus_state(data)
                if verb == "start":
                    self.focus_goal.setText(goal)
                messages = {"start": f"Foco iniciado por {command.minutes} minutos. Sua meta: {goal}.",
                            "pause": "Foco pausado.", "resume": "Foco retomado. Um passo por vez.",
                            "complete": "Sessão concluída. Hora de uma pausa."}
                self.assistant_reply(messages[verb])

            self.client.rest("POST", f"/v1/focus/{path}",
                             {"action": verb, "goal": goal, "focus_minutes": command.minutes, "break_minutes": 5}, updated)

    def assistant_search_result(self, data):
        if data.get("status") != "ok":
            self.assistant_reply("Não consegui pesquisar o projeto agora.")
            return
        hits = data.get("hits", [])
        if not hits:
            self.assistant_reply("Não encontrei esse trecho na busca limitada do projeto.")
            return
        locations = "\n".join(f"{hit['path']}:{hit['line']} — {hit['text']}" for hit in hits[:10])
        self.assistant_reply(f"Encontrei {len(hits)} ocorrências na busca limitada. Veja os locais no chat.")
        self.append(locations + "\n")

    def cancel(self):
        self.speaker.stop()
        self.client.send({"v": 1, "type": "cancel"})

    def new_session(self):
        if self.busy:
            return
        self.session = str(uuid4())
        self.exercise_workflow = "idle"
        self.history.clear()
        self.speaker.stop()

    def pause(self):
        def done(data):
            self.paused = data["paused"]
            self.pause_button.setText("Retomar observação" if self.paused else "Pausar observação")
            self.set_status(
                "Observação pausada; contexto descartado"
                if self.paused
                else "Eventos do editor habilitados",
                "paused" if self.paused else "ready",
            )

        self.client.rest("POST", "/v1/observation", {"paused": not self.paused}, done)

    def remember(self):
        kind, ok = QInputDialog.getItem(
            self, "Memória", "Tipo", ["preference", "difficulty", "topic"], 0, False
        )
        if not ok:
            return
        text, ok = QInputDialog.getMultiLineText(self, "Memória", "O que guardar neste projeto?")
        if ok and text.strip():
            self.client.rest(
                "POST",
                "/v1/memory/" + quote(self.project.currentText(), safe=""),
                {"kind": kind, "content": text},
                lambda _: self.set_status("Memória salva", "ready"),
            )

    def memory(self):
        project = self.project.currentText()

        def show(data):
            dialog = MemoryDialog(
                self,
                data["items"],
                lambda: self.memory_refresh(dialog),
                self.edit_memory_item,
                self.delete_memory_item,
            )
            dialog.exec()

        self.client.rest(
            "GET",
            "/v1/memory/" + quote(project, safe=""),
            None,
            show,
        )

    def memory_refresh(self, dialog):
        self.client.rest(
            "GET",
            "/v1/memory/" + quote(self.project.currentText(), safe=""),
            None,
            lambda data: dialog.populate(data["items"]),
        )

    def edit_memory_item(self, dialog, item):
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        content, accepted = QInputDialog.getMultiLineText(
            self, "Editar memória", "Conteúdo", data["content"]
        )
        if not accepted or not content.strip():
            return
        project = quote(self.project.currentText(), safe="")
        self.client.rest(
            "PUT",
            f"/v1/memory/{project}/{data['id']}",
            {"kind": data["kind"], "content": content.strip()},
            lambda _: self.memory_refresh(dialog),
        )

    def delete_memory_item(self, dialog, item):
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        approved = QMessageBox.question(self, "Excluir memória", "Excluir esta anotação?")
        if approved != QMessageBox.StandardButton.Yes:
            return
        project = quote(self.project.currentText(), safe="")
        self.client.rest(
            "DELETE",
            f"/v1/memory/{project}/{data['id']}",
            None,
            lambda _: self.memory_refresh(dialog),
        )

    def quick_prompt(self, text: str):
        focus_index = self.mode.findData("focus")
        if focus_index >= 0:
            self.mode.setCurrentIndex(focus_index)
        self.prompt.setText(text)
        self.ask()

    def start_programming_exercise(self):
        if self.busy:
            return
        tutor_index = self.mode.findData("tutor")
        if tutor_index >= 0:
            self.mode.setCurrentIndex(tutor_index)
        self.exercise_workflow = "generating"
        self.prompt.setText(
            "Crie um único exercício bem simples para iniciante em Python. Use um enunciado curto, "
            "com objetivo claro e no máximo um exemplo de entrada e saída. Não mostre código de solução "
            "nem resposta. Termine pedindo que eu envie minha solução."
        )
        self.ask()

    def learning_progress(self):
        project = quote(self.project.currentText(), safe="")

        def show_dashboard(progress):
            self.client.rest(
                "GET", f"/v1/focus/{project}/history", None,
                lambda history: FocusDashboardDialog(self, progress, history.get("items", [])).exec(),
            )

        path = "/v1/learning/" + project
        self.client.rest(
            "GET",
            path,
            None,
            show_dashboard,
        )

    def exercises(self):
        project = quote(self.project.currentText(), safe="")
        action, ok = QInputDialog.getItem(
            self,
            "Exercícios",
            "Ação",
            ["Criar exercício", "Revisar próximo"],
            0,
            False,
        )
        if not ok:
            return
        if action == "Criar exercício":
            prompt, accepted = QInputDialog.getMultiLineText(
                self, "Novo exercício", "Pergunta ou tarefa"
            )
            if not accepted or not prompt.strip():
                return
            answer, accepted = QInputDialog.getMultiLineText(
                self, "Novo exercício", "Resposta esperada (opcional)"
            )
            if not accepted:
                return
            topic, accepted = QInputDialog.getText(self, "Novo exercício", "Tópico")
            if not accepted:
                return
            self.client.rest(
                "POST",
                f"/v1/exercises/{project}",
                {"prompt": prompt, "answer": answer, "topic": topic},
                lambda _: self.set_status("Exercício salvo", "ready"),
            )
            return

        def show(data):
            items = data.get("items", [])
            if not items:
                self.append("\nNenhum exercício vencido para revisar.\n")
                return
            item = items[0]
            self.append(f"\nRevisão: {item['prompt']}\n")
            rating, accepted = QInputDialog.getInt(
                self,
                "Revisão espaçada",
                "Nota de 0 (esqueci) a 5 (domino):",
                3,
                0,
                5,
            )
            if accepted:
                self.client.rest(
                    "POST",
                    f"/v1/exercises/{project}/{item['id']}/review",
                    {"rating": rating},
                    lambda _: self.set_status("Revisão registrada", "ready"),
                )

        self.client.rest("GET", f"/v1/exercises/{project}?due_only=true", None, show)

    def closeEvent(self, event):
        self.save_preferences()
        self.focus_timer.stop()
        super().closeEvent(event)

    def shutdown(self):
        self._shutting_down = True
        self.reminder_timer.stop()
        self.focus_timer.stop()
        self.voice_relay.blockSignals(True)
        self.voice_relay.setChecked(False)
        self.voice_relay.blockSignals(False)
        self.voice_input.shutdown()
        self.speaker.stop()
        self.global_shortcuts.stop()
        self.client.socket.blockSignals(True)
        self.client.socket.close()

    def tests(self):
        request = {"name": "run_project_tests", "project": self.project.currentText()}

        def result(data):
            if data.get("status") != "approval_required":
                self.append("\nTestes:\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n")
                return
            message = f"Diretório: {data['cwd']}\nComando: {' '.join(data['command'])}\n\nTestes executam código do projeto com suas permissões, inclusive acesso a arquivos e rede. Executar uma vez?"
            approved = (
                QMessageBox.question(
                    self,
                    "Aprovar execução",
                    message,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            )
            identity = data["approval_id"]

            def decided(_):
                if approved:
                    request["approval_id"] = identity
                    self.client.rest("POST", "/v1/tools", request, result)

            self.client.rest("POST", "/v1/approvals/" + identity, {"approved": approved}, decided)

        self.client.rest("POST", "/v1/tools", request, result)


def run():
    parser = argparse.ArgumentParser(description="Lume, assistente de desktop")
    parser.add_argument("--assistant", action="store_true", help="Abrir no modo assistente")
    parser.add_argument("--show-chat", action="store_true", help="Mostrar a conversa ao iniciar")
    args = parser.parse_args()
    application = QApplication(sys.argv)
    application.setApplicationName("codepet-ai")
    application.setDesktopFileName("codepet-ai")
    application.setOrganizationName("CodePet")
    application.setQuitOnLastWindowClosed(False)
    # Route terminal/service shutdown through Qt so audio and portal children close first.
    signal.signal(signal.SIGINT, lambda *_: QTimer.singleShot(0, application.quit))
    signal.signal(signal.SIGTERM, lambda *_: QTimer.singleShot(0, application.quit))
    settings = Settings()
    client = BackendClient(settings.token.get_secret_value())
    chat = ChatWindow(client, settings)
    if args.assistant:
        chat.mode.setCurrentIndex(chat.mode.findData("assistant"))
    if args.show_chat:
        chat.show()
    application.aboutToQuit.connect(chat.shutdown)
    pet = PetWindow()
    pet.open_chat.connect(chat.show)
    pet.quit_requested.connect(application.quit)
    chat.mode.currentTextChanged.connect(lambda mode: pet.set_spontaneous_enabled(mode != "silent"))
    client.event.connect(pet.react)
    client.failure.connect(lambda message: pet.react({"type": "error"}))
    chat.speaker.speech_started.connect(lambda: pet.react({"type": "token"}))
    chat.speaker.speech_finished.connect(lambda: pet.react({"type": "done"}))
    placement = HyprlandPlacement(pet)
    pet.show()
    placement.start()
    client.connect_backend()
    sys.exit(application.exec())


if __name__ == "__main__":
    run()
