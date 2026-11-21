"""1_placement.py src dst : retouches de placement autour de l'USB3320 (diviseur VIN_MES vers l'alimentation,
R1203, C1204, C1205) et dégagement du couloir ULPI ; vias +3V3 des broches 14 et 23 du PHY, verrouillées."""
import os, sys, pcbnew
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import router as R

src, dst = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(src)
c = R.Carte(b)
FM = pcbnew.FromMM
TM = pcbnew.ToMM
ULPI = R.ULPI
SIG = set(ULPI) | {'~{ULPI_RST}', 'VIN_MES'}

MOVES = {  # absolute mm, rotation
    'R1008': (154.0, 50.0, 180),
    'R1009': (150.8, 50.0, 180),
    'C1013': (152.2, 52.4, 0),
    'R1203': (106.5, 70.5, 90),
    'C1204': (106.6, 57.4, 0),
    'C1205': (101.75, 55.75, 180),
}
BOX = (97.0, 52.0, 121.0, 69.5)   # unlocked copper of any net removed here

removed = []
def rm(t):
    b.Remove(t); removed.append(t)

# 1. copper attached to the old pads of moved parts (fan-out vias, stubs), any lock state
old = []
for ref in MOVES:
    for p in c.fp[ref].Pads():
        old.append((p.GetNetCode(), p.GetEffectiveShape(pcbnew.F_Cu)))
gone = set()
for t in list(b.GetTracks()):
    for net, sh in old:
        if t.GetNetCode() == net and t.GetEffectiveShape(pcbnew.F_Cu).Collide(sh, FM(0.01)):
            gone.add(t.m_Uuid.AsString())
# plane vias at the far end of those stubs
ends = []
for t in b.GetTracks():
    if t.m_Uuid.AsString() in gone and t.GetClass() == 'PCB_TRACK':
        ends += [(t.GetNetCode(), t.GetStart()), (t.GetNetCode(), t.GetEnd())]
for t in list(b.GetTracks()):
    if t.GetClass() == 'PCB_VIA':
        for net, pt in ends:
            if t.GetNetCode() == net and (t.GetPosition() - pt).EuclideanNorm() < FM(0.05):
                gone.add(t.m_Uuid.AsString())
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString() in gone:
        rm(t)
n1 = len(removed)

# 2. moves
for ref, (x, y, r) in MOVES.items():
    f = c.fp[ref]
    f.SetOrientationDegrees(r)
    f.SetPosition(pcbnew.VECTOR2I(FM(x), FM(y)))
    print(ref, [(p.GetNumber(), p.GetNetname(), round(TM(p.GetPosition().x), 3), round(TM(p.GetPosition().y), 3)) for p in f.Pads()])

# 3. whole nets (ULPI, reset, VIN_MES), +VIN branch to the old divider, unlocked copper in BOX
def inbox(p):
    return BOX[0] < TM(p.x) < BOX[2] and BOX[1] < TM(p.y) < BOX[3]
for t in list(b.GetTracks()):
    n = t.GetNetname()
    if n in SIG:
        rm(t); continue
    pts = [t.GetPosition()] if t.GetClass() == 'PCB_VIA' else [t.GetStart(), t.GetEnd()]
    if n == '+VIN' and not t.IsLocked() and all(TM(p.x) < 176.0 for p in pts):
        rm(t); continue
    if not t.IsLocked() and any(inbox(p) for p in pts):
        rm(t)
print('removed', len(removed), '(attached to moved pads: %d)' % n1)

# 4. pre-placed power connections of the PHY (locked)
p23 = c.pad('U1202', 23)
v3 = p23.GetNet()
t = pcbnew.PCB_TRACK(b); t.SetStart(p23.GetPosition()); t.SetEnd(pcbnew.VECTOR2I(FM(98.65), FM(61.25)))
t.SetWidth(FM(0.2)); t.SetLayer(pcbnew.F_Cu); t.SetNet(v3); t.SetLocked(True); b.Add(t)
v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(FM(98.65), FM(61.25))); v.SetViaType(pcbnew.VIATYPE_THROUGH)
v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(FM(0.45)); v.SetDrill(FM(0.2)); v.SetNet(v3); v.SetLocked(True); b.Add(v)
p14 = c.pad('U1202', 14)
c5 = [p for p in c.fp['C1205'].Pads() if p.GetNetname() == '+3V3'][0]
print('C1205 +3V3 pad', TM(c5.GetPosition().x), TM(c5.GetPosition().y))
t = pcbnew.PCB_TRACK(b); t.SetStart(p14.GetPosition())
t.SetEnd(pcbnew.VECTOR2I(FM(101.1), FM(56.75)))
t.SetWidth(FM(0.2)); t.SetLayer(pcbnew.F_Cu); t.SetNet(v3); t.SetLocked(True); b.Add(t)
v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(FM(101.1), FM(56.75))); v.SetViaType(pcbnew.VIATYPE_THROUGH)
v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(FM(0.45)); v.SetDrill(FM(0.2)); v.SetNet(v3); v.SetLocked(True); b.Add(v)

R.remplir(b)
pcbnew.SaveBoard(dst, b)
print('saved', dst)
