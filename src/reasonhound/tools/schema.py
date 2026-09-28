"""Reduce a Pydantic JSON schema to the subset every provider accepts.

Pydantic emits ``$defs`` / ``$ref``, ``title``, ``additionalProperties`` and
``anyOf: [{...}, {"type": "null"}]`` for optional fields. OpenAI and Anthropic
take full JSON Schema, but Gemini's ``parameters`` is an OpenAPI subset that
rejects all of those. Sending one portable schema to everyone keeps the adapters
free of per-provider schema surgery.

Dropping ``additionalProperties`` only loosens the hint the model sees: the
arguments are still validated against the strict Pydantic model on our side.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

__all__ = ["NonPortableSchemaError", "portable_schema"]

_KEEP: frozenset[str] = frozenset(
    {
        "type",
        "description",
        "enum",
        "properties",
        "required",
        "items",
        "anyOf",
        "nullable",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "default",
    }
)


def portable_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema for *model* with refs inlined and non-portable keys removed.

    Raises :class:`NonPortableSchemaError` for constructs that cannot be reduced
    without changing meaning (unions of objects, free-form maps, mixed-type
    enums): failing when the tool is defined beats a provider 400 mid-scan.
    """
    raw = model.model_json_schema()
    defs: dict[str, Any] = raw.get("$defs", {})
    return _clean(raw, defs, model.__name__)


class NonPortableSchemaError(ValueError):
    """A tool or output model uses a schema construct some provider rejects."""


_REJECT: frozenset[str] = frozenset({"oneOf", "allOf", "not", "discriminator", "patternProperties"})

_ENUM_TYPES: dict[type, str] = {str: "string", bool: "boolean", int: "integer", float: "number"}


def _clean(node: Any, defs: dict[str, Any], where: str) -> Any:
    if isinstance(node, list):
        return [_clean(item, defs, where) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        # A sibling description on a $ref (a field's docstring) wins over the target's.
        merged = {**defs[name], **{k: v for k, v in node.items() if k != "$ref"}}
        return _clean(merged, defs, where)
    rejected = _REJECT & node.keys()
    if rejected:
        raise NonPortableSchemaError(f"{where}: unsupported schema keyword {sorted(rejected)[0]!r}")
    if "const" in node:
        # Literal["x"]: a one-value enum is the portable spelling of const.
        node = {**{k: v for k, v in node.items() if k != "const"}, "enum": [node["const"]]}
    nullable = False
    if "anyOf" in node:
        variants = [v for v in node["anyOf"] if v != {"type": "null"}]
        nullable = len(variants) < len(node["anyOf"])
        rest = {k: v for k, v in node.items() if k != "anyOf"}
        if len(variants) == 1:
            # Optional[X] -> X + nullable, the one optional form Gemini understands.
            # Recurse so a $ref variant is resolved like any other node.
            collapsed = _clean({**variants[0], **rest}, defs, where)
            if nullable:
                collapsed["nullable"] = True
            return collapsed
        node = {**rest, "anyOf": variants}
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key not in _KEEP:
            continue
        if key == "properties":
            out[key] = {name: _clean(sub, defs, f"{where}.{name}") for name, sub in value.items()}
        elif key == "default" and value is None:
            continue  # implied by nullable
        elif key in ("default", "enum", "required"):
            out[key] = value  # literal values, not schemas
        else:
            out[key] = _clean(value, defs, where)
    if nullable:
        out["nullable"] = True
    if "enum" in out and "type" not in out:
        kinds = {_ENUM_TYPES.get(type(v)) for v in out["enum"]}
        if len(kinds) != 1 or None in kinds:
            raise NonPortableSchemaError(f"{where}: enum values must share one scalar type")
        out["type"] = kinds.pop()
    if out.get("type") == "object" and "properties" not in out:
        raise NonPortableSchemaError(
            f"{where}: objects need declared properties (no free-form maps)"
        )
    if not out.get("type") and "anyOf" not in out:
        raise NonPortableSchemaError(f"{where}: every schema node needs a type")
    return out
