"""Small, explicit skill catalog for the local tutor."""

import re
from dataclasses import dataclass
from pathlib import Path

SLUG = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
MAX_BYTES = 4096
MAX_INSTRUCTIONS = 2400


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    instructions: str

    def summary(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "description": self.description}


class SkillCatalog:
    def __init__(self, user_directory: Path):
        self.builtin = Path(__file__).parent / "builtin"
        self.user_directory = user_directory.expanduser()

    @staticmethod
    def _read(path: Path, slug: str) -> Skill | None:
        if not SLUG.fullmatch(slug) or path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > MAX_BYTES:
            return None
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            return None
        _, metadata, instructions = text.split("---", 2)
        fields = {}
        for line in metadata.strip().splitlines():
            key, separator, value = line.partition(":")
            if separator and key in {"name", "description"}:
                fields[key] = value.strip()
        instructions = instructions.strip()
        if (
            not fields.get("name")
            or not fields.get("description")
            or len(fields["name"]) > 80
            or len(fields["description"]) > 200
            or not instructions
            or len(instructions) > MAX_INSTRUCTIONS
        ):
            return None
        return Skill(slug, fields["name"], fields["description"], instructions)

    def list(self) -> list[Skill]:
        skills: dict[str, Skill] = {}
        for directory in (self.builtin, self.user_directory):
            if directory.is_symlink() or not directory.is_dir():
                continue
            for child in directory.iterdir():
                if child.is_symlink() or not child.is_dir() or not SLUG.fullmatch(child.name):
                    continue
                path = child / "SKILL.md"
                try:
                    skill = self._read(path, child.name)
                except (OSError, UnicodeError, ValueError):
                    continue
                if skill and skill.id not in skills:
                    skills[skill.id] = skill
        return sorted(skills.values(), key=lambda skill: skill.name.casefold())

    def get(self, identity: str) -> Skill:
        for skill in self.list():
            if skill.id == identity:
                return skill
        raise ValueError("Unknown skill")
