"""6_liaison.py carte net réf broche x y : relie une pastille au cuivre du même net le plus proche de (x, y),
par la grille ; la carte est modifiée en place. Utilisé pour ~CS3 (U1101 80) et SPI1_SCK (R1104 2)."""
import os, sys, time, pcbnew
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import router as R
from grille import Grille
src, nom, ref, num, x, y = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5]), float(sys.argv[6])
b = pcbnew.LoadBoard(src)
c = R.Carte(b)
pa = c.pad(ref, num)
assert pa.GetNetname() == nom
P = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
cand = [t for t in b.GetTracks() if t.GetNetname() == nom]
cible = min(cand, key=lambda t: (t.GetPosition() - P).EuclideanNorm() if t.GetClass() == 'PCB_VIA' else
            min((t.GetStart() - P).EuclideanNorm(), (t.GetEnd() - P).EuclideanNorm()))
print('cible', cible.GetClass(), b.GetLayerName(cible.GetLayer()))
for fin in (False, True):
    g = Grille(b, fin=fin)
    t0 = time.time()
    res = g.relier(pa, cible, [0.2, 0.15], 0.15, marges=(4.0, 12.0, 30.0, 60.0))
    print('fin', fin, 'ok' if res else 'ECHEC', '%.0fs' % (time.time() - t0), flush=True)
    if res:
        for t in res: t.SetLocked(True)
        print('  %.1f mm, %d vias' % (sum(pcbnew.ToMM(t.GetLength()) for t in res if t.GetClass() == 'PCB_TRACK'),
                                      sum(1 for t in res if t.GetClass() == 'PCB_VIA')))
        R.remplir(b); pcbnew.SaveBoard(src, b); break
