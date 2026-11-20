# Matériel

Deux cartes empilées (décision D3) :

| Dossier | Carte | Contenu |
|---|---|---|
| `can8-mere/` | Carte mère, 4 couches | STM32H723ZGT6, PHY USB3320 (USB HS), alimentation 9-36 V, ports CAN 1 à 4 |
| `can8-fille/` | Carte fille, 4 couches | ports CAN 5 à 8, reliée par un connecteur 2 × 20 |
| `bibliotheque/` | | symboles absents de la bibliothèque KiCad (USB3320C, ISO1042, UCC12050, MCP2518FD SOIC) |
| `outils/` | | générateur des schémas, vérification de la netlist, placement, routage, sorties de fabrication |
| `fab/v0.3/` | | sorties de la v0.3 : nomenclature, placement CMS, PDF, rendus ; Gerber et perçages pour la carte fille seulement (le modèle STEP est régénéré par `outils/exporter.sh`, hors git) |

Chaque projet contient le schéma KiCad (`.kicad_pro`, `.kicad_sch`), un export PDF (`*-schema.pdf`), la nomenclature (`*-nomenclature.csv`), le circuit imprimé routé (`.kicad_pcb`, règles complémentaires dans `.kicad_dru`) et la vue PDF du placement v0.2 (`*-placement.pdf`). Les projets s'ouvrent dans **KiCad 9**.
Le schéma-bloc, l'affectation des broches et les points à vérifier sont dans [`docs/schema-bloc.md`](../docs/schema-bloc.md).

## État : v0.3, routage

4 couches, plans de masse et d'alimentation internes pleins. DRC de KiCad 9 sans erreur avec les règles du projet, parité schéma / circuit comprise, sur les deux cartes.

- **Carte fille** : routée à 100 %, sorties de fabrication complètes dans `fab/v0.3/can8-fille/`.
- **Carte mère** : routée sauf 10 liaisons, autour du PHY USB et du STM32. **Pas encore fabricable** : pas de Gerber tant que le DRC trouve une liaison manquante.

Méthode, résultats, liste des liaisons restantes, ce qui est vérifié et ce qui ne l'est pas : [`docs/routage.md`](../docs/routage.md).

```sh
# routage (KiCad 9 + Freerouting 2.5), voir docs/routage.md § 8
python3 hardware/outils/router.py preparer|importer|completer|finir|rapport can8-mere
# sorties de fabrication et rendus dans hardware/fab/v0.3/
sh hardware/outils/exporter.sh v0.3
```

## v0.2 : schémas et placement

Les schémas ont été générés par `outils/generer_schemas.py`, qui décrit chaque carte sous forme de netlist (composant, broche, net) et la dessine en KiCad 7 (lisible par KiCad 8 et 9). `outils/verifier_netlist.py` relit la netlist exportée par `kicad-cli` et la compare à la description : 0 écart sur les deux cartes.

Le dessin est fonctionnel mais brut (étiquettes de nets sur chaque broche). Une fois le schéma validé, on le retouche directement dans KiCad ; le générateur ne doit alors plus être relancé.

Le placement des deux cartes est généré par `outils/placer.py` : gros composants à des positions fixées, passifs placés automatiquement au plus près de leurs broches, contrôles des chevauchements, de la barrière d'isolement, de l'empilage des deux cartes et DRC de KiCad. Détails, images et points à valider : [`docs/placement.md`](../docs/placement.md).

```sh
# régénérer et vérifier (nécessite KiCad 7 : kicad-cli, kicad-symbols, kicad-footprints, module Python pcbnew)
python3 hardware/outils/verifier_netlist.py   # schémas + netlist
python3 hardware/outils/placer.py             # schémas + circuits imprimés placés
```

Les sorties de fabrication (Gerber, BOM, pick & place) sont dans `hardware/fab/<version>/`.
