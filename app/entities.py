"""Legal entity registry.

A "legal entity" is the specific company/subsidiary being reported on --
the thing an end user means when they ask "run the close for Acme Ops
LLC" or "which entity is this reporting against?". Kept separate from
BankTransaction/GLEntry (which stay entity-agnostic) so a single source
upload can be tagged to the right book of record.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models import new_id


@dataclass
class Entity:
    id: str = field(default_factory=new_id)
    name: str = ""
    base_currency: str = "USD"
    # Free-text description surfaced to the chat agent so it can disambiguate
    # ("Acme Ops LLC -- the US operating company, not the EU subsidiary").
    description: str = ""


class EntityRegistry:
    def __init__(self):
        self._entities: dict[str, Entity] = {}

    def add(self, name: str, base_currency: str = "USD", description: str = "") -> Entity:
        entity = Entity(name=name, base_currency=base_currency, description=description)
        self._entities[entity.id] = entity
        return entity

    def get(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def find_by_name(self, name: str) -> Entity | None:
        name = name.strip().lower()
        for entity in self._entities.values():
            if entity.name.strip().lower() == name:
                return entity
        return None

    def list(self) -> list[Entity]:
        return list(self._entities.values())


registry = EntityRegistry()
