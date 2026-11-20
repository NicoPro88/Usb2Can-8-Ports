# Matériel

Deux cartes empilées (décision D3) :

| Dossier | Carte | Contenu |
|---|---|---|
| `can8-mere/` | Carte mère, 4 couches | STM32H723ZGT6, PHY USB3320 (USB HS), alimentation 9-36 V, ports CAN 1 à 4 |
| `can8-fille/` | Carte fille | ports CAN 5 à 8, reliée par un connecteur 2 × 20 |
| `bibliotheque/` | | symboles absents de la bibliothèque KiCad (USB3320C, ISO1042, UCC12050, MCP2518FD SOIC) |
| `outils/` | | générateur des schémas et vérification de la netlist |

Chaque projet contient le schéma KiCad (`.kicad_pro`, `.kicad_sch`), un export PDF (`*-schema.pdf`) et la nomenclature (`*-nomenclature.csv`).
Le schéma-bloc, l'affectation des broches et les points à vérifier sont dans [`docs/schema-bloc.md`](../docs/schema-bloc.md).

## État : v0.2 (vérifications faites, avant placement)

Les schémas ont été générés par `outils/generer_schemas.py`, qui décrit chaque carte sous forme de netlist (composant, broche, net) et la dessine en KiCad 7 (lisible par KiCad 8 et 9). `outils/verifier_netlist.py` relit la netlist exportée par `kicad-cli` et la compare à la description : 0 écart sur les deux cartes.

Le dessin est fonctionnel mais brut (étiquettes de nets sur chaque broche). Une fois le schéma validé, on le retouche directement dans KiCad ; le générateur ne doit alors plus être relancé.

```sh
# régénérer et vérifier (nécessite KiCad 7 : kicad-cli et kicad-symbols)
python3 hardware/outils/verifier_netlist.py
```

Les sorties de fabrication (Gerber, BOM, pick & place) iront dans `hardware/fab/` à chaque version publiée.
