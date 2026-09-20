"""
deep10.core - a 10-bit drawing layer presenting PIL's API.

WHY THIS EXISTS
    PIL has no >8-bit colour mode. Its deep modes (I;16, I, F) are single
    channel, and drawing text or pasting onto an I;16 image corrupts values
    (measured: paste(1023) stores 65535; bitmap text stores 0/255/65280/65535).

HOW IT WORKS
    The pixel buffer is a numpy uint16 array holding 10-bit codes (0..1023).
    Every drawing call is rendered by PIL itself into an 8-bit mode 'L' mask,
    then the 10-bit colour is written through that mask with numpy.

    Because the mask comes from the same PIL rasteriser the 8-bit generator
    uses, geometry is identical by construction. Measured on line, rectangle,
    ellipse, polygon and bitmap text: 0 differing pixels.

COLOUR CONVENTION
    The generator keeps its original 8-bit arithmetic. Colours arriving here
    are 0..255 and are scaled by 1023/255, which is injective (256 distinct in,
    256 distinct out, so step counts are preserved) and round-trips exactly:
    round(round(v*1023/255)*255/1023) == v for all 256 values. Scaled patterns
    therefore read identically to Bill's on an 8-bit scope.

    The exception is legal white. 235 scales to 943, but BT.709 legal white at
    10 bits is 940, so 235 is snapped to 940. That one value reads 234 rather
    than 235 on an 8-bit scope; it is the only value where the two rules
    disagree.

    Continuous gradients are the other exception. Those saturate all 256 codes
    at 8 bits, so scaling would leave an 8-bit ramp in a 10-bit file. Their
    functions compute against MAXVAL directly and wrap the result in raw10(),
    which bypasses the scaling here.
"""
import os
import numpy as np
from PIL import Image as _PILImage, ImageDraw as _PILDraw, ImageFont as _PILFont

# Settable so the whole chain can be run at 8 bits as a positive control:
# with DEEP10_MAXVAL=255 the shim becomes an identity and the generator must
# reproduce Bill's published files exactly. If it does not, the shim is wrong.
MAXVAL = int(os.environ.get("DEEP10_MAXVAL", 1023))
SRCMAX = 255           # the depth the original source was written for
LEGAL_WHITE_8, LEGAL_WHITE_10 = 235, 940


class raw10(int):
    """Marks a value as already being in 0..MAXVAL, so it is not scaled."""
    __slots__ = ()


_SNAP = False


def snap_legal(on):
    """Enable the legal-white snap for the patterns where 235 MEANS legal
    white, i.e. the clipping and broadcast-target patterns. Elsewhere 235 is
    an ordinary value - a step in Color-Step-Lin-Gray, for instance - and must
    scale to 943 like everything else, or it reads 234 on an 8-bit scope."""
    global _SNAP
    _SNAP = bool(on)


def scale8(v):
    """8-bit source value -> 10-bit. Exact at 0 -> 0 and 255 -> 1023."""
    v = int(v)
    if MAXVAL == SRCMAX:
        return v                     # 8-bit control mode: identity
    if _SNAP and v == LEGAL_WHITE_8:
        return LEGAL_WHITE_10        # 943 by arithmetic; BT.709 says 940
    return int(round(v * MAXVAL / SRCMAX))


def _clamp(v):
    """PIL clamps out-of-range ink values rather than wrapping.
    Measured on 8-bit RGB: -108 -> 0, -1 -> 0, 256 -> 255, 300 -> 255.
    The generator relies on this: mk_color_triangle_solid computes negative
    values for points outside the triangle."""
    return 0 if v < 0 else (MAXVAL if v > MAXVAL else int(v))


