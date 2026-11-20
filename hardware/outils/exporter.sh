#!/bin/sh
# Sorties de fabrication et de revue des deux cartes (KiCad 9, kicad-cli).
#
#   sh hardware/outils/exporter.sh [version [carte ...]]   (par défaut : v0.3, les deux cartes)
#
# Écrit dans hardware/fab/<version>/<carte>/ :
#   gerbers/ + perçages (Excellon) et leur archive <carte>-gerbers.zip (seulement si le DRC ne
#   trouve aucune liaison manquante),
#   <carte>-nomenclature.csv, <carte>-placement-cms.csv (pick & place),
#   <carte>-schema.pdf, <carte>-pcb.pdf (une page par couche),
#   <carte>.step (modèle 3D, hors git), <carte>-dessus.png, <carte>-dessous.png, <carte>-3d.png (rendus).
set -e
VERSION=${1:-v0.3}
[ $# -gt 0 ] && shift
CARTES=${*:-can8-mere can8-fille}
HW=$(cd "$(dirname "$0")/.." && pwd)
for CARTE in $CARTES; do
    SRC="$HW/$CARTE"
    OUT="$HW/fab/$VERSION/$CARTE"
    rm -rf "$OUT"
    mkdir -p "$OUT/gerbers"
    PCB="$SRC/$CARTE.kicad_pcb"
    SCH="$SRC/$CARTE.kicad_sch"

    kicad-cli sch export pdf -o "$OUT/$CARTE-schema.pdf" "$SCH"
    kicad-cli sch export bom -o "$OUT/$CARTE-nomenclature.csv" \
        --fields 'Reference,Value,Footprint,${QUANTITY},${DNP}' \
        --labels 'Repères,Valeur,Empreinte,Quantité,Non monté' \
        --group-by 'Value,Footprint' --ref-range-delimiter '' "$SCH"

    # pas de Gerber pour une carte dont le routage n'est pas terminé (liaisons manquantes au DRC)
    kicad-cli pcb drc --format json --severity-error -o "$OUT/drc.json" "$PCB" >/dev/null
    MANQUANTES=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))['unconnected_items']))" "$OUT/drc.json")
    rm -f "$OUT/drc.json"
    if [ "$MANQUANTES" -gt 0 ]; then
        echo "$CARTE : $MANQUANTES liaisons manquantes, pas de Gerber ni de perçage" >&2
        rmdir "$OUT/gerbers"
        cat > "$OUT/A-LIRE.md" <<FIN
# $CARTE $VERSION : pas encore fabricable

Le routage n'est pas terminé : **$MANQUANTES liaisons restent à tirer** (DRC de KiCad, liaisons
manquantes ; détails dans docs/routage.md). Les fichiers Gerber et de perçage ne sont donc
volontairement pas fournis pour cette carte.

Une fois les liaisons terminées dans KiCad (DRC sans liaison manquante), régénérer les sorties :

    sh hardware/outils/exporter.sh $VERSION $CARTE

Les autres fichiers de ce dossier (schéma, vue PDF des couches, nomenclature, placement CMS,
rendus) correspondent à l'état actuel de la carte.
FIN
    else
    kicad-cli pcb export gerbers -o "$OUT/gerbers/" \
        -l F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts \
        --subtract-soldermask "$PCB"
    kicad-cli pcb export drill -o "$OUT/gerbers/" --format excellon --excellon-separate-th \
        --generate-map --map-format gerberx2 "$PCB"
    (cd "$OUT/gerbers" && zip -q -r "../$CARTE-gerbers.zip" .)
    fi
    kicad-cli pcb export pos -o "$OUT/$CARTE-placement-cms.csv" --format csv --units mm \
        --side both --smd-only "$PCB"

    # KiCad 9 : en mode multipage, -o est un dossier
    kicad-cli pcb export pdf -o "$OUT/pdf/" --mode-multipage --ibt \
        -l F.Cu,In1.Cu,In2.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Fab,B.Fab \
        --cl Edge.Cuts "$PCB"
    mv "$OUT/pdf/$CARTE.pdf" "$OUT/$CARTE-pcb.pdf" && rmdir "$OUT/pdf"
    kicad-cli pcb export step -o "$OUT/$CARTE.step" --subst-models --force "$PCB" >/dev/null

    kicad-cli pcb render -o "$OUT/$CARTE-dessus.png" --side top -w 2400 -h 1600 --zoom 1.6 \
        --quality high --background opaque "$PCB" >/dev/null
    kicad-cli pcb render -o "$OUT/$CARTE-dessous.png" --side bottom -w 2400 -h 1600 --zoom 1.6 \
        --quality high --background opaque "$PCB" >/dev/null
    kicad-cli pcb render -o "$OUT/$CARTE-3d.png" --side top --rotate '-45,0,30' --zoom 1.2 \
        -w 2400 -h 1600 --quality high --background opaque --perspective "$PCB" >/dev/null
    echo "$CARTE : sorties dans $OUT"
done
