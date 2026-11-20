# Journal des décisions d'architecture

Chaque décision reprend une question ouverte de [`architecture-options.md`](architecture-options.md).
Statuts possibles : **en discussion**, **décidé**, **remis en cause**.

Les prix sont des ordres de grandeur unitaires (petites quantités, distributeurs type Mouser/Digikey) à vérifier au moment du choix final.

---

## D1. CAN 2.0 seul ou CAN FD ?

**Statut : décidé le 2026-11-20** : option b, matériel compatible CAN FD, firmware CAN 2.0B d'abord.

### Options

| Option | Composants | Surcoût vs CAN 2.0 | Conséquences |
|---|---|---|---|
| a. CAN 2.0 seul | MCP2515 (SPI) ou bxCAN, transceivers classiques (TJA1050, MCP2551) | référence | Composants en fin de vie ou non recommandés pour nouveaux designs ; aucune évolution possible vers FD sans refaire la carte. |
| b. Matériel FD, firmware CAN 2.0 d'abord | MCP2518FD ou FDCAN intégré, transceivers FD (TCAN1042, MCP2562FD, ISO1042) | ≈ 0 à 1 € par port | Mêmes composants que les designs actuels ; FD activable plus tard par simple évolution du firmware et du protocole USB. |
| c. CAN FD complet dès la v1 | Idem b | ≈ 0 à 1 € par port | Firmware et protocole hôte plus complexes dès le départ (trames 64 octets, deux débits par port) ; débit USB beaucoup plus élevé à absorber. |

### Points à retenir

- Les contrôleurs et transceivers modernes sont presque tous compatibles FD : rester en CAN 2.0 pur n'économise rien et oblige à choisir des composants anciens (MCP2515/MCP2551 non recommandés pour nouveaux designs).
- Un contrôleur FD gère parfaitement le CAN 2.0 à 500 kbit/s : le choix b n'impose rien au départ.
- Si FD est activé : 8 ports × jusqu'à 2 à 5 Mbit/s en phase de données dépassent l'USB Full Speed (12 Mbit/s). **USB High Speed devient obligatoire.**
- Côté PC, SocketCAN et gs_usb gèrent CAN FD (gs_usb depuis Linux 6.x), donc le choix b reste compatible avec la piste gs_usb.

### Décision

Option **b** retenue : tout le matériel (contrôleurs, transceivers, isolation éventuelle, USB High Speed) est choisi compatible CAN FD ; la v1 du firmware ne fait que du CAN 2.0B à 500 kbit/s, le FD vient dans une version suivante.

Conséquences :
- Contrôleurs CAN : FDCAN intégré ou MCP2518FD (MCP2515 exclu).
- Transceivers : modèles compatibles FD (TCAN1042, MCP2562FD, TJA1462 ou ISO1042 si isolation).
- Liaison hôte : USB 2.0 High Speed (480 Mbit/s), donc MCU avec USB HS intégré ou PHY ULPI externe.

---

## D2. Isolation galvanique nécessaire ?

**Statut : décidé le 2026-11-20** : option c, isolation par port.

### Options

