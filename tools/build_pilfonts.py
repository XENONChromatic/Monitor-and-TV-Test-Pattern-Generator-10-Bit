#!/usr/bin/env python3
"""
Rebuild pilfonts/ - the bitmap fonts mk-patterns.py needs.

The upstream repository ships without pilfonts/ and its .gitignore does not
exclude them; they were simply never committed. Without them the generator
raises FileNotFoundError on the first pattern and writes nothing.

THE FONT
    -Adobe-Helvetica-Medium-R-Normal--20-140-100-100-P-100-ISO10646-1
    i.e. the X11 core bitmap Adobe Helvetica at 100 dpi. The 75 dpi set
    renders visibly too small and produces output that does NOT match the
    published patterns.

SOURCES (any one)
    Linux :  apt-get download xfonts-100dpi && dpkg-deb -x xfonts-100dpi*.deb f/
    macOS :  the XQuartz installer package, WITHOUT installing it:
                 brew fetch --cask xquartz          # or download the .pkg
                 pkgutil --expand <pkg> exp
                 cat exp/XQuartzComponent.pkg/Payload | gunzip -dc | cpio -id
                 # fonts land in opt/X11/share/fonts/100dpi/

    Point this script at whichever directory holds helvR*.pcf.gz.

These fonts are Copyright (c) 1984, 1987 Adobe Systems Incorporated and
Copyright (c) 1988, 1991 Digital Equipment Corporation. They are NOT committed
to this repository, matching upstream.
"""
import sys, gzip, shutil, os, pathlib
from PIL import PcfFontFile

SIZES = ("08", "10", "12", "14", "18", "24")

def main(src, dst="pilfonts"):
    pathlib.Path(dst).mkdir(exist_ok=True)
    for s in SIZES:
        g = os.path.join(src, f"helvR{s}.pcf.gz")
        if not os.path.exists(g):
            sys.exit(f"missing {g} - is this the 100dpi directory?")
        tmp = f"/tmp/_helvR{s}.pcf"
        with gzip.open(g, 'rb') as fi, open(tmp, 'wb') as fo:
            shutil.copyfileobj(fi, fo)
        with open(tmp, 'rb') as fi:
            f = PcfFontFile.PcfFontFile(fi)
            res = f.info.get(b'RESOLUTION_X', b'?').decode()
            if res != '100':
                sys.exit(f"helvR{s}.pcf reports RESOLUTION_X={res}, expected 100")
            f.save(os.path.join(dst, f"helvR{s}.pil"))
        print(f"  helvR{s}.pil")
    print(f"wrote {len(SIZES)} fonts to {dst}/")

if __name__ == '__main__':
    main(*sys.argv[1:])
