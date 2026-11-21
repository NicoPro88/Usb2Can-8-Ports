"""5_reset_phy.py src dst : ~ULPI_RST sort de la broche 27 de l'USB3320 par une via sous la rangée de broches
(boucle +1V8_PHY des broches 28 et 30 resserrée), puis routage sur la grille jusqu'à R1203."""
import os, sys, pcbnew
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import router as R
from grille import Grille

src, dst = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(src)
c = R.Carte(b)
FM, TM = pcbnew.FromMM, pcbnew.ToMM
CORBEILLE = []
V18 = '/USB 2.0 High Speed /+1V8_PHY'


def V(x, y):
    return pcbnew.VECTOR2I(FM(x), FM(y))


def piste(n, pts, w=0.2, L=pcbnew.F_Cu):
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(V(x0, y0)); t.SetEnd(V(x1, y1)); t.SetWidth(FM(w)); t.SetLayer(L)
        t.SetNet(b.FindNet(n)); t.SetLocked(True); b.Add(t); out.append(t)
    return out


def via(n, x, y, d=0.45, trou=0.2):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(x, y)); v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(FM(d)); v.SetDrill(FM(trou)); v.SetNet(b.FindNet(n)); v.SetLocked(True); b.Add(v)
    return v


# 1. +1V8_PHY loop between pins 28 and 30, left leg moved right by 0.04 mm and kept above Y1201
k = 0
for t in list(b.GetTracks()):
    if t.GetNetname() != V18 or t.GetClass() != 'PCB_TRACK' or t.GetLayer() != pcbnew.F_Cu or t.IsLocked():
        continue
    p = [t.GetStart(), t.GetEnd()]
    if all(101.6 <= TM(q.x) <= 102.85 and 62.7 <= TM(q.y) <= 63.95 for q in p) and any(TM(q.x) < 102.7 for q in p):
        b.Remove(t); CORBEILLE.append(t); k += 1
print('boucle +1V8 : %d segments retirés' % k)
piste(V18, [(101.75, 62.6), (101.74, 63.3), (101.95, 63.7), (102.1, 63.85), (102.45, 63.85), (102.8, 63.5)], 0.15)

# 2. ~ULPI_RST: short stub from pin 27 to a via just below the pin row
rst = '~{ULPI_RST}'
piste(rst, [(101.25, 62.6), (101.23, 63.13)])
v = via(rst, 101.23, 63.13)

# 3. grid route from that via to R1203 pad 2
g = Grille(b, fin=True)
res = g.relier(v, c.pad('R1203', 2), [0.2, 0.15], 0.15, marges=(4.0, 10.0, 25.0))
print('~ULPI_RST', 'tirée' if res else 'ECHEC')
if res:
    for t in res:
        t.SetLocked(True)
    print('  %.1f mm, %d vias' % (sum(TM(t.GetLength()) for t in res if t.GetClass() == 'PCB_TRACK'),
                                  sum(1 for t in res if t.GetClass() == 'PCB_VIA')))
R.remplir(b)
pcbnew.SaveBoard(dst, b)
