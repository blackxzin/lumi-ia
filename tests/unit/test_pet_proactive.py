from apps.desktop.pet.state import PetMachine, PetState
from backend.app.proactive.events import Proactive
from backend.app.schemas.messages import EditorEvent


def event():
    return EditorEvent(
        project="demo",
        path="main.py",
        language="python",
        diagnostics=[{"line": 2, "message": "name is not defined", "severity": "error"}],
    )


def test_pet_states_from_real_events():
    pet = PetMachine()
    for action, state in [
        ("queued", PetState.THINKING),
        ("token", PetState.TALKING),
        ("done", PetState.HAPPY),
        ("error", PetState.ERROR),
        ("cancelled", PetState.IDLE),
        ("greet", PetState.WAVING),
        ("open_laptop", PetState.TYPING),
        ("cast_spell", PetState.CASTING),
    ]:
        assert pet.handle(action) == state
    assert len(PetState) == 12


def test_proactive_debounce_cooldown_and_silent():
    p = Proactive(True)
    assert p.observe(event(), now=0) is None
    assert p.observe(event(), now=0.5) is None
    assert p.observe(event(), now=3) is None
    assert p.observe(event(), now=6)["line"] == 2
    for second in (9, 12, 15, 18):
        assert p.observe(event(), now=second) is None
    assert p.observe(event(), mode="silent", now=200) is None
    p.reset()
    assert not p.seen
    assert Proactive(False).observe(event(), now=0) is None
