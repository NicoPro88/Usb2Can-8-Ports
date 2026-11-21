# Retouches de la carte mère (v0.3, deuxième passe)

Ces scripts ont terminé la carte mère après le routage automatique (voir [`docs/routage.md`](../../../docs/routage.md) § 4). Ils ont été appliqués **une seule fois, dans l'ordre ci-dessous**, à partir de la carte routée de la première passe v0.3 (avant `finir`). Ils sont gardés comme trace : les positions sont écrites en dur, ils ne se relancent pas sur une autre carte.

Chaque carte intermédiaire doit s'appeler `can8-mere.kicad_pcb` et se trouver à côté de `can8-mere.kicad_pro` et `can8-mere.kicad_dru`. Sinon pcbnew remplit les plans avec les règles par défaut (isolement de 1 mm du châssis oublié, par exemple).

| Étape | Commande | Effet |
|---|---|---|
| 1 | `1_placement.py src dst` | Diviseur VIN_MES (R1008, R1009, C1013) déplacé près de l'alimentation ; R1203, C1204, C1205 déplacés autour de l'USB3320 ; cuivre non verrouillé retiré dans le couloir PHY → STM32 ; vias +3V3 des broches 14 et 23 du PHY |
| 2 | `2_bus_ulpi.py src dst 2_ordre_ulpi.txt 1 0` | Les 12 lignes ULPI tirées sur la grille (F.Cu horizontal, B.Cu vertical), verrouillées |
| 3 | `3_interruptions.py src dst` | ~INT1, ~INT2, ~INT3 sur PG0, PG1, PA11 (broches 56, 57, 103) |
| 4 | `ROUTAGE_CARTE=… ROUTAGE_DOSSIER=… router.py completer can8-mere` | 43 → 7 liaisons manquantes |
| 5 | `4_reprises.py src dst` | Découplage du STM32 (broches 38, 39, 61, C1104), PHY_VBUS, C1204 : 7 → 3 |
| 6 | `router.py completer can8-mere` | Rien de plus (3) |
| 7 | `5_reset_phy.py src dst` | ~ULPI_RST : 3 → 2 |
| 8 | `6_liaison.py carte '~{CS3}' U1101 80 140.2 101.6` puis `6_liaison.py carte SPI1_SCK R1104 2 106.62 100.73` | 2 → 0 |
| 9 | `7_ulpi_d7.py carte` | Bout de ULPI_D7 raccourci |
| 10 | `router.py finir can8-mere`, DRC avec parité, `exporter.sh v0.3 can8-mere` | Plans externes, couture, sérigraphie, sorties de fabrication |

Le schéma suit le même changement d'interruptions : `generer_schemas.py` (broches 56, 57, 103), puis `mcu.kicad_sch` régénéré. La parité schéma / circuit du DRC est à 0 écart.
