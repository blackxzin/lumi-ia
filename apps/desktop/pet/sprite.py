"""Small SVG animation frames for Lume's wizard costume."""

from pathlib import Path
from xml.etree import ElementTree

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from apps.desktop.pet.state import PetState

ASSET = Path(__file__).resolve().parents[1] / "assets/wizard_pet.svg"
SVG_NS = "http://www.w3.org/2000/svg"
ElementTree.register_namespace("", SVG_NS)


def body_path(state: PetState, phase: int, typing_pose: int = 2) -> str:
    """Animate Lume's own silhouette with distinct walk, work and sleep poses."""
    if state == PetState.SLEEPING:
        return "M14 36H50V53H46V58H40V53H34V59H28V54H22V59H18V53H14Z"
    if state == PetState.TYPING and typing_pose == 2:
        return "M16 29H40V32H44V35H47V44H43V58H37V51H32V59H26V51H22V58H16V46H12V39H13V33H16Z"
    if state == PetState.TYPING and typing_pose == 1:
        return "M16 29H44V33H49V35H52V43H48V44H45V58H39V51H34V59H28V51H23V58H17V46H11V39H12V33H16Z"
    legs = (58, 59, 59, 58)
    if state == PetState.WALKING:
        legs = (
            (58, 59, 59, 58),
            (53, 59, 55, 59),
            (58, 59, 59, 58),
            (59, 55, 59, 53),
        )[phase % 4]
    elif state == PetState.IDLE:
        # A tiny alternating foot shift keeps the idle loop from freezing in
        # one rectangular silhouette while preserving the four-leg design.
        legs = (
            (58, 59, 59, 58),
            (57, 59, 58, 58),
            (56, 59, 59, 57),
            (57, 59, 58, 58),
            (58, 58, 59, 58),
            (59, 58, 58, 59),
            (58, 59, 59, 58),
            (58, 59, 59, 58),
        )[phase % 8]
    outer_left, inner_left, inner_right, outer_right = legs
    return (
        f"M15 29H49V{outer_right}H45V51H41V{inner_right}H35V51"
        f"H29V{inner_left}H23V51H19V{outer_left}H15Z"
    )


def arm_paths(state: PetState, phase: int) -> tuple[str, str]:
    """Small articulated arms that do not change the body's proportions."""
    left = "M15 38H12V40H9V43H12V45H15Z"
    right = "M49 38H52V40H55V43H52V45H49Z"
    if state == PetState.SLEEPING:
        return "M14 44H10V46H7V48H14Z", "M50 44H54V46H57V48H50Z"
    if state == PetState.WALKING:
        if phase % 4 in {1, 2}:
            left = "M15 38H12V37H9V39H8V42H12V44H15Z"
        else:
            right = "M49 38H52V37H55V39H56V42H52V44H49Z"
    elif state == PetState.WAVING:
        right = (
            "M49 38H52V34H55V29H58V33H55V39H52V44H49Z"
            if phase % 4 in {0, 2}
            else "M49 38H53V36H57V35H58V39H54V42H52V45H49Z"
        )
    elif state == PetState.HAPPY:
        left = "M15 38H12V35H9V32H7V36H10V43H15Z"
        right = "M49 38H52V35H55V32H57V36H54V43H49Z"
    elif state in {PetState.THINKING, PetState.TALKING}:
        # Hands alternate between the notebook and the chin while a task is
        # being prepared, giving the thinking state a working pose of its own.
        if phase % 4 in {0, 1}:
            right = "M49 38H52V36H56V38H59V41H55V43H49Z"
        else:
            left = "M15 38H12V36H9V38H7V41H10V43H15Z"
    elif state == PetState.IDLE:
        # Keep the idle pose alive with small alternating arm gestures.  The
        # larger gestures still happen later in the cycle, so the character
        # does not look like a static sticker between activities.
        idle_phase = phase % 16
        if idle_phase in {1, 2, 3}:
            left = "M15 38H12V36H9V34H7V38H10V43H15Z"
        elif idle_phase in {5, 6, 7}:
            right = "M49 38H52V36H55V34H57V38H54V43H49Z"
        elif idle_phase in {9, 10, 11, 12}:
            left = "M15 38H12V34H9V29H7V33H9V41H15Z"
            right = "M49 38H52V34H55V29H57V33H55V41H49Z"
        elif idle_phase in {13, 14}:
            left = "M15 38H12V36H9V38H7V41H10V44H15Z"
        else:
            right = "M49 38H52V36H55V38H57V41H54V44H49Z"
    return left, right


