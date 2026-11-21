"""2_bus_ulpi.py src dst ordres.txt fin(0/1) bouts_stm32(0/1) : bus ULPI tiré ligne par ligne sur la grille,
F.Cu de préférence horizontale et B.Cu verticale ; essaie chaque ordre du fichier et garde le meilleur.
Ordre retenu : 2_ordre_ulpi.txt, avec fin=1 (vias 0,45 / 0,2 mm) et bouts_stm32=0."""
import os, sys, time, random, pcbnew
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import router as R
from grille import Grille

src, dst = sys.argv[1], sys.argv[2]
listf = sys.argv[3]
fin, stmb = sys.argv[4] == "1", sys.argv[5] == "1"
SENS = {pcbnew.F_Cu: 'h', pcbnew.B_Cu: 'v'}

meilleur = None


def essai(ordre):
    b = pcbnew.LoadBoard(src)
    pads = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            pads.setdefault(p.GetNetname(), {})[fp.GetReference()] = p
    g = Grille(b, fin=fin)
    bouts = {}
    for nom in ordre:
        bouts[nom] = []
        for ref in ('U1202', 'U1101'):
            p = pads[nom][ref]
            t = None
            if nom == 'ULPI_D7' and ref == 'U1202':
                t = pcbnew.PCB_TRACK(b); t.SetStart(p.GetPosition())
                t.SetEnd(pcbnew.VECTOR2I(p.GetPosition().x, pcbnew.FromMM(54.3)))
                t.SetWidth(pcbnew.FromMM(0.2)); t.SetLayer(pcbnew.F_Cu); t.SetNet(p.GetNet()); b.Add(t); g.ajouter(t)
            elif ref == 'U1202':
                cote = abs(pcbnew.ToMM(p.GetPosition().x) - 104.44) < 0.01
                t = g.bout(p, longueur=1.2 if cote else 0.6)
            elif stmb:
                t = g.bout(p, longueur=0.6)
            if t is not None:
                t.SetLocked(True)
            bouts[nom].append(t or p)
    rates, long_ = [], 0.0
    for nom in ordre:
        a, c = bouts[nom]
        res = g.relier(a, c, [0.2], 0.15, marges=(4.0, 10.0), sens=SENS)
        if res:
            for t in res:
                t.SetLocked(True)
            long_ += sum(pcbnew.ToMM(t.GetLength()) for t in res if t.GetClass() == 'PCB_TRACK')
        else:
            rates.append(nom)
    return b, rates, long_


ordres = [l.strip().split(',') for l in open(listf) if l.strip()]
for k, ordre in enumerate(ordres):
    t0 = time.time()
    b, rates, L = essai(ordre)
    score = (len(rates), L)
    print('essai %d : %d ratées %s, %.0f mm (%.0fs) ordre=%s' % (k, len(rates), ' '.join(rates), L, time.time() - t0,
                                                                 ','.join(ordre)), flush=True)
    if meilleur is None or score < meilleur:
        meilleur = score
        R.remplir(b)
        pcbnew.SaveBoard(dst, b)
        print('  meilleur', score, flush=True)
    if not rates:
        break
print('FIN', meilleur)
