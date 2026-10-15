import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from apps.desktop.pet.sprite import arm_paths, body_path
from apps.desktop.pet.state import PetState
from apps.desktop.pet.widget import PetWindow


@pytest.mark.desktop
def test_pet_render_and_animation_pause():
    app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    pet.show()
    pet.react({"type": "token"})
    app.processEvents()
    assert not pet.sheet.isNull()
    assert not pet.grab().isNull()
    pet.toggle()
    assert not pet.timer.isActive()
    pet.close()


@pytest.mark.desktop
def test_pet_renders_at_30fps_without_speeding_up_pose_timing():
    _app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    pet.set_spontaneous_enabled(False)

    assert pet.timer.interval() == 33
    assert pet.frame == 0
    pet.tick_30fps()
    pet.tick_30fps()
    assert pet.frame == 0
    pet.tick_30fps()
    assert pet.frame == 1
    pet.close()


@pytest.mark.desktop
def test_pet_walk_fills_position_between_logical_steps():
    _app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    pet.set_spontaneous_enabled(False)
    pet.machine.handle("walk")
    pet.render_subframe = 1
    assert pet.sprite_position()[0] == pet.x + round(pet.speed / 3)
    pet.render_subframe = 2
    assert pet.sprite_position()[0] == pet.x + round(2 * pet.speed / 3)
    pet.close()


@pytest.mark.desktop
def test_pet_walk_clears_previous_position():
    app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    pet.show()
    app.processEvents()
    assert pet.grab().toImage().pixelColor(130, 165).alpha() > 0

    pet.speed = 30
    pet.machine.handle("walk")
    for _ in range(5):
        pet.tick()
        app.processEvents()

    frame = pet.grab().toImage()
    assert pet.x == 250
    assert frame.pixelColor(130, 165).alpha() == 0
    assert frame.pixelColor(280, 165).alpha() > 0
    pet.close()


@pytest.mark.desktop
def test_pet_finishes_idle_yawn_and_takes_a_short_walk():
    app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    pet.set_spontaneous_enabled(False)
    initial_x = pet.x
    for _ in range(24):
        pet.tick()
    assert pet.machine.state == PetState.IDLE
    assert pet.sheet.toImage() == pet.animator.frame(PetState.IDLE, 24).toImage()
    for _ in range(20):
        pet.tick()
    assert pet.machine.state == PetState.WALKING
    for _ in range(18):
        pet.tick()
    assert pet.machine.state == PetState.IDLE
    assert pet.x != initial_x
    assert pet.frame == 0
    app.processEvents()
    pet.close()


@pytest.mark.desktop
def test_compact_bubble_follows_pet_without_a_white_trail():
    app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    pet.show()
    app.processEvents()
    assert pet.bubble_rect().width() < pet.width()
    assert pet.grab().toImage().pixelColor(50, 20).alpha() > 0

    pet.x = pet.width() - pet.sprite_size()[0]
    pet.redraw_surface()
    app.processEvents()
    assert pet.grab().toImage().pixelColor(50, 20).alpha() == 0
    pet.close()


@pytest.mark.desktop
def test_wizard_animation_has_distinct_walk_and_expression_frames():
    app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    app.processEvents()
    animator = pet.animator
    walk_still = animator.frame(PetState.WALKING, 0).toImage()
    walk_step = animator.frame(PetState.WALKING, 1).toImage()
    blink = animator.frame(PetState.IDLE, 0, blink=True).toImage()
    sleep = animator.frame(PetState.SLEEPING, 0).toImage()
    idle = animator.frame(PetState.IDLE, 0).toImage()
    yawn = animator.frame(PetState.IDLE, 24).toImage()
    assert walk_still != walk_step
    assert idle != blink
    assert idle != sleep
    assert idle != yawn
    assert body_path(PetState.WAVING, 0) == body_path(PetState.WAVING, 1)
    assert arm_paths(PetState.WAVING, 0) != arm_paths(PetState.WAVING, 1)
    assert all(image.size() == idle.size() for image in (walk_still, walk_step, blink, sleep))
    assert all(not animator.frame(state, 0).isNull() for state in PetState)
    assert (
        animator.frame(PetState.WAVING, 0).toImage() != animator.frame(PetState.WAVING, 1).toImage()
    )
    assert (
        animator.frame(PetState.TYPING, 0).toImage() != animator.frame(PetState.TYPING, 1).toImage()
    )
    assert (
        animator.frame(PetState.CASTING, 0).toImage()
        != animator.frame(PetState.CASTING, 1).toImage()
    )
    assert (
        animator.frame(PetState.THINKING, 0).toImage()
        != animator.frame(PetState.THINKING, 1).toImage()
    )
    assert (
        animator.frame(PetState.HAPPY, 0).toImage()
        != animator.frame(PetState.HAPPY, 1).toImage()
    )
    assert (
        animator.frame(PetState.TYPING, 0, prop_offset=8).toImage()
        != animator.frame(PetState.TYPING, 0).toImage()
    )
    front = animator.frame(PetState.TYPING, 0, typing_pose=0).toImage()
    side = animator.frame(PetState.TYPING, 0, typing_pose=2).toImage()
    assert front.pixelColor(22, 45).red() < 50  # two eyes while facing forward
    assert side.pixelColor(22, 45).red() > 200  # one eye in side profile
    assert side.pixelColor(56, 55).blue() > side.pixelColor(56, 55).red()
    assert not any(
        (color := idle.pixelColor(x, y)).alpha() > 0
        and color.red() > 230
        and color.green() > 230
        and color.blue() > 230
        for y in range(idle.height())
        for x in range(idle.width())
    )
    pet.close()


