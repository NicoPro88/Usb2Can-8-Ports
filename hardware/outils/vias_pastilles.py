"""Liste les vias posées dans une pastille CMS de leur propre net (via in pad).

    python3 hardware/outils/vias_pastilles.py hardware/can8-mere/can8-mere.kicad_pcb

Sans bouchage par le fabricant, la soudure d'une pastille percée peut fuir dans la via
à la refusion. Les vias thermiques sous une pastille centrale (EP) sont voulues.
"""
import sys
import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
vias = [t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA']
n = 0
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            continue
        L = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        forme = p.GetEffectivePolygon(L)
        for v in vias:
            if v.GetNetCode() == p.GetNetCode() and forme.Contains(v.GetPosition()):
                n += 1
                print('%-7s %-3s %-40s via %.2f mm en (%.2f, %.2f)' % (
                    f.GetReference(), p.GetNumber(), p.GetNetname(), pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)),
                    pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y)))
print('%d vias dans des pastilles' % n)
