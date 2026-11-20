# Pistes d'architecture (à valider)

Rien n'est décidé. Ce document liste les options pour en discuter.

## Contraintes de départ

- 8 ports CAN à 500 kbit/s.
- Charge pire cas : 8 × ~4 400 trames/s (trames standard 8 octets à 100 % de charge) ≈ 35 000 trames/s, soit quelques Mbit/s utiles vers l'hôte. USB Full Speed (12 Mbit/s) est juste possible ; High Speed (480 Mbit/s) donne de la marge.

## Option A : un MCU avec plusieurs contrôleurs CAN intégrés + extension

- STM32H7 : 2 FDCAN (3 sur certains H7A3/H7B0). STM32G4 : jusqu'à 3 FDCAN. STM32H5 : 2 FDCAN.
- Aucun MCU courant n'a 8 contrôleurs CAN : il faut compléter par des contrôleurs SPI.
- Avantages : faible latence sur les ports natifs.
- Inconvénients : architecture hétérogène (deux pilotes à maintenir).

## Option B : MCU + 8 contrôleurs SPI MCP2518FD

- Un MCU avec USB High Speed (ex. STM32H7 avec PHY ULPI, ou STM32H7R/S, STM32U5 avec USB HS intégré) et plusieurs bus SPI rapides.
- 8 × MCP2518FD (CAN FD, SPI jusqu'à 20 MHz) + 8 transceivers.
- Avantages : 8 ports identiques, firmware homogène, CAN FD gratuit.
- Inconvénients : coût et surface des 8 contrôleurs, débit SPI à dimensionner (répartir sur 2 à 4 bus SPI).

## Option C : deux ou quatre MCU + hub USB

- Ex. 4 × STM32G0B1 (2 FDCAN chacun, firmware candleLight existant) derrière un hub USB intégré.
- Avantages : firmware open source déjà disponible, chaque MCU vu comme un périphérique gs_usb.
- Inconvénients : 4 périphériques USB côté hôte, plus de composants.

## Transceivers et isolation

- Transceivers : TCAN1042, MCP2562FD, TJA1051/TJA1462.
- Isolation optionnelle : ISO1042 ou ADM3053 (avec alimentation isolée intégrée), à décider selon l'usage.
- Terminaison 120 Ω commutable par port (cavalier ou interrupteur analogique).

## Questions ouvertes

1. CAN 2.0 seul ou CAN FD ?
2. Isolation galvanique nécessaire ?
3. Connecteurs : DB9, borniers, RJ45 ?
4. Alimentation par l'USB uniquement ou externe ?
5. Logiciel côté PC : SocketCAN/gs_usb, ou protocole propre ?