@pytest.mark.desktop
def test_pet_greets_periodically_without_interrupting_work_or_silent_mode():
    app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    original_bubble = pet.bubble
    pet.next_greeting_tick = 1
    pet.tick()
    assert pet.machine.state == PetState.WAVING
    assert pet.bubble == "Oi!"
    for _ in range(12):
        pet.tick()
    assert pet.machine.state == PetState.IDLE
    assert pet.bubble == original_bubble

    pet.next_greeting_tick = pet.total_ticks + 1
    pet.set_greetings_enabled(False)
    pet.tick()
    assert pet.machine.state != PetState.WAVING
    pet.set_greetings_enabled(True)
    pet.start_greeting()
    pet.react({"type": "queued"})
    assert pet.machine.state == PetState.THINKING
    assert pet.bubble == original_bubble
    app.processEvents()
    pet.close()


@pytest.mark.desktop
def test_pet_uses_laptop_and_staff_without_interrupting_work():
    app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    assert pet.scale == 3.5
    original_bubble = pet.bubble
    pet.next_greeting_tick = 999
    pet.next_activity_tick = 1
    pet.tick()
    assert pet.machine.state == PetState.TYPING
    assert pet.bubble == "Digitando..."
    for _ in range(6):
        pet.tick()
    assert pet.sheet.toImage().pixelColor(22, 45).red() > 200
    for _ in range(23):
        pet.tick()
    assert pet.sheet.toImage().pixelColor(22, 45).red() < 50
    for _ in range(3):
        pet.tick()
    assert pet.machine.state == PetState.IDLE
    assert pet.bubble == original_bubble

    pet.next_activity_tick = pet.total_ticks + 1
    pet.tick()
    assert pet.machine.state == PetState.CASTING
    assert pet.bubble == "Magia!"
    pet.react({"type": "queued"})
    assert pet.machine.state == PetState.THINKING
    assert pet.bubble == original_bubble

    pet.react({"type": "idle"})
    pet.set_spontaneous_enabled(False)
    pet.next_activity_tick = pet.total_ticks + 1
    pet.tick()
    assert pet.machine.state != PetState.TYPING
    assert pet.machine.state != PetState.CASTING
    app.processEvents()
    pet.close()


@pytest.mark.desktop
def test_staff_sparkle_disappears_after_magic():
    app = QApplication.instance() or QApplication([])
    pet = PetWindow()
    pet.show()
    pet.activity_turn = 1
    pet.start_activity()
    pet.activity_ticks = 5
    pet.redraw_surface()
    app.processEvents()
    width, height = pet.sprite_size()
    orb_x = pet.x + round(58 * width / 64)
    orb_y = pet.height() - height + round(25 * height / 72)
    assert pet.grab().toImage().pixelColor(orb_x, orb_y).alpha() > 0

    pet.finish_activity()
    pet.redraw_surface()
    app.processEvents()
    assert pet.grab().toImage().pixelColor(orb_x, orb_y).alpha() == 0
    pet.close()


def test_chat_window_receives_qt_and_backend_events(settings):
    from apps.desktop.chat.transport import BackendClient
    from apps.desktop.main import ChatWindow

    app = QApplication.instance() or QApplication([])
    QSettings("CodePet", "Lume").clear()
    client = BackendClient(settings.token.get_secret_value())
    window = ChatWindow(client, settings)
    assert window.skill.currentData() == "auto"
    assert window.voice.isChecked()
    spoken = []
    window.speaker.say = spoken.append
    window.show()
    app.processEvents()
    client.event.emit({"type": "token", "content": "exemplo"})
    assert "exemplo" in window.history.toPlainText()
    client.event.emit({"type": "done"})
    assert spoken == ["exemplo"]
    window.voice.setChecked(False)
    client.event.emit({"type": "token", "content": "silêncio"})
    client.event.emit({"type": "done"})
    assert spoken == ["exemplo"]
    window.shutdown()
    window.close()


@pytest.mark.desktop
def test_chat_is_translucent_with_visible_text(settings):
    from apps.desktop.chat.transport import BackendClient
    from apps.desktop.main import ChatWindow

    app = QApplication.instance() or QApplication([])
    client = BackendClient(settings.token.get_secret_value())
    window = ChatWindow(client, settings)
    window.history.setPlainText("Texto visível")
    window.show()
    app.processEvents()
    frame = window.grab().toImage()
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert frame.pixelColor(0, 0).alpha() == 0
    assert 0 < frame.pixelColor(20, 20).alpha() < 255
    origin = window.history.mapTo(window, window.history.rect().topLeft())
    assert any(
        min(color.red(), color.green(), color.blue()) > 220
        for y in range(origin.y() + 12, origin.y() + 42)
        for x in range(origin.x() + 12, origin.x() + 145)
        if (color := frame.pixelColor(x, y)).alpha() > 0
    )
    window.shutdown()
    window.close()


@pytest.mark.desktop
def test_chat_sends_selected_skill(settings):
    from apps.desktop.chat.transport import BackendClient
    from apps.desktop.main import ChatWindow

    app = QApplication.instance() or QApplication([])
    client = BackendClient(settings.token.get_secret_value())
    sent = []
    client.send = sent.append
    client.authenticated = True
    window = ChatWindow(client, settings)
    window.load_skills(
        {"items": [{"id": "debug-error", "name": "Investigar erro", "description": "Depuração"}]}
    )
    assert window.skill.currentData() == "auto"
    window.skill.setCurrentIndex(2)
    window.prompt.setText("Por que falhou?")
    window.ask()
    assert sent[0]["skill"] == "debug-error"
    app.processEvents()
    window.shutdown()
    window.close()