def add_idle_magic(root: ElementTree.Element, phase: int) -> None:
    """A tiny spark travels between Lume's hands during an idle gesture."""
    if not 8 <= phase <= 17:
        return
    positions = (
        (10, 32), (13, 28), (17, 24), (22, 20), (28, 17),
        (34, 17), (40, 20), (45, 24), (49, 28), (52, 32),
    )
    x, y = positions[phase - 8]
    ElementTree.SubElement(
        root,
        f"{{{SVG_NS}}}path",
        {
            "d": f"M{x + 2} {y}H{x + 4}V{y + 2}H{x + 6}V{y + 4}H{x + 4}V{y + 6}"
            f"H{x + 2}V{y + 4}H{x}V{y + 2}H{x + 2}Z",
            "fill": "#72DBD4" if phase % 2 else "#F9D66A",
        },
    )


def eye_path(state: PetState, blink: bool, typing_pose: int = 2, phase: int = 0) -> str:
    if state == PetState.TYPING:
        if typing_pose == 2:
            return "M34 39H41" if blink else "M34 36L41 39L34 42"
        if typing_pose == 1:
            return "M22 39H25M35 39H42" if blink else "M22 39H25M35 36L42 39L35 42"
    if blink or state == PetState.SLEEPING or (state == PetState.IDLE and 22 <= phase % 32 <= 26):
        return "M19 39H26M38 39H45"
    if state == PetState.IDLE and phase % 32 in {0, 1, 2, 3}:
        return "M20 37V42M40 37V42"
    if state == PetState.IDLE and phase % 32 in {27, 28, 29, 30, 31}:
        return "M24 37V42M44 37V42"
    if state == PetState.ERROR:
        return "M20 36L25 42M25 36L20 42M39 36L44 42M44 36L39 42"
    if state == PetState.CONFUSED:
        return "M19 35L26 39L19 43M40 39H43"
    if state == PetState.HAPPY:
        return "M19 40L22 36L26 40M38 40L42 36L45 40"
    return "M22 37V42M42 37V42"


def add_laptop(root: ElementTree.Element, phase: int, offset: int, pose: int) -> None:
    """Show the lid's back to the viewer; its screen faces the pet on the left."""
    group = ElementTree.SubElement(root, f"{{{SVG_NS}}}g", {"transform": f"translate({offset} -4)"})

    def part(tag: str, **attributes: str) -> None:
        ElementTree.SubElement(group, f"{{{SVG_NS}}}{tag}", attributes)

    if pose == 0:
        part("rect", x="46", y="59", width="15", height="4", fill="#7891A8")
        part("rect", x="44", y="63", width="19", height="3", fill="#253D5C")
        part("rect", x="43", y="55", width="5", height="4", fill="#F26C4A")
        return

    part(
        "path",
        d="M39 63L51 59L61 61L54 67Z",
        fill="#8EA5BA",
        stroke="#183655",
        **{"stroke-width": "1"},
    )
    part("path", d="M42 62L51 60M45 64L53 62", stroke="#243E60", **{"stroke-width": "1"})
    if pose == 1:
        part("path", d="M51 46L60 44L62 60L51 61Z", fill="#355A80")
        part("path", d="M51 46V61", stroke="#142C4A", **{"stroke-width": "2"})
    else:
        part("path", d="M49 40L60 38L62 59L51 61Z", fill="#355A80")
        part("path", d="M49 40L51 61", stroke="#142C4A", **{"stroke-width": "2"})
        part("path", d="M48 43L50 58", stroke="#65C5BD", **{"stroke-width": "1"})
        part("path", d="M56 45L57 47L59 48L57 49L56 51L55 49L53 48L55 47Z", fill="#E6B55A")

    near_tap = 62 if phase % 2 == 0 else 53
    far_tap = 53 if phase % 2 == 0 else 62
    part(
        "path",
        d=f"M42 44H47V53H44V{near_tap}H41V55H42Z",
        fill="#F26C4A",
    )
    part(
        "path",
        d=f"M37 46H41V53H40V{far_tap}H37Z",
        fill="#F26C4A",
    )
    part(
        "rect",
        x="43" if phase % 2 else "39",
        y="53" if phase % 2 else "61",
        width="4",
        height="3",
        fill="#FF9C72",
    )