| Option | Principe | Composants | Surcoût pour 8 ports | Conséquences |
|---|---|---|---|---|
| a. Aucune isolation | Masse commune PC / carte / 8 bus | Transceivers standard (TCAN1042) | 0 € | Le plus simple et compact. Risque de boucles de masse et de destruction si un bus est à un potentiel différent (véhicule, machine, alimentation séparée). Réservé à un usage banc avec masse commune maîtrisée. |
| b. Une barrière commune | Isolation entre la partie USB/MCU et l'ensemble des 8 ports (isolateurs numériques sur les bus SPI, ex. ISO7741, + un convertisseur DC/DC isolé) | 2 à 4 isolateurs SPI + 1 DC/DC isolé | ≈ 15 à 25 € | Protège le PC. Les 8 bus restent reliés entre eux : à n'utiliser que si tous les bus partagent la même masse. L'isolateur limite la fréquence SPI (~25 à 50 MHz selon modèle, à vérifier). |
| c. Isolation par port | Chaque port a sa propre barrière : transceiver isolé (ISO1042) + petit DC/DC isolé (ex. UCC12050, B0505S), ou ADM3053 tout intégré | 8 × (ISO1042 + DC/DC), ou 8 × ADM3053 | ≈ 40 à 60 € (ISO1042 + DC/DC), ≈ 80 à 100 € (ADM3053) | Chaque bus est indépendant du PC et des autres bus. Standard des interfaces professionnelles multi-voies. Surface PCB plus grande (DC/DC + règles d'isolement), dissipation d'environ 0,3 à 0,5 W par port. |

### Points à retenir

- Isoler côté USB (isolateur USB type ADuM4160) est écarté : ces isolateurs sont limités au Full Speed, incompatible avec le besoin High Speed de D1.
- ISO1042 et ADM3053 sont compatibles CAN FD : l'option c reste cohérente avec D1.
- L'isolation par port pèse sur le budget d'alimentation (question 4) : 8 DC/DC isolés à ~70 % de rendement ajoutent ~2 à 4 W, au-delà de ce qu'un port USB 2.0 standard fournit (2,5 W).

### Décision

Option **c** retenue : chaque port a sa propre barrière d'isolation, avec un transceiver isolé ISO1042 (compatible CAN FD) et un petit convertisseur DC/DC isolé 5 V dédié.

Conséquences :
- 8 domaines de masse isolés (GND_ISO_1 à GND_ISO_8), séparés de la masse USB/MCU et entre eux.
- Le niveau d'isolement réel est fixé par le maillon le plus faible (DC/DC, distances d'isolement sur le PCB) : viser au moins 1 kV, valeur exacte à fixer avec le choix du DC/DC.
- Règles de routage : saignée sans cuivre sous chaque barrière, distances de fuite et d'isolement respectées jusqu'au connecteur.
- Budget d'alimentation alourdi (voir D4) : l'USB 2.0 seul (2,5 W) ne suffit plus.

---

## D3. Connecteurs

**Statut : en discussion** (recommandation : DB9 au brochage CiA 303-1, ou borniers pour un câblage à demeure)

### Options

| Option | Encombrement pour 8 ports | Coût unitaire | Conséquences |
|---|---|---|---|
| a. DB9 mâle, brochage CiA 303-1 (2 = CAN_L, 7 = CAN_H, 3 = GND, 9 = V+ optionnel) | ~260 mm en ligne, ~130 mm avec 4 blocs DB9 doubles superposés | ≈ 1 à 4 € | Standard de fait (PEAK, Kvaser, Vector) : câbles et adaptateurs du commerce utilisables tels quels. Encombrant. |
| b. Borniers débrochables 3 ou 4 points (CAN_H, CAN_L, GND_ISO, blindage) | ~100 à 130 mm | ≈ 1 à 2 € | Compact, câblage direct sur fils, pratique en banc ou armoire industrielle. Pas de câble standard, risque d'erreur de câblage. |
| c. RJ45 (CiA 303-1 : 1 = CAN_H, 2 = CAN_L, 3 = GND) | ~70 mm avec deux blocs 2×4 | ≈ 1 à 3 € | Très compact, câbles bon marché. Risque de confusion avec un port Ethernet, brochage moins répandu que le DB9. |
| d. Un connecteur haute densité (ex. DSUB 37) + câble éclaté | ~70 mm | ≈ 5 à 10 € + câble | Une seule prise sur la carte. Nécessite de fabriquer un faisceau, isolement entre ports à vérifier dans le connecteur. |

### Points à retenir

- Avec l'isolation par port (D2), chaque connecteur porte sa propre masse isolée : le connecteur doit garder les distances d'isolement entre ports (DB9 et borniers séparés le font naturellement).
- La terminaison 120 Ω commutable reste sur la carte, quel que soit le connecteur.

### Recommandation

Option **a** si la carte doit fonctionner avec les câbles et outils CAN du commerce ; option **b** si elle est destinée à être câblée à demeure dans un banc ou une armoire.

---

## D4. Alimentation

**Statut : décidé le 2026-11-20** : option c, alimentation externe 9 à 36 V seulement, l'USB ne sert qu'aux données.

### Budget de puissance estimé

| Bloc | Typique | Pire cas |
|---|---|---|
| MCU + PHY USB HS + 8 contrôleurs SPI + LED | ≈ 1 à 1,5 W | ≈ 1,5 W |
| 8 côtés isolés (ISO1042 + DC/DC à ~60 % de rendement) | ≈ 2 W (bus peu chargés) | ≈ 5 W (bus dominants en continu) |
| **Total** | **≈ 3 à 3,5 W** | **≈ 6,5 W** |

