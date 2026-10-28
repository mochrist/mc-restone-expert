"""Linter and index generator for the knowledge base in ``knowledge/``.

    uv run python -m redstone.knowledge lint
    uv run python -m redstone.knowledge index
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "knowledge"
GENERATED = {"README.md", "SOURCES.md", "UNVERIFIED.md"}

FIELDS = ["Aussage", "Version", "Quelle", "Konfidenz", "Status"]
CONFIDENCE = {"hoch", "mittel", "niedrig"}
STATUS = {"belegt", "ungeprüft", "widersprüchlich", "im-Spiel-verifiziert"}
VERIFIED_STATUS = {"belegt", "im-Spiel-verifiziert"}

_HEADING = re.compile(r"^### ([A-Z0-9]+-\d{3}): (.+)$")
_FIELD = re.compile(r"^- ([A-Za-zäöüÄÖÜ]+): (.*)$")
_SOURCE_REF = re.compile(r"\[(SRC-[A-Z0-9.-]+)\]")


@dataclass
class Claim:
    id: str
    title: str
    file: Path
    line: int
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return self.fields.get("Status", "").split(" ", 1)[0]


def parse_file(path: Path) -> list[Claim]:
    claims: list[Claim] = []
    current: Claim | None = None
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if m := _HEADING.match(line):
            current = Claim(m.group(1), m.group(2), path, no)
            claims.append(current)
        elif line.startswith("#"):
            current = None
        elif current is not None and (m := _FIELD.match(line)):
            current.fields[m.group(1)] = m.group(2).strip()
    return claims


def knowledge_files() -> list[Path]:
    return sorted(p for p in KNOWLEDGE.rglob("*.md")
                  if p.name not in GENERATED and p.parent.name != "sources")


def known_sources() -> set[str]:
    """Source ids from SOURCES.md and from knowledge/sources/*.md (one file per research area)."""
    paths = [KNOWLEDGE / "SOURCES.md", *sorted((KNOWLEDGE / "sources").glob("*.md"))]
    ids: set[str] = set()
    for path in paths:
        if path.exists():
            ids.update(re.findall(r"^- \[(SRC-[A-Z0-9.-]+)\]", path.read_text(encoding="utf-8"), re.M))
    return ids


def lint() -> list[str]:
    errors: list[str] = []
    sources = known_sources()
    seen: dict[str, Claim] = {}
    for path in knowledge_files():
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        prefix_match = re.search(r"^prefix: ([A-Z0-9]+)$", text, re.M)
        if not text.startswith("---") or not prefix_match:
            errors.append(f"{rel}: missing front matter with 'prefix:'")
        claims = parse_file(path)
        if not claims:
            errors.append(f"{rel}: no claims")
        for c in claims:
            where = f"{rel}:{c.line} {c.id}"
            if c.id in seen:
                errors.append(f"{where}: duplicate id (also in {seen[c.id].file.relative_to(ROOT)})")
            seen[c.id] = c
            if prefix_match and not c.id.startswith(prefix_match.group(1) + "-"):
                errors.append(f"{where}: id does not use file prefix {prefix_match.group(1)}")
            for f in FIELDS:
                if not c.fields.get(f):
                    errors.append(f"{where}: missing field '{f}'")
            if c.fields.get("Konfidenz") and c.fields["Konfidenz"] not in CONFIDENCE:
                errors.append(f"{where}: Konfidenz must be one of {sorted(CONFIDENCE)}")
            if c.fields.get("Status") and c.status not in STATUS:
                errors.append(f"{where}: Status must start with one of {sorted(STATUS)}")
            if c.status == "im-Spiel-verifiziert":
                m = re.search(r"\((scenarios/[^)]+)\)", c.fields["Status"])
                if not m or not (ROOT / m.group(1)).exists():
                    errors.append(f"{where}: verified status must reference an existing scenario file")
            refs = _SOURCE_REF.findall(c.fields.get("Quelle", ""))
            if c.fields.get("Quelle") and not refs and c.status != "ungeprüft":
                errors.append(f"{where}: Quelle must cite at least one [SRC-...] id")
            for ref in refs:
                if ref not in sources:
                    errors.append(f"{where}: unknown source {ref} (add it to knowledge/SOURCES.md)")
    return errors


def all_claims() -> list[Claim]:
    return [c for p in knowledge_files() for c in parse_file(p)]


def index() -> str:
    open_claims = [c for c in all_claims() if c.status not in VERIFIED_STATUS]
    lines = [
        "# Ungeprüfte und widersprüchliche Aussagen",
        "",
        "Generiert mit `uv run python -m redstone.knowledge index`. Nicht von Hand bearbeiten.",
        "",
        f"Stand: {len(open_claims)} offene von {len(all_claims())} Aussagen; "
        f"{sum(c.status == 'im-Spiel-verifiziert' for c in all_claims())} davon sind im Spiel verifiziert, "
        "die übrigen sind durch Quellen (meist den Spielcode) belegt.",
        "",
        "| ID | Status | Konfidenz | Aussage | Datei |",
        "|---|---|---|---|---|",
    ]
    for c in sorted(open_claims, key=lambda c: (c.status, c.id)):
        rel = c.file.relative_to(KNOWLEDGE).as_posix()
        title = c.title.replace("|", "\\|")
        lines.append(f"| {c.id} | {c.status} | {c.fields.get('Konfidenz', '')} | {title} | [{rel}]({rel}) |")
    return "\n".join(lines) + "\n"


def mark_verified(claim_ids: list[str], scenario: str, note: str | None = None) -> list[str]:
    """Set Status of the given claims to im-Spiel-verifiziert (scenario). Returns ids not found."""
    if not (ROOT / scenario).exists():
        raise FileNotFoundError(scenario)
    missing = set(claim_ids)
    by_file: dict[Path, list[Claim]] = {}
    for c in all_claims():
        if c.id in missing:
            by_file.setdefault(c.file, []).append(c)
            missing.discard(c.id)
    for path, claims in by_file.items():
        lines = path.read_text(encoding="utf-8").splitlines()
        targets = {c.line for c in claims}
        current = False
        for i, line in enumerate(lines):
            if _HEADING.match(line):
                current = (i + 1) in targets
            elif current and line.startswith("- Status:"):
                lines[i] = f"- Status: im-Spiel-verifiziert ({scenario})"
            elif current and note and line.startswith("- Hinweise:"):
                lines[i] = f"{line} {note}"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sorted(missing)


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "lint"
    if cmd == "mark":
        # mark <scenario path> <ID>...
        missing = mark_verified(argv[2:], argv[1])
        print(f"marked {len(argv) - 2 - len(missing)} claims" + (f"; not found: {missing}" if missing else ""))
        return 1 if missing else 0
    if cmd == "lint":
        errors = lint()
        for e in errors:
            print(e)
        print(f"{len(all_claims())} claims, {len(errors)} errors")
        return 1 if errors else 0
    if cmd == "index":
        (KNOWLEDGE / "UNVERIFIED.md").write_text(index(), encoding="utf-8")
        print("wrote knowledge/UNVERIFIED.md")
        return 0
    print(f"unknown command {cmd!r}; use lint or index")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
