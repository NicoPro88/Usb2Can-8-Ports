"""4_reprises.py src dst : reprises à la main après le routage automatique : doublons de pistes, C1204 hors de
la zone de l'USB3320, PHY_VBUS (via de la broche 23 décalée), éventail des broches 38, 39 et 61 du STM32,
via de masse de C1104."""
import os, sys, pcbnew
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import router as R

src, dst = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(src)
c = R.Carte(b)
FM, TM = pcbnew.FromMM, pcbnew.ToMM


def V(x, y):
    return pcbnew.VECTOR2I(FM(x), FM(y))


def net(n):
    ni = b.FindNet(n)
    assert ni is not None, n
    return ni


def piste(n, pts, w=0.2, L=pcbnew.F_Cu):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(V(x0, y0)); t.SetEnd(V(x1, y1)); t.SetWidth(FM(w)); t.SetLayer(L)
        t.SetNet(net(n)); t.SetLocked(True); b.Add(t)


def via(n, x, y, d=0.45, trou=0.2):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(x, y)); v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(FM(d)); v.SetDrill(FM(trou)); v.SetNet(net(n)); v.SetLocked(True); b.Add(v)
    return v


def pts(t):
    return [t.GetPosition()] if t.GetClass() == 'PCB_VIA' else [t.GetStart(), t.GetEnd()]


CORBEILLE = []


def retirer(n, x0, y0, x1, y1, tous=False, quoi=None):
    k = 0
    for t in list(b.GetTracks()):
        if t.GetNetname() != n or (t.IsLocked() and not tous):
            continue
        if quoi and t.GetClass() != quoi:
            continue
        if any(x0 <= TM(p.x) <= x1 and y0 <= TM(p.y) <= y1 for p in pts(t)):
            b.Remove(t); CORBEILLE.append(t); k += 1
    return k


# 0. exact duplicates left by the completer (same layer, net, width, ends in either order)
vus, dup = set(), 0
for t in list(b.GetTracks()):
    if t.GetClass() != 'PCB_TRACK':
        continue
    a, e = (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)
    k = (t.GetLayer(), t.GetNetCode(), t.GetWidth(), min(a, e), max(a, e))
    if k in vus and not t.IsLocked():
        b.Remove(t); CORBEILLE.append(t); dup += 1
    vus.add(k)
print('doublons retirés', dup)

# 1. C1204 clear of the USB3320 courtyard; +3V3 stub lengthened, GND via out of the pad
f = c.fp['C1204']
f.SetPosition(V(106.75, 57.4))
print('C1204 retirés', retirer('+3V3', 104.6, 57.3, 105.6, 57.6), retirer('GND', 107.7, 57.1, 108.3, 57.4))
piste('+3V3', [(105.975, 57.4), (105.45, 57.45), (104.65, 57.45)], 0.3)
piste('GND', [(107.525, 57.4), (108.45, 57.4)], 0.3)
via('GND', 108.45, 57.4, 0.6, 0.3)

# 2. PHY_VBUS: pin 23 via moved down-right, RBIAS via reduced, track pin 22 -> R1201
print('via 23 retirée', retirer('+3V3', 98.6, 61.2, 99.6, 61.3, tous=True))
piste('+3V3', [(99.562, 61.25), (98.7, 61.35)])
via('+3V3', 98.7, 61.35)
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA' and t.GetNetname().endswith('/RBIAS'):
        t.SetWidth(FM(0.45)); t.SetDrill(FM(0.2))
piste('/USB 2.0 High Speed /PHY_VBUS', [(99.562, 60.75), (98.15, 60.8), (98.15, 61.6)])

# 3. STM32 pins 38 (GND) / 39 (+3V3): fan-out inside the package
print('éventail 38 retiré', retirer('GND', 121.9, 56.6, 124.0, 58.4))
piste('GND', [(121.6, 56.75), (122.0, 56.75), (122.75, 56.95)])
via('GND', 122.75, 56.95)
piste('+3V3', [(121.6, 57.25), (122.2, 57.25), (122.95, 57.85)])
via('+3V3', 122.95, 57.85)

# 4. C1104 GND pad: plane via between the pad and ULPI_DIR
piste('GND', [(119.25, 55.725), (119.95, 55.45)], 0.25)
via('GND', 119.95, 55.45)

# 5. STM32 pin 61 (GND): plane via on the outer side, pin 62 -> C1106 track moved down
print('61/62 retirés', retirer('GND', 120.5, 68.1, 120.7, 68.3), retirer('+3V3', 119.2, 68.7, 120.7, 68.8))
piste('GND', [(120.9, 68.25), (120.2, 68.22)])
via('GND', 120.2, 68.22)
piste('+3V3', [(120.9, 68.75), (120.45, 68.8), (119.4, 68.8)], 0.2)

R.remplir(b)
pcbnew.SaveBoard(dst, b)
print('saved', dst)
