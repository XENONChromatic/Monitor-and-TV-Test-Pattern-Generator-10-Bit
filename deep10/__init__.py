"""
deep10 - drop-in 10-bit replacements for the PIL names mk-patterns.py imports.

Usage in mk-patterns.py: replace

    from PIL import Image
    from PIL import ImageDraw
    from PIL import ImageFont
    from PIL import ImageOps

with

    from deep10 import Image, ImageDraw, ImageFont, ImageOps, MAXVAL
"""
import numpy as np
from PIL import Image as _PILImage, ImageFont as _PILFont
from .core import DeepImage, DeepDraw, MAXVAL, SRCMAX, scale8, _parse, raw10, snap_legal

__all__ = ["Image", "ImageDraw", "ImageFont", "ImageOps",
           "MAXVAL", "SRCMAX", "scale8", "raw10", "r10", "lab", "snap_legal"]


def r10(v):
    """Mark a value or sequence as already 10-bit, so the shim will not scale it.
    Used only by the functions that compute continuous gradients."""
    if isinstance(v, (int, np.integer)):
        return raw10(int(v))
    return tuple(raw10(int(x)) for x in v)


def lab(v):
    """The 10-bit number a printed label should show, whichever space the
    caller is working in."""
    return int(v) if isinstance(v, raw10) else scale8(v)


class Image:
    """Module stand-in for PIL.Image."""
    @staticmethod
    def new(mode, size, color=None):
        if mode != "RGB":
            raise ValueError(f"deep10: unexpected Image.new mode {mode!r}")
        return DeepImage(size, color)

    @staticmethod
    def frombytes(mode, size, data):
        # Mode '1' bitmaps are masks, not pictures. They stay 1-bit and are
        # handed straight to PIL, exactly as the 8-bit generator does.
        if mode != "1":
            raise ValueError(f"deep10: unexpected Image.frombytes mode {mode!r}")
        return _PILImage.frombytes(mode, size, data)

    @staticmethod
    def fromarray(arr, mode=None):
        if mode not in (None, "RGB"):
            raise ValueError(f"deep10: unexpected Image.fromarray mode {mode!r}")
        a = np.asarray(arr)
        if a.ndim != 3 or a.shape[2] != 3:
            raise ValueError(f"deep10: fromarray expects HxWx3, got {a.shape}")
        img = DeepImage((a.shape[1], a.shape[0]))
        # All three fromarray call sites are gradient functions computing
        # directly against MAXVAL, so the array is already 10-bit.
        img.a[:] = np.clip(a, 0, MAXVAL).astype(np.uint16)
        return img


class ImageDraw:
    """Module stand-in for PIL.ImageDraw."""
    @staticmethod
    def Draw(img):
        return DeepDraw(img)


class ImageOps:
    """Module stand-in for PIL.ImageOps."""
    @staticmethod
    def invert(img):
        """PIL's invert is a 256-entry LUT, i.e. 255-v, and refuses I;16.
        At 10 bits the correct operation is MAXVAL - v."""
        out = DeepImage(img.size)
        out.a = (MAXVAL - img.a.astype(np.int32)).clip(0, MAXVAL).astype(np.uint16)
        return out


ImageFont = _PILFont          # .load() on a .pil bitmap font is unchanged
