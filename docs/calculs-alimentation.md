# Calculs de l'alimentation 9-36 V -> 5 V (TPS54360)

Les équations et constantes viennent de la datasheet TI TPS54360 (SLVSBB4G), section 8.2 « Detailed Design Procedure ». Le même calcul refait avec les données de l'exemple de la datasheet redonne bien ses valeurs (13 kohms, 6,4 nF, 39 pF), ce qui valide les formules utilisées ici.

## Cahier des charges

| Paramètre | Valeur |
|---|---|
| Entrée | 9 à 36 V (démarrage à 8 V, arrêt à 6,25 V) |
| Sortie | 5 V, 2 A de dimensionnement (≈ 1,5 A au pire estimé, voir D4) |
| Fréquence | 500 kHz |
| Constantes TPS54360 | VREF = 0,8 V, gmea = 350 µA/V, gmps = 12 A/V, temps de conduction minimal 135 ns |

## Fréquence de découpage

- RT = 200 kohms donne 500 kHz (tableau des caractéristiques : 450 / 500 / 550 kHz à RT = 200 kohms).
- Temps de conduction à 36 V : D = 5,5 / 36 ≈ 0,15, soit ton ≈ 0,15 / 500 kHz ≈ 306 ns, supérieur aux 135 ns minimum. Pas de saut d'impulsions à 36 V.

## Seuil de démarrage (UVLO, broche EN)

Les valeurs de l'exemple de la datasheet conviennent telles quelles : 523 kohms entre VIN et EN, 84,5 kohms entre EN et la masse, pour un démarrage à 8 V et un arrêt à 6,25 V. La carte reste donc arrêtée tant que l'entrée est trop basse pour un fonctionnement correct, et l'hystérésis évite les oscillations au démarrage.

## Tension de sortie

R haut = 53,6 kohms, R bas = 10,2 kohms : VOUT = 0,8 × (1 + 53,6 / 10,2) = 5,0 V.

## Inductance

- Lmin = (VINmax − VOUT) / (IOUT × KIND) × VOUT / (VINmax × fsw), avec KIND = 0,3 (condensateurs céramiques).
- Lmin = (36 − 5) / (2 × 0,3) × 5 / (36 × 500 kHz) ≈ 14,4 µH, d'où **15 µH**.
- Ondulation à 36 V : (36 − 5) × (5 / 36) / (15 µH × 500 kHz) ≈ 0,57 A crête à crête.
- Courant crête en fonctionnement : 2 + 0,29 ≈ 2,3 A. Pour la robustesse, la saturation doit dépasser la limite de courant du TPS54360 (5,5 A nominal) : **Isat ≥ 6 A, Irms ≥ 3 A**, blindée, environ 10 × 10 mm.

## Condensateurs de sortie

Deux 47 µF 10 V céramiques X5R/X7R, comme dans l'exemple de la datasheet. Capacité effective après déclassement ≈ 58 µF, ESR ≈ 2,5 mohms (deux en parallèle).

## Compensation

| Étape | Formule | Résultat |
|---|---|---|
| Pôle du modulateur | fp = IOUT / (2π × VOUT × COUT) | 2 / (2π × 5 × 58,3 µF) ≈ 1,09 kHz |
| Zéro de l'ESR | fz = 1 / (2π × ESR × COUT) | ≈ 1,09 MHz |
| Fréquence de coupure | fc = min(√(fp × fz), √(fp × fsw / 2)) | min(34,5 kHz ; 16,5 kHz) = **16,5 kHz** |
| RCOMP | 2π × fc × COUT × VOUT / (gmps × VREF × gmea) | ≈ 9,0 kohms, d'où **9,09 kohms** |
| CCOMP | 1 / (2π × RCOMP × fp) | ≈ 16 nF, d'où **15 nF** |
| CP | max(COUT × ESR / RCOMP ; 1 / (π × RCOMP × fsw)) | max(16 pF ; 70 pF), d'où **68 pF** |

Contrôle avec l'exemple de la datasheet (3,5 A, 600 kHz, même COUT) : 13,0 kohms, 6,4 nF et 40,8 pF, pour 13 kohms, 6,8 nF et 39 pF retenus par TI.

Cette méthode néglige la compensation de pente. Mesurer la réponse à un échelon de charge sur le premier prototype : dépassement visé inférieur à 5 %.

## Autres composants

- Diode de roue libre B560C : 60 V, 5 A, Schottky, tient la limite de courant en court-circuit.
- Condensateur de bootstrap : 100 nF.
- Entrée : 47 µF 63 V électrolytique, plus 2,2 µF 100 V et 100 nF céramiques au plus près des broches VIN et GND.
- TVS SMBJ36CA : rien ne conduit jusqu'à 36 V, écrêtage à environ 58 V au courant crête. Reste sous les 65 V maximum absolu du TPS54360.

## PTC d'entrée

Littelfuse **2920L110/60MR** : boîtier 2920, 60 V, 1,1 A maintenu à 23 °C.

- Courant d'entrée typique : ≈ 0,4 A à 9 V et 0,3 A à 12 V.
- Au pire cas, avec 8 bus en court-circuit permanent, ≈ 8,5 W en entrée, soit 0,95 A à 9 V. Dans un boîtier chaud, la PTC peut alors se déclencher. C'est sans dommage, puisqu'elle se réarme, et cette situation correspond déjà à un défaut.
