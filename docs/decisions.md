# Journal des décisions d'architecture

Chaque décision reprend une question ouverte de [`architecture-options.md`](architecture-options.md).
Statuts possibles : **en discussion**, **décidé**, **remis en cause**.

Les prix sont des ordres de grandeur unitaires (petites quantités, distributeurs type Mouser/Digikey) à vérifier au moment du choix final.

---

## D1. CAN 2.0 seul ou CAN FD ?

**Statut : en discussion** (recommandation : matériel compatible CAN FD, firmware CAN 2.0 d'abord)

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

### Recommandation

Option **b** : tout le matériel (contrôleurs, transceivers, isolation éventuelle, USB High Speed) est choisi compatible CAN FD ; la v1 du firmware ne fait que du CAN 2.0B à 500 kbit/s, FD vient dans une version suivante.

---

## D2. Isolation galvanique nécessaire ?

**Statut : en discussion** (recommandation : isolation par port)

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

### Recommandation

Option **c** avec ISO1042 + DC/DC isolé par port, si la carte doit se brancher sur des systèmes dont la masse n'est pas maîtrisée (véhicules, machines, bancs différents). Option **a** si la carte est destinée uniquement à un banc avec masse commune.

---

## D3. Connecteurs

**Statut : à traiter**

## D4. Alimentation

**Statut : à traiter**

## D5. Logiciel côté PC

**Statut : à traiter**
