"""Immutable block states in the string form used by the game: ``minecraft:repeater[delay=2,facing=north]``."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

DEFAULT_NAMESPACE = "minecraft"


def normalize_name(name: str) -> str:
    return name if ":" in name else f"{DEFAULT_NAMESPACE}:{name}"


@dataclass(frozen=True)
class BlockState:
    name: str
    props: tuple[tuple[str, str], ...] = ()

    @classmethod
    def of(cls, name: str, props: dict[str, object] | None = None, /, **kwargs: object) -> BlockState:
        merged = {**(props or {}), **kwargs}
        items = tuple(sorted((k, _prop_str(v)) for k, v in merged.items()))
        return cls(normalize_name(name), items)

    @classmethod
    def parse(cls, text: str) -> BlockState:
        text = text.strip()
        if "[" not in text:
            return cls.of(text)
        if not text.endswith("]"):
            raise ValueError(f"malformed block state: {text!r}")
        name, _, rest = text[:-1].partition("[")
        props: dict[str, object] = {}
        if rest:
            for part in rest.split(","):
                key, sep, value = part.partition("=")
                if not sep:
                    raise ValueError(f"malformed property {part!r} in {text!r}")
                props[key.strip()] = value.strip()
        return cls.of(name, props)

    @property
    def id(self) -> str:
        """Name without the ``minecraft:`` namespace."""
        ns, _, path = self.name.partition(":")
        return path if ns == DEFAULT_NAMESPACE else self.name

    @cached_property
    def _props_dict(self) -> dict[str, str]:
        return dict(self.props)

    @property
    def properties(self) -> dict[str, str]:
        return dict(self._props_dict)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._props_dict.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        value = self._props_dict.get(key)
        return default if value is None else int(value)

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self._props_dict.get(key)
        return default if value is None else value == "true"

    def with_(self, **kwargs: object) -> BlockState:
        return BlockState.of(self.name, {**self._props_dict, **kwargs})

    @property
    def is_air(self) -> bool:
        return self.name in AIR_NAMES

    def __str__(self) -> str:
        if not self.props:
            return self.name
        return f"{self.name}[{','.join(f'{k}={v}' for k, v in self.props)}]"

    def __repr__(self) -> str:
        return f"BlockState({str(self)!r})"


def _prop_str(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


AIR_NAMES = frozenset({"minecraft:air", "minecraft:cave_air", "minecraft:void_air"})
AIR = BlockState("minecraft:air")
