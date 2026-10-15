from enum import StrEnum


class PetState(StrEnum):
    IDLE = "idle"
    WALKING = "walking"
    SLEEPING = "sleeping"
    THINKING = "thinking"
    TALKING = "talking"
    HAPPY = "happy"
    CONFUSED = "confused"
    ERROR = "error"
    LISTENING = "listening"
    WAVING = "waving"
    TYPING = "typing"
    CASTING = "casting"


class PetMachine:
    EVENTS = {
        "queued": PetState.THINKING,
        "state": PetState.THINKING,
        "token": PetState.TALKING,
        "done": PetState.HAPPY,
        "error": PetState.ERROR,
        "cancelled": PetState.IDLE,
        "ready": PetState.IDLE,
        "listen": PetState.LISTENING,
        "uncertain": PetState.CONFUSED,
        "rest": PetState.SLEEPING,
        "walk": PetState.WALKING,
        "idle": PetState.IDLE,
        "greet": PetState.WAVING,
        "open_laptop": PetState.TYPING,
        "cast_spell": PetState.CASTING,
    }

    def __init__(self):
        self.state = PetState.IDLE
        self.paused = False

    def handle(self, event: str) -> PetState:
        self.state = self.EVENTS.get(event, self.state)
        return self.state