def add_thinking_work(root: ElementTree.Element, phase: int) -> None:
    """A small notebook and changing code marks for the focused work pose."""
    group = ElementTree.SubElement(
        root,
        f"{{{SVG_NS}}}g",
        {"transform": f"translate(0 {(phase % 4 in {1, 2}) * -1})"},
    )

    def part(tag: str, **attributes: str) -> None:
        ElementTree.SubElement(group, f"{{{SVG_NS}}}{tag}", attributes)

    part(
        "path",
        d="M47 34H61V51H47Z",
        fill="#203C60",
        stroke="#6B94B9",
        **{"stroke-width": "1"},
    )
    part("path", d="M50 38H58M50 42H56M50 46H54", stroke="#72DBD4", **{"stroke-width": "1"})
    part("path", d="M44 49L50 43L52 45L46 51Z", fill="#F8C54E")
    if phase % 4 in {0, 1}:
        part("path", d="M54 30H56V32H54Z", fill="#F8C54E")
    else:
        part("path", d="M58 28H60V30H58Z", fill="#72DBD4")


def add_completion_effect(root: ElementTree.Element, phase: int) -> None:
    """Pixel confetti and a bright check mark when a task completes."""
    sparks = (
        ("M7 24H9V27H7Z", "#72DBD4"),
        ("M55 22H58V24H55Z", "#F8C54E"),
        ("M11 34H13V37H11Z", "#F8C54E"),
        ("M51 31H54V34H51Z", "#72DBD4"),
    )
    for index, (path, color) in enumerate(sparks):
        if (phase + index) % 4 in {0, 1}:
            ElementTree.SubElement(
                root,
                f"{{{SVG_NS}}}path",
                {"d": path, "fill": color},
            )
    if phase % 4 in {1, 2}:
        ElementTree.SubElement(
            root,
            f"{{{SVG_NS}}}path",
            {"d": "M29 42L32 45L37 39L39 41L32 49L27 44Z", "fill": "#72DBD4"},
        )


def add_staff(root: ElementTree.Element, phase: int, offset: int) -> None:
    """A held staff with small, changing pixel-art magic sparks."""
    group = ElementTree.SubElement(root, f"{{{SVG_NS}}}g", {"transform": f"translate({offset} 0)"})

    def part(tag: str, **attributes: str) -> None:
        ElementTree.SubElement(group, f"{{{SVG_NS}}}{tag}", attributes)

    part(
        "path",
        d="M49 57L58 19",
        stroke="#81502D",
        **{"stroke-width": "4", "stroke-linecap": "square"},
    )
    part("path", d="M55 19L58 13L61 19L58 24Z", fill="#F6BE4D")
    part("rect", x="48", y=str(42 + phase % 2), width="9", height="5", fill="#F26C4A")
    sparks = (
        ("M43 12H45V10H47V12H49V14H47V16H45V14H43Z", 0),
        ("M49 5H51V3H53V5H55V7H53V9H51V7H49Z", 1),
        ("M58 5H60V3H62V5H64V7H62V9H60V7H58Z", 2),
        ("M38 21H40V19H42V21H44V23H42V25H40V23H38Z", 3),
    )
    for path, moment in sparks:
        if (phase - moment) % 4 in {0, 1}:
            part("path", d=path, fill="#F9D66A" if moment % 2 else "#72DBD4")


