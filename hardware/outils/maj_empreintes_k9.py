#!/usr/bin/env python3
"""Passage des circuits imprimés v0.2 (KiCad 7) aux empreintes KiCad 9.

    python3 hardware/outils/maj_empreintes_k9.py      (API pcbnew de KiCad 9)

Pour chaque empreinte des deux cartes : recharge la version de la bibliothèque KiCad 9
(pastilles, sérigraphie, modèle 3D en ${KICAD9_3DMODEL_DIR}), à la même position, avec la
même face, la même orientation, la même référence, les mêmes champs, le même lien vers
le schéma et les mêmes nets. Les DB9 prennent le nom KiCad 9 de leur empreinte
(« DSUB-9_Pins_… » au lieu de « DSUB-9_Male_… », dessin identique).

Les trous de fixation suivent le symbole du schéma : présents dans la nomenclature
(champ « in_bom » du symbole MountingHole_Pad), absents du fichier de placement.

À ne lancer qu'une fois, sur les fichiers produits par placer.py (KiCad 7).
"""
import os
import sys

import pcbnew

HW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FP_DIR = os.environ.get('KICAD9_FOOTPRINT_DIR', '/usr/share/kicad/footprints')
RENOMMES = {
    'DSUB-9_Male_Horizontal_P2.77x2.84mm_EdgePinOffset9.90mm_Housed_MountingHolesOffset11.32mm':
        'DSUB-9_Pins_Horizontal_P2.77x2.84mm_EdgePinOffset9.90mm_Housed_MountingHolesOffset11.32mm',
}


def migrer(nom):
    chemin = os.path.join(HW, nom, nom + '.kicad_pcb')
    board = pcbnew.LoadBoard(chemin)
    anciens = list(board.GetFootprints())
    for old in anciens:
        fpid = old.GetFPID()
        lib = fpid.GetLibNickname().wx_str()
        name = RENOMMES.get(fpid.GetLibItemName().wx_str(), fpid.GetLibItemName().wx_str())
        new = pcbnew.FootprintLoad(os.path.join(FP_DIR, lib + '.pretty'), name)
        if new is None:
            sys.exit('%s : empreinte %s:%s introuvable' % (old.GetReference(), lib, name))
        new.SetFPID(pcbnew.LIB_ID(lib, name))
        # pastilles : mêmes numéros des deux côtés
        anc = {}
        for p in old.Pads():
            anc.setdefault(p.GetNumber(), p.GetNet())
        nouv = {p.GetNumber() for p in new.Pads()}
        if set(anc) != nouv:
            sys.exit('%s : pastilles différentes %s / %s' % (old.GetReference(), sorted(anc), sorted(nouv)))
        new.SetReference(old.GetReference())
        new.SetValue(old.GetValue())
        for f in old.GetFields():
            if f.IsReference() or f.IsValue() or f.GetName() == 'Footprint':
                continue
            if new.HasFieldByName(f.GetName()):
                new.GetFieldByName(f.GetName()).SetText(f.GetText())
            else:
                nf = pcbnew.PCB_FIELD(new, new.GetNextFieldId(), f.GetName())
                nf.SetText(f.GetText())
                nf.SetVisible(False)
                nf.SetLayer(new.Reference().GetLayer())
                new.AddField(nf)
        new.SetPath(old.GetPath())
        new.SetSheetname(old.GetSheetname())
        new.SetSheetfile(old.GetSheetfile())
        attrs = old.GetAttributes()
        if lib == 'MountingHole':
            attrs &= ~pcbnew.FP_EXCLUDE_FROM_BOM
        new.SetAttributes(attrs)
        board.Add(new)
        if old.GetLayer() == pcbnew.B_Cu:
            new.Flip(new.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        new.SetOrientation(old.GetOrientation())
        new.SetPosition(old.GetPosition())
        for p in new.Pads():
            p.SetNet(anc[p.GetNumber()])
        new.SetLocked(old.IsLocked())
        board.Remove(old)
    pcbnew.SaveBoard(chemin, board)
    print('%s : %d empreintes rechargées depuis la bibliothèque KiCad 9' % (nom, len(anciens)))


if __name__ == '__main__':
    # un processus par carte : un second LoadBoard dans le même processus échoue (KiCad 9.0.8)
    if len(sys.argv) > 1:
        migrer(sys.argv[1])
    else:
        import subprocess
        for n in ('can8-mere', 'can8-fille'):
            subprocess.run([sys.executable, os.path.abspath(__file__), n], check=True)