Un port USB 2.0 fournit 2,5 W (500 mA), un port USB 3.x 4,5 W (900 mA) : aucun des deux ne couvre le pire cas.

### Options

| Option | Composants | Surcoût | Conséquences |
|---|---|---|---|
| a. USB seul (USB-A / micro / USB-C sans négociation) | Rien de plus | 0 € | Écarté : insuffisant avec l'isolation par port. |
| b. USB-C 5 V / 3 A (15 W) | Connecteur USB-C + résistances CC, détection du courant annoncé | ≈ 1 € | Un seul câble. Fonctionne seulement si le port hôte annonce 1,5 A ou 3 A (beaucoup de ports PC USB-A ne le font pas). |
| c. Alimentation externe seule (ex. 9 à 36 V), USB pour les données | Jack ou bornier + régulateur abaisseur + protections (inversion, surtension) | ≈ 3 à 5 € | Indépendant du PC, compatible 12/24 V véhicule et industriel. Un bloc secteur ou un câble d'alimentation en plus. |
| d. Les deux : entrée externe 9 à 36 V **ou** USB-C | c + b + sélection automatique (diode idéale, ex. LM66100) | ≈ 4 à 7 € | Un seul câble USB-C sur un port capable, alimentation externe sinon. Le firmware peut lire le courant annoncé et signaler une alimentation insuffisante. |

### Décision

Option **c** retenue : la carte est alimentée uniquement par une entrée externe 9 à 36 V ; l'USB ne transporte que les données.

Conséquences :
- La carte est un périphérique USB auto-alimenté (self-powered) : le MCU doit surveiller VBUS (pont diviseur) pour ne connecter le pull-up D+ que lorsque le câble USB est branché. Sans alimentation externe, la carte n'apparaît pas sur le PC.
- Étage d'entrée : protection contre l'inversion de polarité, TVS contre les surtensions (12/24 V véhicule), fusible réarmable, puis régulateur abaisseur vers 5 V ou 3,3 V.
- Budget à dimensionner pour ~6,5 W en sortie, soit ~8 W en entrée en tenant compte du rendement.
- Connecteur d'alimentation (jack ou bornier débrochable) à choisir avec D3.

---

## D5. Logiciel côté PC

**Statut : en discussion** (recommandation : protocole gs_usb, 8 voies dans un seul périphérique)

### Options

| Option | Principe | Côté Linux | Côté Windows | Conséquences |
|---|---|---|---|---|
| a. gs_usb (protocole candleLight) | Un périphérique USB qui expose 8 voies CAN | Pilote `gs_usb` du noyau : apparaît directement en `can0` à `can7` (SocketCAN), CAN FD géré | Accès via libusb/WinUSB : python-can (interface `gs_usb`), Cangaroo | Aucun pilote PC à écrire sous Linux. Le protocole impose sa structure de trames ; le firmware doit le respecter. |
| b. slcan (protocole ASCII sur port série virtuel) | 8 ports série USB CDC-ACM, un par voie | `slcand` crée les interfaces SocketCAN | Ports COM natifs, nombreux outils | Simple à déboguer. Texte ASCII peu efficace, pas de CAN FD standardisé, 8 ports série à gérer. |
| c. Protocole propre | Format binaire libre | Pilote ou démon à écrire | Pilote ou bibliothèque à écrire | Liberté totale (horodatage, statistiques), mais tout le logiciel PC est à développer et maintenir. |

### Points à retenir

- Le pilote `gs_usb` actuel du noyau Linux accepte jusqu'à 255 voies par périphérique ; les noyaux anciens étaient limités à 3 voies. La version minimale du noyau à supporter est à vérifier.
- Le pilote ne reconnaît que des couples VID:PID listés dans son code. Pour un nouveau matériel, il faut soit obtenir un VID:PID (ex. pid.codes, gratuit pour le matériel open source) et le faire ajouter au pilote, soit le déclarer à la main via `new_id` en attendant.
- gs_usb envoie une trame par transfert USB : avec l'USB High Speed (D1), le débit de 8 voies à 500 kbit/s est largement couvert.

### Recommandation

Option **a** : gs_usb avec les 8 voies dans un seul périphérique. C'est la piste la plus courte vers un usage réel sous Linux (SocketCAN, can-utils, Wireshark) et elle reste utilisable sous Windows via python-can.
