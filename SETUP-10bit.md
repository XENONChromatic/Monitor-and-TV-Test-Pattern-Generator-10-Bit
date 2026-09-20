# 10-bit fork - setup

Generates the 206 patterns as **10-bit** values (codes 0-1023) written to
16-bit TIFF or PNG, instead of 8-bit.

## What was added

| Path | Purpose |
|---|---|
| `deep10/` | drawing layer presenting PIL's API over a 10-bit numpy buffer |
| `deep10/core.py` | `DeepImage`, `DeepDraw` - mask-based rendering |
| `deep10/writer.py` | 16-bit RGB output via OpenCV |
| `tools/build_pilfonts.py` | rebuild the bitmap fonts the generator needs |
| `tools/compare_all.py` | per-pixel comparison of a whole set against Bill's |

## What changed in `mk-patterns.py`

81 lines of 2751 (2.9%), across 22 drawing functions. No functions added,
removed, renamed or reordered. The edits fall into seven kinds:

| kind | lines | what it does |
|---|---|---|
| `MAXVAL` for the literal 255 | 32 | the ceiling becomes 1023 |
| `r10(...)` | 24 | marks a value as ALREADY 10-bit, so the shim does not scale it again |
| `lab(...)` | 8 | the printed label reads the 10-bit number |
| `snap_legal(True/False)` | 4 | guards `mk_targets` and `mk_clipping`, the only two functions where 235 means BT.709 narrow white and must become 940 rather than the scaled 943 |
| `scale8(...)` | 3 | a threshold or constant that has to move with the depth, e.g. Bill's `> 128` |
| imports | 3 | the shim and the writer |
| writer | 1 | 16-bit PNG out |

Everything else is untouched, including his imports of numpy and PIL.

## Why PIL alone will not do this

PIL has no colour mode above 8 bits. Its deep modes (`I;16`, `I`, `F`) are
single channel, and drawing onto an `I;16` image is not safe:

    paste(1023, box, mask)  stores 65535
    bitmap text             stores 0 / 255 / 65280 / 65535, wrong geometry

So `deep10` renders every call through PIL into an 8-bit mode `L` mask and
writes the 10-bit colour through that mask with numpy. Because the mask comes
from the same rasteriser the 8-bit generator uses, **geometry is identical by
construction** - measured at 0 differing pixels for line, rectangle, ellipse,
polygon and bitmap text.

PIL also cannot write 16-bit RGB at all, so output goes through OpenCV. OpenCV
is used rather than OpenImageIO because OIIO writes `sRGB`, `gAMA`, `cHRM` and
`eXIf` chunks that make readers transform the values: Photoshop showed 27042
where the file held 60218. cv2 emits IHDR+IDAT+IEND only, matching Bill's.

## Install

    python3 -m venv .venv && .venv/bin/pip install numpy Pillow opencv-python-headless

Licences: numpy BSD-3, Pillow MIT-CMU, OpenCV Apache-2.0.

## Build

    python3 tools/build_pilfonts.py <dir containing helvR*.pcf.gz>
    python3 mk-patterns.py -o OUT -c png -x 1920 -y 1080 -u FHD
    python3 mk-patterns.py -o OUT -c png -x 3840 -y 2160 -u UHD

Only `png` and `tif` are accepted. The other twelve formats in `-c` cannot
carry 16 bits; `gif` in particular writes without error and reads back zero.
Bill publishes PNG only, so PNG is what the sets use.

`-u` carries the family name straight into the file names, so it must be the
same string Bill uses (`FHD`, `UHD`) for the names to match his set.

## Verifying

    DEEP10_MAXVAL=255 python3 mk-patterns.py -o CTL -c png -x 3840 -y 2160 -u UHD

With `DEEP10_MAXVAL=255` the shim is an identity and the patched generator must
reproduce the unmodified upstream output. Measured at UHD: 195/206 files
pixel-identical to a pristine v1.0.2 build, the other 11 being the 10
random-seed patterns and the banner timestamp. This control is what caught the
`> 128` threshold bug, which the 10-bit comparison could not see.

    python3 tools/compare_all.py <bill dir> <10-bit dir> out.json UHD-3840x2160-

## Value rules

| Kind | Rule | Example |
|---|---|---|
| Legal-range anchors | defined by BT.709 at the new depth | 16 -> 64, 235 -> 940 |
| Container ceiling | x 1023/255 | 255 -> 1023 |
| Clipping patch step | x4 | step 1 -> step 4, so 64 and 940 land on a patch |
| Discrete patch value | scale the 8-bit result, do not recompute | 28 -> 112, not 115 |
| Everything computed | recomputed against MAXVAL=1023 | ramps gain 1024 steps |
| `#rrggbb` literals | x 1023/255 | `#ffffff` -> 1023 |

Files are stored **full-scale expanded**, `code * 65535 / 1023`. Raw 10-bit
codes in a 16-bit container would put white at 1.56% of full scale and read as
near-black. The expansion round-trips exactly for all 1024 codes.

## File names

Identical to the 8-bit set. Where a value appears in a file name
(`swatch-rgb-fix-red-255-...`, `wipe-rgb-fix-blue-127-...`) the name keeps the
8-bit number while the pixels carry the 10-bit value.
