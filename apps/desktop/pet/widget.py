import random

from PySide6.QtCore import QRect, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QRegion, QTransform
from PySide6.QtWidgets import QInputDialog, QMenu, QWidget

from apps.desktop.pet.sprite import SpriteAnimator
from apps.desktop.pet.state import PetMachine, PetState


class PetWindow(QWidget):
    open_chat = Signal()
    quit_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CodePet Lume")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.machine = PetMachine()
        self.preferences = QSettings("CodePet", "Lume")
        self.scale = self.preferences.value("pet_scale", 3.5, type=float)
        self.speed = self.preferences.value("pet_speed", 3, type=int)
        self.frame = 0
        self.x = 100
        self.direction = 1
        self.bubble = "Olá! Duplo clique para conversar."
        self.animator = SpriteAnimator()
        self.sheet = self.animator.frame(PetState.IDLE, 0)
        self.resize(360, 190)
        self.timer = QTimer(self)
        # Render at 30 fps for a steadier Wayland surface.  Logical pose
        # changes remain at 10 fps so greetings and activities keep their
        # intended duration instead of becoming three times faster.
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick_30fps)
        self.timer.start()
        self.render_subframe = 0
        self.idle_ticks = 0
        self.still_ticks = 0
        self.walk_ticks = 0
        self.total_ticks = 0
        self.next_greeting_tick = 30
        self.greeting_ticks = 0
        self.next_activity_tick = 75
        self.activity_ticks = 0
        self.activity_turn = 0
        self.spontaneous_enabled = True
        self.bubble_before_greeting = self.bubble
        self.bubble_before_activity = self.bubble
        self.refresh_mask()

    def tick_30fps(self):
        """Repaint at 30 fps while advancing the authored animation at 10 fps."""
        self.render_subframe = (self.render_subframe + 1) % 3
        if self.render_subframe == 0:
            self.tick()
        else:
            self.redraw_surface()

    def react(self, event: dict):
        kind = event.get("type", "")
        if kind in self.machine.EVENTS:
            if self.machine.state == PetState.WAVING:
                self.finish_greeting()
            elif self.machine.state in {PetState.TYPING, PetState.CASTING}:
                self.finish_activity()
        self.machine.handle(kind)
        self.idle_ticks = 0
        self.still_ticks = 0
        self.walk_ticks = 0
        if event.get("type") == "token":
            self.bubble = "Estou explicando no chat…"
        elif event.get("type") == "done":
            self.bubble = "Pronto. Vamos experimentar?"
        elif event.get("type") == "error":
            self.bubble = "Confira a conexão no chat."
        self.redraw_surface()

    def tick(self):
        if self.machine.paused:
            return
        self.frame = (self.frame + 1) % 32
        self.total_ticks += 1
        self.idle_ticks += 1
        if self.machine.state == PetState.WAVING:
            self.greeting_ticks += 1
            if self.greeting_ticks >= 12:
                self.finish_greeting()
        elif self.machine.state in {PetState.TYPING, PetState.CASTING}:
            self.activity_ticks += 1
            duration = 32 if self.machine.state == PetState.TYPING else 20
            if self.activity_ticks >= duration:
                self.finish_activity()
        elif (
            self.spontaneous_enabled
            and self.total_ticks >= self.next_greeting_tick
            and self.machine.state in {PetState.IDLE, PetState.WALKING}
        ):
            self.start_greeting()
        elif (
            self.spontaneous_enabled
            and self.total_ticks >= self.next_activity_tick
            and self.machine.state in {PetState.IDLE, PetState.WALKING}
        ):
            self.start_activity()
        if self.idle_ticks > 15 and self.machine.state in {
            PetState.HAPPY,
            PetState.CONFUSED,
            PetState.ERROR,
        }:
            self.machine.handle("idle")
        if self.machine.state == PetState.SLEEPING and self.idle_ticks > 220:
            self.machine.handle("idle")
            self.idle_ticks = 0
            self.still_ticks = 0
            self.frame = 0
        elif self.machine.state in {PetState.IDLE, PetState.WALKING, PetState.HAPPY}:
            if self.idle_ticks > 150:
                self.machine.handle("rest")
                self.walk_ticks = 0
                self.still_ticks = 0
            elif self.machine.state == PetState.WALKING:
                self.walk_ticks += 1
                self.x += self.direction * self.speed
                sprite_width, _ = self.sprite_size()
                if self.x <= 0 or self.x >= self.width() - sprite_width:
                    self.direction *= -1
                    self.x = max(0, min(self.x, self.width() - sprite_width))
                if self.walk_ticks >= 18:
                    self.machine.handle("idle")
                    self.walk_ticks = 0
                    self.still_ticks = 0
                    self.frame = 0
            elif self.machine.state == PetState.IDLE:
                self.still_ticks += 1
                if self.still_ticks >= 44:
                    self.machine.handle("walk")
                    self.still_ticks = 0
                    self.walk_ticks = 0
        self.redraw_surface()

    def start_greeting(self):
        self.machine.handle("greet")
        self.greeting_ticks = 0
        self.bubble_before_greeting = self.bubble
        self.bubble = "Oi!"
        self.next_greeting_tick = self.total_ticks + random.randint(210, 360)
        self.next_activity_tick = max(self.next_activity_tick, self.total_ticks + 60)

    def finish_greeting(self):
        self.machine.handle("idle")
        self.greeting_ticks = 0
        self.idle_ticks = 0
        self.still_ticks = 0
        self.frame = 0
        self.bubble = self.bubble_before_greeting

    def start_activity(self):
        event = "open_laptop" if self.activity_turn == 0 else "cast_spell"
        self.activity_turn = 1 - self.activity_turn
        self.machine.handle(event)
        self.activity_ticks = 0
        self.bubble_before_activity = self.bubble
        self.bubble = "Digitando..." if self.machine.state == PetState.TYPING else "Magia!"
        self.next_activity_tick = self.total_ticks + random.randint(150, 230)
        self.next_greeting_tick = max(self.next_greeting_tick, self.total_ticks + 80)

    def finish_activity(self):
        self.machine.handle("idle")
        self.activity_ticks = 0
        self.idle_ticks = 0
        self.still_ticks = 0
        self.frame = 0
        self.bubble = self.bubble_before_activity

    def set_spontaneous_enabled(self, enabled: bool):
        self.spontaneous_enabled = enabled
        if not enabled:
            if self.machine.state == PetState.WAVING:
                self.finish_greeting()
                self.redraw_surface()
            elif self.machine.state in {PetState.TYPING, PetState.CASTING}:
                self.finish_activity()
                self.redraw_surface()
        else:
            self.next_greeting_tick = max(self.next_greeting_tick, self.total_ticks + 30)
            self.next_activity_tick = max(self.next_activity_tick, self.total_ticks + 50)

    def set_greetings_enabled(self, enabled: bool):
        self.set_spontaneous_enabled(enabled)

    def redraw_surface(self):
        # A changing window mask clips Qt's backing-store damage on Wayland.
        # Repaint the whole translucent surface first, then restore the input mask.
        prop_offset = 0
        typing_pose = 2
        if self.machine.state in {PetState.TYPING, PetState.CASTING}:
            duration = 32 if self.machine.state == PetState.TYPING else 20
            prop_offset = max(
                0,
                8 - self.activity_ticks * 2,
                (self.activity_ticks - (duration - 4)) * 2,
            )
            if self.machine.state == PetState.TYPING:
                if self.activity_ticks < 3 or self.activity_ticks >= 29:
                    typing_pose = 0
                elif self.activity_ticks < 6 or self.activity_ticks >= 26:
                    typing_pose = 1
        self.sheet = self.animator.frame(
            self.machine.state,
            self.frame,
            blink=self.frame == 31,
            prop_offset=prop_offset,
            typing_pose=typing_pose,
            subframe=self.render_subframe,
        )
        self.clearMask()
        self.repaint()
        self.refresh_mask()

    def sprite_size(self) -> tuple[int, int]:
        width = round(self.scale * 17)
        return width, round(width * self.sheet.height() / self.sheet.width())

    def sprite_position(self) -> tuple[int, int]:
        _, height = self.sprite_size()
        # The logical walk step remains at 10 fps, but the 30 fps renderer
        # fills the space between steps so movement does not jump by several
        # pixels on each authored frame.
        x = self.x
        if self.machine.state == PetState.WALKING and not self.machine.paused:
            x += round(self.direction * self.speed * self.render_subframe / 3)
        y = self.height() - height
        if self.machine.state in {PetState.WALKING, PetState.TALKING}:
            y -= 2 if self.frame % 4 == 1 else 0
        elif self.machine.state == PetState.IDLE:
            y -= (0, 0, 1, 1, 2, 1, 0, 0)[self.frame % 8]
        elif self.machine.state in {PetState.HAPPY, PetState.WAVING}:
            y -= 5 if self.frame % 4 in {1, 2} else 0
        elif self.machine.state == PetState.ERROR:
            x += 3 if self.frame % 2 else -3
        return x, y

    def bubble_rect(self) -> QRect:
        sprite_width, _ = self.sprite_size()
        x, _ = self.sprite_position()
        text_width = QFontMetrics(self.font()).horizontalAdvance(self.bubble)
        width = min(self.width() - 8, max(110, text_width + 28))
        left = max(4, min(self.width() - width - 4, x + sprite_width // 2 - width // 2))
        return QRect(left, 4, width, 42)

    def refresh_mask(self):
        width, height = self.sprite_size()
        x, y = self.sprite_position()
        if self.machine.state == PetState.CONFUSED:
            sprite_region = QRegion(QRect(x - 5, y - 5, width + 10, height + 10))
        else:
            source = QRegion(self.sheet.mask())
            sprite_region = (
                QTransform()
                .scale(width / self.sheet.width(), height / self.sheet.height())
                .map(source)
                .translated(x, y)
            )
        if self.machine.state in {
            PetState.SLEEPING,
            PetState.THINKING,
            PetState.TALKING,
            PetState.HAPPY,
            PetState.ERROR,
            PetState.LISTENING,
        }:
            sprite_region |= QRegion(QRect(x + width - 8, y + 4, 38, 28))
        self.setMask(sprite_region | QRegion(self.bubble_rect()))

    def paintEvent(self, _):
        painter = QPainter(self)
        # Wayland may reuse the translucent surface between sprite positions.
        # Replace the whole previous frame before drawing the new one.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.setPen(Qt.GlobalColor.transparent)
        painter.setBrush(Qt.GlobalColor.white)
        bubble = self.bubble_rect()
        painter.drawRoundedRect(bubble, 10, 10)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(
            bubble.adjusted(8, 2, -8, -2),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.bubble,
        )
        width, height = self.sprite_size()
        state = self.machine.state
        x, y = self.sprite_position()
        if state == PetState.CONFUSED:
            painter.translate(x + width / 2, y + height / 2)
            painter.rotate(4 if self.frame % 2 else -4)
            painter.drawPixmap(QRect(-width // 2, -height // 2, width, height), self.sheet)
            painter.resetTransform()
        else:
            painter.drawPixmap(QRect(x, y, width, height), self.sheet)
        markers = {
            PetState.SLEEPING: "Z",
            PetState.THINKING: "…",
            PetState.TALKING: "· ·",
            PetState.HAPPY: "✦",
            PetState.CONFUSED: "?",
            PetState.ERROR: "!",
            PetState.LISTENING: "♫",
        }
        if state in markers:
            painter.setPen(QColor("#132C5C"))
            font = QFont()
            font.setBold(True)
            font.setPointSize(14)
            painter.setFont(font)
            painter.drawText(QRect(x + width - 8, y + 4, 38, 28), markers[state])

    def mouseDoubleClickEvent(self, _):
        self.open_chat.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("Conversar", self.open_chat.emit)
        menu.addAction(
            "Retomar animação" if self.machine.paused else "Pausar animação", self.toggle
        )
        menu.addAction("Tamanho", self.set_size)
        menu.addAction("Velocidade", self.set_speed)
        menu.addAction("Sair", self.quit_requested.emit)
        menu.exec(event.globalPos())

    def toggle(self):
        self.machine.paused = not self.machine.paused
        self.timer.stop() if self.machine.paused else self.timer.start()

    def set_size(self):
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Tamanho")
        dialog.setLabelText("Escala do pixel")
        dialog.setInputMode(QInputDialog.InputMode.DoubleInput)
        dialog.setDoubleRange(3.0, 8.0)
        dialog.setDoubleDecimals(1)
        dialog.setDoubleStep(0.5)
        dialog.setDoubleValue(self.scale)
        if dialog.exec():
            self.scale = dialog.doubleValue()
            self.preferences.setValue("pet_scale", self.scale)
            self.preferences.sync()
            self.x = min(self.x, self.width() - self.sprite_size()[0])
            self.redraw_surface()

    def set_speed(self):
        value, accepted = QInputDialog.getInt(
            self, "Velocidade", "Pixels por passo", self.speed, 1, 10
        )
        if accepted:
            self.speed = value
            self.preferences.setValue("pet_speed", self.speed)
            self.preferences.sync()

    def closeEvent(self, event):
        self.preferences.setValue("pet_scale", self.scale)
        self.preferences.setValue("pet_speed", self.speed)
        self.preferences.sync()
        super().closeEvent(event)