def _parse(color):
    """Return an (r,g,b) tuple of clamped 10-bit ints."""
    if color is None:
        return None
    if isinstance(color, str):
        s = color.lstrip('#')
        if len(s) == 3:
            s = ''.join(c * 2 for c in s)
        return tuple(scale8(int(s[i:i + 2], 16)) for i in (0, 2, 4))
    if isinstance(color, (int, np.integer)):
        v = int(color) if isinstance(color, raw10) else scale8(_clamp8(color))
        return (_clamp(v),) * 3
    t = tuple((int(x) if isinstance(x, raw10) else scale8(_clamp8(x))) for x in color)
    if len(t) == 1:
        t = t * 3
    return tuple(_clamp(v) for v in t[:3])


def _clamp8(v):
    """PIL clamps out-of-range ink before use; do the same in 8-bit space."""
    v = int(v)
    return 0 if v < 0 else (SRCMAX if v > SRCMAX else v)


def _pairs(xy):
    """Flatten any of PIL's accepted xy forms into a list of (x,y).

    PIL accepts (x0,y0,x1,y1), ((x0,y0),(x1,y1)), [(x,y),...] and mixtures.
    Flattening uniformly avoids having to guess which form a caller used."""
    if xy is None:
        return []
    flat = []
    for e in (xy if isinstance(xy, (list, tuple, np.ndarray)) else [xy]):
        if isinstance(e, (list, tuple, np.ndarray)):
            flat.extend(e)
        else:
            flat.append(e)
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat) - 1, 2)]


def _bbox_of(xy, pad):
    """A superset of the region a draw call will touch, from its coordinates.
    Without this every call would getbbox() the whole frame, which is ruinous
    for the per-pixel d.point() loop in mk_color_triangle_solid."""
    pts = _pairs(xy)
    if not pts:
        return None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (int(min(xs)) - pad, int(min(ys)) - pad,
            int(max(xs)) + pad + 1, int(max(ys)) + pad + 1)


class DeepImage:
    """Stands in for PIL.Image.Image. Holds HxWx3 uint16 of 10-bit codes."""
    __slots__ = ('a', 'size', '_mask', '_mdraw')

    def __init__(self, size, color=None):
        w, h = int(size[0]), int(size[1])
        self.size = (w, h)
        self.a = np.zeros((h, w, 3), np.uint16)
        if color is not None:
            self.a[:] = _parse(color)
        self._mask = None
        self._mdraw = None

    def _scratch(self):
        """A persistent mode 'L' scratch mask and its ImageDraw."""
        if self._mask is None:
            self._mask = _PILImage.new('L', self.size, 0)
            self._mdraw = _PILDraw.Draw(self._mask)
        return self._mask, self._mdraw

    def _apply(self, color, hint=None):
        """Write `color` wherever the scratch mask is non-zero, then clear it.

        `hint` is a superset of the region the caller drew into, derived from
        the draw coordinates. Without it every call would getbbox() the whole
        frame, which is ruinous for the per-pixel d.point() loop in
        mk_color_triangle_solid (up to 2,073,600 calls at 1920x1080)."""
        mask, _ = self._scratch()
        w, h = self.size
        if hint is not None:
            hx0, hy0, hx1, hy1 = hint
            hx0, hy0 = max(hx0, 0), max(hy0, 0)
            hx1, hy1 = min(hx1, w), min(hy1, h)
            if hx1 <= hx0 or hy1 <= hy0:
                return
            sub = mask.crop((hx0, hy0, hx1, hy1))
            b = sub.getbbox()
            if b is None:
                return
            box = (hx0 + b[0], hy0 + b[1], hx0 + b[2], hy0 + b[3])
        else:
            box = mask.getbbox()
        if box is None:
            return
        x0, y0, x1, y1 = box
        sub = np.asarray(mask.crop(box))
        self.a[y0:y1, x0:x1][sub > 0] = _parse(color)
        self._mdraw.rectangle(box_to_xy(box), fill=0)   # clear only what was dirtied

    def paste(self, src, box, mask=None):
        """Two forms are used by the generator:
             paste(colour_tuple, (x,y), mask)  - stencil a flat colour, 2 sites
             paste(DeepImage,    (x,y))        - blit a sub-image, 9 sites
        Both clip at the target edges, as PIL's paste does."""
        x, y = int(box[0]), int(box[1])
        h, w = self.a.shape[:2]

        if isinstance(src, DeepImage):
            sw, sh = src.size
            x0, y0 = max(x, 0), max(y, 0)
            x1, y1 = min(x + sw, w), min(y + sh, h)
            if x1 <= x0 or y1 <= y0:
                return
            patch = src.a[y0 - y:y1 - y, x0 - x:x1 - x]
            if mask is None:
                self.a[y0:y1, x0:x1] = patch
            else:
                m = np.asarray(mask.convert('L'))[y0 - y:y1 - y, x0 - x:x1 - x]
                self.a[y0:y1, x0:x1][m > 0] = patch[m > 0]
            return

        if mask is None:
            raise NotImplementedError("deep10: paste of a flat colour with no mask is unused here")
        mw, mh = mask.size
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + mw, w), min(y + mh, h)
        if x1 <= x0 or y1 <= y0:
            return
        m = np.asarray(mask.convert('L'))[y0 - y:y1 - y, x0 - x:x1 - x]
        self.a[y0:y1, x0:x1][m > 0] = _parse(src)

    def copy(self):
        n = DeepImage(self.size)
        n.a = self.a.copy()
        return n

    def to_array(self):
        return self.a


