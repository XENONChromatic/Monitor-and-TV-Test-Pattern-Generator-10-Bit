#!/usr/bin/env python3
"""
Compare EVERY pixel of EVERY 10-bit pattern against Bill's 8-bit equivalent.

CRITERION, per pixel
  scale group     v10 must equal round(v8*1023/255) EXACTLY, with 235 snapped
                  to 940 (BT.709 legal white). Tolerance 0.
  gradient group  recomputed at the new depth, so compared against the
                  UNSNAPPED scale with tolerance 8. Measured basis: the 99th
                  percentile deviation is 4 across every gradient, and the
                  worst case is 7 in Color-Triangle-Wireframe, where Bill's
                  code truncates the interpolation twice.
  labels          a pixel drawn in one of the flat text colours, in either
                  image, is accepted. Printed labels now read 10-bit numbers
                  so their glyphs sit in different places.
  known variable  color-random-* (seed), banner (date), wipe-hs* (v1.0.2
                  changed the algorithm). Reported separately, never hidden.

Anything else is a DEFECT.
"""
import sys, os, json
import numpy as np, cv2

TOL_GRAD = 8
TEXT10 = np.array([(1023,1023,1023),(0,0,0),(1023,0,0),(0,1023,0)], np.int32)
SNAP = np.array([940 if v==235 else round(v*1023/255) for v in range(256)], np.int32)
PLAIN= np.array([round(v*1023/255) for v in range(256)], np.int32)

def is_grad(stem, n8):
    return n8 >= 200 or any(k in stem for k in ('Wipe','-Cont','Triangle','Random','Composite'))

def is_known(stem):
    return stem.startswith("Color-Random") or stem == "Banner" or stem.startswith("Wipe-Hs")

def main(dir8, dir10, out, prefix="FHD-1920x1080-"):
    rows=[]
    for f in sorted(x for x in os.listdir(dir8) if x.lower().endswith(".png")):
        stem=f[len(prefix):-4]
        a8=cv2.imread(os.path.join(dir8,f), cv2.IMREAD_UNCHANGED)[...,:3][...,::-1].astype(np.int32)
        a10=np.rint(cv2.imread(os.path.join(dir10,f), cv2.IMREAD_UNCHANGED)[...,:3][...,::-1]
                    .astype(np.float64)*1023/65535).astype(np.int32)
        n8=len(np.unique(a8)); grad=is_grad(stem,n8)
        # The legal-white snap applies only where 235 MEANS legal white: the
        # two functions that draw clipping and broadcast-target patterns.
        # Everywhere else 235 is an ordinary value and scales to 943.
        snapped = stem.startswith("Clipping-") or stem.startswith("Check-Clipping-Target")
        exp=(SNAP if (snapped and not grad) else PLAIN)[a8]
        d=np.abs(a10-exp)
        ok=(d<=(TOL_GRAD if grad else 0)).all(-1)
        for t in TEXT10:
            ok |= (a10==t).all(-1)
            ok |= (exp==t).all(-1)
        bad=~ok; n=int(bad.sum())
        r=dict(stem=stem, grad=grad, known=is_known(stem), px=int(bad.size),
               defect=n, maxdev=int(d.max()))
        if n:
            ys,xs=np.where(bad)
            r["bbox"]=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())]
            r["sample"]=[int(ys[0]),int(xs[0]),a8[ys[0],xs[0]].tolist(),
                         exp[ys[0],xs[0]].tolist(),a10[ys[0],xs[0]].tolist()]
        rows.append(r)
    json.dump(rows,open(out,"w"),indent=1)
    return rows

if __name__=="__main__":
    rows=main(*sys.argv[1:5])
    real=[r for r in rows if r["defect"] and not r["known"]]
    known=[r for r in rows if r["defect"] and r["known"]]
    print(f"patterns compared : {len(rows)}")
    print(f"pixels compared   : {sum(r['px'] for r in rows):,}")
    print(f"fully clean       : {len(rows)-len(real)-len(known)}")
    print(f"known-variable    : {len(known)}  (random seed / banner date / v1.0.2 wipe)")
    print(f"DEFECTS           : {len(real)}")
    for r in sorted(real,key=lambda r:-r["defect"]):
        s=r["sample"]
        print(f"  {r['stem']:<44} {r['defect']:>9,} px  bbox {r['bbox']}")
        print(f"      y{s[0]} x{s[1]}: 8-bit {s[2]} -> expected {s[3]}, got {s[4]}")