class SpriteAnimator:
    def __init__(self):
        self.template = ElementTree.parse(ASSET).getroot()
        self.cache: dict[tuple[PetState, int, bool, int, int, int], QPixmap] = {}

    def frame(
        self,
        state: PetState,
        phase: int,
        blink: bool = False,
        prop_offset: int = 0,
        typing_pose: int = 2,
        subframe: int = 0,
    ) -> QPixmap:
        phase %= 32
        subframe %= 3
        key = (state, phase, blink, prop_offset, typing_pose, subframe)
        if key not in self.cache:
            self.cache[key] = self._render(
                state, phase, blink, prop_offset, typing_pose, subframe
            )
        return self.cache[key]

    def _render(
        self,
        state: PetState,
        phase: int,
        blink: bool,
        prop_offset: int,
        typing_pose: int,
        subframe: int,
    ) -> QPixmap:
        root = ElementTree.fromstring(ElementTree.tostring(self.template))
        body = root.find(".//*[@id='body']")
        left_arm = root.find(".//*[@id='left-arm']")
        right_arm = root.find(".//*[@id='right-arm']")
        eyes = root.find(".//*[@id='eyes']")
        hat = root.find(".//*[@id='hat']")
        star = root.find(".//*[@id='hat-star']")
        assert all(part is not None for part in (body, left_arm, right_arm, eyes, hat, star))
        animated_body = body_path(state, phase, typing_pose)
        body.set("d", animated_body)
        eyes.set("d", eye_path(state, blink, typing_pose, phase))

        # Pixel-sized breathing, leaning and eye movement use one shared motion
        # transform.  Keeping body, arms, eyes and hat on the same transform
        # makes the sprite feel articulated instead of sliding independently.
        body_y = 0
        motion_x = 0
        tilt = 0
        if state == PetState.WALKING:
            body_y = (0, -1, -2, -1)[phase % 4]
            motion_x = (-1, 0, 1, 0)[phase % 4]
            tilt = (-2, -1, 1, 2)[phase % 4]
        elif state == PetState.SLEEPING:
            body_y = 0 if phase % 16 < 8 else 1
            tilt = -1 if phase % 16 < 8 else 1
        elif state in {PetState.THINKING, PetState.TALKING, PetState.LISTENING}:
            body_y = -1 if phase % 8 in {2, 3, 4} else 0
            motion_x = (-1, 0, 1, 0)[phase % 4]
            tilt = (-1, 0, 1, 0)[phase % 4]
        elif state in {PetState.HAPPY, PetState.WAVING, PetState.CASTING}:
            body_y = (0, -1, -2, -1)[phase % 4]
            motion_x = (-1, 0, 1, 0)[phase % 4]
            tilt = (-2, -1, 1, 2)[phase % 4]
        elif state == PetState.IDLE:
            idle_phase = phase % 8
            body_y = (0, -1, -2, -3, -2, -1, 0, 0)[idle_phase]
            motion_x = (-2, -1, 0, 1, 2, 1, 0, -1)[idle_phase]
            tilt = (-3, -2, -1, 1, 3, 2, 1, -2)[idle_phase]
        if subframe and state != PetState.TYPING:
            next_phase = (phase + 1) % 32
            if state == PetState.WALKING or state in {
                PetState.HAPPY,
                PetState.WAVING,
                PetState.CASTING,
            }:
                next_y = (0, -1, -2, -1)[next_phase % 4]
                next_x = (-1, 0, 1, 0)[next_phase % 4]
                next_tilt = (-2, -1, 1, 2)[next_phase % 4]
            elif state == PetState.IDLE:
                next_idle = next_phase % 8
                next_y = (0, -1, -2, -3, -2, -1, 0, 0)[next_idle]
                next_x = (-2, -1, 0, 1, 2, 1, 0, -1)[next_idle]
                next_tilt = (-3, -2, -1, 1, 3, 2, 1, -2)[next_idle]
            elif state == PetState.SLEEPING:
                next_y = 0 if next_phase % 16 < 8 else 1
                next_x = 0
                next_tilt = -1 if next_phase % 16 < 8 else 1
            else:
                next_y = -1 if next_phase % 8 in {2, 3, 4} else 0
                next_x = (-1, 0, 1, 0)[next_phase % 4]
                next_tilt = (-1, 0, 1, 0)[next_phase % 4]
            ratio = subframe / 3
            body_y += (next_y - body_y) * ratio
            motion_x += (next_x - motion_x) * ratio
            tilt += (next_tilt - tilt) * ratio
        if state != PetState.TYPING:
            motion = f"translate({motion_x:.2f} {body_y:.2f}) rotate({tilt:.2f} 32 44)"
            body.set("transform", motion)
            eyes.set(
                "transform",
                f"{motion} translate(0 {10 if state == PetState.SLEEPING else 0})",
            )
        else:
            motion = ""
        if state == PetState.IDLE and 13 <= phase % 32 <= 19 and not blink:
            eyes.set("transform", f"{motion} translate(2 0)")

        if state == PetState.TYPING:
            root.remove(left_arm)
            root.remove(right_arm)
        else:
            left_path, right_path = arm_paths(state, phase)
            left_arm.set("d", left_path)
            right_arm.set("d", right_path)
            if motion:
                left_arm.set("transform", motion)
                right_arm.set("transform", motion)

        shadow = ElementTree.Element(
            f"{{{SVG_NS}}}ellipse",
            {
                "cx": str(32 + motion_x),
                "cy": "62",
                "rx": str(20 + (phase % 4 in {0, 3})),
                "ry": "2.2",
                "fill": "#17263D",
                "opacity": "0.18" if body_y >= 0 else "0.11",
            },
        )
        root.insert(0, shadow)

        if state == PetState.TYPING and typing_pose:
            shift = -3 if typing_pose == 1 else -6
            hat.set("transform", f"translate({shift} 0)")
        elif state in {PetState.WALKING, PetState.WAVING, PetState.CASTING}:
            shift = (0, -1, 0, 1)[phase % 4]
            hat.set("transform", f"translate({shift} 0) {motion}")
        elif state == PetState.SLEEPING:
            hat.set("transform", f"translate(1 10) {motion}")
        elif state == PetState.THINKING:
            hat.set("transform", f"translate({-1 if phase % 8 < 4 else 1} 0) {motion}")
        elif state == PetState.IDLE and 21 <= phase % 32 <= 26:
            hat.set("transform", f"translate(-1 -1) {motion}")
        elif state != PetState.TYPING:
            hat.set("transform", motion)
        if phase % 32 in {5, 6, 7, 8, 21, 22}:
            star.set("fill", "#FFF0A5")

        if state == PetState.TALKING:
            ElementTree.SubElement(
                root,
                f"{{{SVG_NS}}}path",
                {
                    "d": "M30 44H35V48H30Z" if phase % 4 < 2 else "M30 45H35V46H30Z",
                    "fill": "#14171E",
                    "transform": f"translate(0 {body_y})",
                },
            )
        elif state == PetState.IDLE and 23 <= phase % 32 <= 26:
            ElementTree.SubElement(
                root,
                f"{{{SVG_NS}}}path",
                {"d": "M30 44H35V49H30Z", "fill": "#14171E", "transform": f"translate(0 {body_y})"},
            )
        elif state == PetState.TYPING:
            add_laptop(root, phase, prop_offset, typing_pose)
        elif state in {PetState.THINKING, PetState.TALKING}:
            add_thinking_work(root, phase)
        elif state == PetState.CASTING:
            add_staff(root, phase, prop_offset)

        if state == PetState.IDLE:
            add_idle_magic(root, phase)

        if state == PetState.HAPPY and phase % 8 in {1, 2, 5}:
            ElementTree.SubElement(
                root,
                f"{{{SVG_NS}}}path",
                {"d": "M56 16H58V13H60V16H62V18H60V21H58V18H56Z", "fill": "#F8C54E"},
            )
        if state == PetState.HAPPY:
            add_completion_effect(root, phase)
        elif state == PetState.THINKING and phase % 8 in {2, 3, 4}:
            ElementTree.SubElement(
                root,
                f"{{{SVG_NS}}}path",
                {"d": "M58 15H61V18H58Z", "fill": "#F8C54E"},
            )

        renderer = QSvgRenderer(QByteArray(ElementTree.tostring(root)))
        if not renderer.isValid():
            raise ValueError("Não foi possível renderizar o sprite SVG")
        image = QImage(64, 72, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.translate(0, 6)
        renderer.render(painter)
        painter.end()
        return QPixmap.fromImage(image)
