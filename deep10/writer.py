"""deep10.writer - 16-bit RGB output.

Pillow cannot write 16-bit RGB at all (TypeError: Cannot handle this data
type: (1,1,3), <u2), so output does not go through PIL.

WHY NOT OpenImageIO FOR PNG
    OIIO tags its output. Measured, it writes sRGB, gAMA (0.45455), cHRM,
    eXIf and oFFs chunks, and forcing oiio:ColorSpace to Linear still leaves
    gAMA, eXIf and oFFs. Any reader that honours gAMA then transforms the
    picture: Photoshop showed legal white as 27042 instead of 30109, which is
    exactly 60218/65535 linearised through sRGB.

    Bill's own PNGs carry IHDR and IDAT and nothing else. cv2 writes the same
    two chunks and round-trips the values exactly, so PNG goes through cv2.

VALUE CONVENTION
    Stored full-scale expanded: code * 65535 / MAXVAL. Raw 10-bit codes in a
    16-bit container would put white at 1.56% of full scale and read as
    near-black. The expansion round-trips exactly for all 1024 codes.
"""
import numpy as np
import cv2
from .core import MAXVAL


def expand(codes):
    """10-bit codes -> full-scale 16-bit. Exact round trip, verified 1024/1024."""
    return np.rint(np.asarray(codes, np.float64) * 65535.0 / MAXVAL).astype(np.uint16)


def write(path, codes, description=""):
    a = expand(codes)
    if path.lower().endswith(".png"):
        # cv2 takes BGR and emits IHDR + IDAT only, matching the 8-bit set.
        # Its default compression is level 1; level 9 is ~3x smaller and still
        # lossless, verified byte-exact on read-back.
        if not cv2.imwrite(path, np.ascontiguousarray(a[..., ::-1]),
                           [cv2.IMWRITE_PNG_COMPRESSION, 9]):
            raise IOError(f"deep10.writer: cv2 failed to write {path}")
        return
    if path.lower().endswith((".tif", ".tiff")):
        if not cv2.imwrite(path, np.ascontiguousarray(a[..., ::-1])):
            raise IOError(f"deep10.writer: cv2 failed to write {path}")
        return
    raise ValueError(f"deep10.writer: unsupported output {path}")
