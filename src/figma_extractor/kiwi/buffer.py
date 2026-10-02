"""Kiwi binary buffer reader (varint, strings, floats, byte arrays)."""

from __future__ import annotations

import struct


class ByteBuffer:
    __slots__ = ("data", "index", "length")

    def __init__(self, data: bytes | bytearray | memoryview | None = None) -> None:
        if data is None:
            self.data = bytearray()
            self.length = 0
        else:
            self.data = bytearray(data)
            self.length = len(self.data)
        self.index = 0

    def to_bytes(self) -> bytes:
        return bytes(self.data[: self.length])

    def read_byte(self) -> int:
        if self.index + 1 > len(self.data):
            raise IndexError("Index out of bounds")
        value = self.data[self.index]
        self.index += 1
        return value

    def read_byte_array(self) -> bytes:
        length = self.read_var_uint()
        start = self.index
        end = start + length
        if end > len(self.data):
            raise IndexError("Read array out of bounds")
        self.index = end
        return bytes(self.data[start:end])

    def read_var_float(self) -> float:
        index = self.index
        data = self.data
        if index + 1 > len(data):
            raise IndexError("Index out of bounds")
        first = data[index]
        if first == 0:
            self.index = index + 1
            return 0.0
        if index + 4 > len(data):
            raise IndexError("Index out of bounds")
        bits = first | (data[index + 1] << 8) | (data[index + 2] << 16) | (data[index + 3] << 24)
        self.index = index + 4
        # Rotate exponent back: (bits << 23) | (bits >>> 9)
        bits = ((bits << 23) & 0xFFFFFFFF) | (bits >> 9)
        return struct.unpack("<f", struct.pack("<I", bits))[0]

    def read_var_uint(self) -> int:
        value = 0
        shift = 0
        while True:
            byte = self.read_byte()
            value |= (byte & 127) << shift
            shift += 7
            if not (byte & 128) or shift >= 35:
                break
        return value & 0xFFFFFFFF

    def read_var_int(self) -> int:
        value = self.read_var_uint()
        # ZigZag decode for signed 32-bit
        if value & 1:
            return ~(value >> 1)
        return value >> 1

    def read_var_uint64(self) -> int:
        value = 0
        shift = 0
        while True:
            byte = self.read_byte()
            if (byte & 128) and shift < 56:
                value |= (byte & 127) << shift
                shift += 7
                continue
            value |= byte << shift
            return value

    def read_var_int64(self) -> int:
        value = self.read_var_uint64()
        sign = value & 1
        value >>= 1
        return ~value if sign else value

    def read_string(self) -> str:
        # Null-terminated UTF-8
        start = self.index
        data = self.data
        try:
            end = data.index(0, start)
        except ValueError as exc:
            raise IndexError("Unterminated string") from exc
        text = bytes(data[start:end]).decode("utf-8")
        self.index = end + 1
        return text