def box_to_xy(box):
    """PIL getbbox() is exclusive at x1,y1; rectangle() is inclusive."""
    x0, y0, x1, y1 = box
    return [(x0, y0), (x1 - 1, y1 - 1)]


class DeepDraw:
    """Stands in for PIL.ImageDraw.ImageDraw."""
    __slots__ = ('img',)

    def __init__(self, img):
        self.img = img

    def _stroke(self, method, color, hint, *args, **kw):
        """Render through PIL's own rasteriser into an 8-bit mask, then write
        the 10-bit colour through it. kw may carry outline=/width= for the
        outline-only forms, in which case fill= is not passed."""
        _, md = self.img._scratch()
        if 'outline' not in kw:
            kw['fill'] = 255
        getattr(md, method)(*args, **kw)
        self.img._apply(color, hint)

    # --- the primitives the generator uses ----------------------------------
    def line(self, xy, fill=None, width=1, **kw):
        self._stroke('line', fill, _bbox_of(xy, width + 2), xy, width=width)

    def point(self, xy, fill=None):
        """Written straight into the array: no mask, no scan.
        mk_color_triangle_solid calls this once per pixel."""
        pts = _pairs(xy)
        a = self.img.a
        h, w = a.shape[:2]
        col = _parse(fill)
        for x, y in pts:
            x, y = int(x), int(y)
            if 0 <= x < w and 0 <= y < h:
                a[y, x] = col

    def polygon(self, xy, fill=None, outline=None):
        hint = _bbox_of(xy, 2)
        if fill is not None:
            self._stroke('polygon', fill, hint, xy)
        if outline is not None:
            self._stroke('line', outline, hint, list(xy) + [xy[0]])

    def text(self, xy, text, fill=None, font=None, **kw):
        _, md = self.img._scratch()
        bb = md.textbbox(xy, text, font)
        hint = (int(bb[0]) - 2, int(bb[1]) - 2, int(bb[2]) + 3, int(bb[3]) + 3)
        self._stroke('text', fill, hint, xy, text, font=font)

    def rectangle(self, xy, fill=None, outline=None, width=1):
        hint = _bbox_of(xy, width + 2)
        if fill is not None:
            self._stroke('rectangle', fill, hint, xy)
        if outline is not None:
            self._stroke('rectangle', outline, hint, xy, outline=255, width=width)

    def ellipse(self, xy, fill=None, outline=None, width=1):
        hint = _bbox_of(xy, width + 2)
        if fill is not None:
            self._stroke('ellipse', fill, hint, xy)
        if outline is not None:
            self._stroke('ellipse', outline, hint, xy, outline=255, width=width)

    def textbbox(self, xy, text, font=None, **kw):
        _, md = self.img._scratch()
        return md.textbbox(xy, text, font)
