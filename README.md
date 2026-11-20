# Usb2Can-8-Ports

Carte électronique offrant **8 ports CAN** (jusqu'à **500 kbit/s** chacun) reliés à un PC par **un seul port USB**.

## Objectif

- 8 bus CAN indépendants, isolés ou non (à décider), débit nominal 500 kbit/s (CAN 2.0B, CAN FD envisageable).
- Connexion hôte en USB (USB 2.0 Full Speed ou High Speed, à décider selon la charge).
- Compatibilité visée côté PC : SocketCAN (Linux) et, si possible, un protocole ouvert type gs_usb / candleLight.
- Conception matérielle sous KiCad, firmware embarqué et documentation versionnés dans ce dépôt.

## Organisation du dépôt

| Dossier | Contenu |
|---|---|
| `hardware/` | Projet KiCad (schéma, PCB, bibliothèques, fichiers de fabrication) |
| `firmware/` | Code embarqué du microcontrôleur |
| `docs/` | Cahier des charges, choix d'architecture, notes de conception |

## État

Phase de cadrage. Aucun choix d'architecture n'est figé : voir [`docs/architecture-options.md`](docs/architecture-options.md).
