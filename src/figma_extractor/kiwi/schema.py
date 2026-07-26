"""Decode and pretty-print Kiwi binary schemas embedded in `.fig` files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from figma_extractor.kiwi.buffer import ByteBuffer

DefinitionKind = Literal["ENUM", "STRUCT", "MESSAGE"]
PRIMITIVE_TYPES = ["bool", "byte", "int", "uint", "float", "string", "int64", "uint64"]
KINDS: list[DefinitionKind] = ["ENUM", "STRUCT", "MESSAGE"]


@dataclass
class Field:
    name: str
    type: Any
    is_array: bool
    value: int
    is_deprecated: bool = False


@dataclass
class Definition:
    name: str
    kind: DefinitionKind
    fields: list[Field] = field(default_factory=list)


@dataclass
class Schema:
    package: str | None
    definitions: list[Definition]


def decode_binary_schema(data: bytes | ByteBuffer) -> Schema:
    bb = data if isinstance(data, ByteBuffer) else ByteBuffer(data)
    definition_count = bb.read_var_uint()
    definitions: list[Definition] = []

    for _ in range(definition_count):
        definition_name = bb.read_string()
        kind = KINDS[bb.read_byte()]
        field_count = bb.read_var_uint()
        fields: list[Field] = []
        for _ in range(field_count):
            field_name = bb.read_string()
            type_code = bb.read_var_int()
            is_array = bool(bb.read_byte() & 1)
            value = bb.read_var_uint()
            fields.append(
                Field(
                    name=field_name,
                    type=None if kind == "ENUM" else type_code,  # type: ignore[arg-type]
                    is_array=is_array,
                    value=value,
                )
            )
        definitions.append(Definition(name=definition_name, kind=kind, fields=fields))

    # Bind type names afterwards (same second pass as kiwi-schema)
    for definition in definitions:
        for fld in definition.fields:
            type_code = fld.type  # temporarily a number or None
            if type_code is None:
                continue
            assert isinstance(type_code, int)
            if type_code < 0:
                idx = ~type_code
                if idx >= len(PRIMITIVE_TYPES):
                    raise ValueError(f"Invalid type {type_code}")
                fld.type = PRIMITIVE_TYPES[idx]
            else:
                if type_code >= len(definitions):
                    raise ValueError(f"Invalid type {type_code}")
                fld.type = definitions[type_code].name

    return Schema(package=None, definitions=definitions)


def pretty_print_schema(schema: Schema) -> str:
    lines: list[str] = []
    for definition in schema.definitions:
        if definition.kind == "ENUM":
            lines.append(f"enum {definition.name} {{")
            for fld in definition.fields:
                lines.append(f"  {fld.name} = {fld.value};")
            lines.append("}")
        elif definition.kind == "STRUCT":
            lines.append(f"struct {definition.name} {{")
            for fld in definition.fields:
                array = "[]" if fld.is_array else ""
                lines.append(f"  {fld.type}{array} {fld.name};")
            lines.append("}")
        else:
            lines.append(f"message {definition.name} {{")
            for fld in definition.fields:
                array = "[]" if fld.is_array else ""
                lines.append(f"  {fld.type}{array} {fld.name} = {fld.value};")
            lines.append("}")
        lines.append("")
    return "\n".join(lines)


def schema_as_dict(schema: Schema) -> dict[str, Any]:
    return {
        "package": schema.package,
        "definitions": [
            {
                "name": d.name,
                "kind": d.kind,
                "fields": [
                    {
                        "name": f.name,
                        "type": f.type,
                        "isArray": f.is_array,
                        "value": f.value,
                        "isDeprecated": f.is_deprecated,
                    }
                    for f in d.fields
                ],
            }
            for d in schema.definitions
        ],
    }
