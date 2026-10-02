"""Token-oriented notation used for model context.

The encoder and decoder follow the TOON format and are included in this
package. The implementation is derived from the MIT-licensed project by the
TOON Format Organization (Johann Schopplich and contributors). Annotation
calls ``encode``. ``decode`` turns that text back into structured values.
"""

from figma_extractor.toon.decoder import ToonDecodeError, decode
from figma_extractor.toon.encoder import encode
from figma_extractor.toon.types import DecodeOptions, EncodeOptions

__all__ = [
    "DecodeOptions",
    "EncodeOptions",
    "ToonDecodeError",
    "decode",
    "encode",
]
