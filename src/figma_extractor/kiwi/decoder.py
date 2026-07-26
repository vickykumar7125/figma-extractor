"""Interpretive Kiwi message decoder bound to an embedded schema."""

from __future__ import annotations

from typing import Any, Callable

from figma_extractor.kiwi.buffer import ByteBuffer
from figma_extractor.kiwi.schema import Definition, Schema


class CompiledSchema:
    """Bound decode helpers for every STRUCT / MESSAGE / ENUM in a schema."""

    def __init__(self, schema: Schema) -> None:
        self.schema = schema
        self.definitions: dict[str, Definition] = {d.name: d for d in schema.definitions}
        self.enums: dict[str, dict[Any, Any]] = {}
        self._decoders: dict[str, Callable[[ByteBuffer], Any]] = {}

        for definition in schema.definitions:
            if definition.kind == "ENUM":
                mapping: dict[Any, Any] = {}
                for fld in definition.fields:
                    mapping[fld.name] = fld.value
                    mapping[fld.value] = fld.name
                self.enums[definition.name] = mapping

        # Build decoders after enums exist so nested refs resolve.
        for definition in schema.definitions:
            if definition.kind in ("STRUCT", "MESSAGE"):
                self._decoders[definition.name] = self._make_decoder(definition)

    def decode_message(self, data: bytes | ByteBuffer, type_name: str = "Message") -> Any:
        bb = data if isinstance(data, ByteBuffer) else ByteBuffer(data)
        decoder = self._decoders.get(type_name)
        if decoder is None:
            raise KeyError(f"No decoder for type {type_name!r}")
        return decoder(bb)

    def _make_decoder(self, definition: Definition) -> Callable[[ByteBuffer], Any]:
        fields = definition.fields
        kind = definition.kind
        field_by_id = {f.value: f for f in fields} if kind == "MESSAGE" else None

        def decode_value(bb: ByteBuffer, type_name: str | None) -> Any:
            if type_name == "bool":
                return bool(bb.read_byte())
            if type_name == "byte":
                return bb.read_byte()
            if type_name == "int":
                return bb.read_var_int()
            if type_name == "uint":
                return bb.read_var_uint()
            if type_name == "float":
                return bb.read_var_float()
            if type_name == "string":
                return bb.read_string()
            if type_name == "int64":
                return bb.read_var_int64()
            if type_name == "uint64":
                return bb.read_var_uint64()

            nested = self.definitions.get(type_name or "")
            if nested is None:
                raise ValueError(f"Invalid type {type_name!r}")
            if nested.kind == "ENUM":
                raw = bb.read_var_uint()
                return self.enums[nested.name].get(raw, raw)
            return self._decoders[nested.name](bb)

        def decode_field(bb: ByteBuffer, fld) -> Any:
            if fld.is_array:
                if fld.type == "byte":
                    return bb.read_byte_array()
                length = bb.read_var_uint()
                return [decode_value(bb, fld.type) for _ in range(length)]
            return decode_value(bb, fld.type)

        if kind == "STRUCT":

            def decode_struct(bb: ByteBuffer) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for fld in fields:
                    if fld.is_deprecated:
                        decode_field(bb, fld)
                        continue
                    result[fld.name] = decode_field(bb, fld)
                return result

            return decode_struct

        def decode_message(bb: ByteBuffer) -> dict[str, Any]:
            result: dict[str, Any] = {}
            while True:
                field_id = bb.read_var_uint()
                if field_id == 0:
                    return result
                fld = field_by_id.get(field_id) if field_by_id is not None else None
                if fld is None:
                    raise ValueError(
                        f"Attempted to parse invalid message {definition.name!r}: unknown field id {field_id}"
                    )
                if fld.is_deprecated:
                    decode_field(bb, fld)
                    continue
                result[fld.name] = decode_field(bb, fld)

        return decode_message


def compile_schema(schema: Schema) -> CompiledSchema:
    return CompiledSchema(schema)
