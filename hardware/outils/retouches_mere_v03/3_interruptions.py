"""3_interruptions.py src dst : ~INT1, ~INT2, ~INT3 passent des broches 82, 85, 86 (PD13, PD14, PD15) aux
broches 56, 57, 103 (PG0, PG1, PA11) du STM32 ; même changement que dans generer_schemas.py."""
import sys, pcbnew
src, dst = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(src)
u = [f for f in b.GetFootprints() if f.GetReference() == 'U1101'][0]
pad = {p.GetNumber(): p for p in u.Pads()}
MOVES = {'~{INT1}': ('82', '56', 'PD13'), '~{INT2}': ('85', '57', 'PD14'), '~{INT3}': ('86', '103', 'PD15')}
for net, (old, new, nom) in MOVES.items():
    po, pn = pad[old], pad[new]
    ni = po.GetNet()
    assert ni.GetNetname() == net, (net, ni.GetNetname())
    # copper of the INT net touching the old pad
    for t in list(b.GetTracks()):
        if t.GetNetCode() == ni.GetNetCode() and t.GetEffectiveShape(pcbnew.F_Cu).Collide(
                po.GetEffectiveShape(pcbnew.F_Cu), pcbnew.FromMM(0.01)):
            print('remove', t.GetClass(), pcbnew.ToMM(t.GetStart().x) if t.GetClass() == 'PCB_TRACK' else '')
            b.Remove(t)
    nc = pcbnew.NETINFO_ITEM(b, 'unconnected-(U1101-%s-Pad%s)' % (nom, old))
    b.Add(nc)
    po.SetNet(nc)
    pn.SetNet(ni)
    print(net, old, '->', new)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(dst, b)
