#!/usr/bin/env python3
"""Génère les projets KiCad de la carte 8 ports CAN.

    python3 hardware/outils/generer_schemas.py

Produit :
  hardware/bibliotheque/can8.kicad_sym   symboles absents de la bibliothèque KiCad
  hardware/can8-mere/                     carte mère : MCU, USB, alimentation, ports 1 à 4
  hardware/can8-fille/                    carte fille : ports 5 à 8

Les schémas sont décrits ici sous forme de netlist (composant -> broche -> net).
Ils servent de point de départ : on peut ensuite les retoucher directement dans
KiCad, auquel cas ce script ne doit plus être relancé sur le projet modifié.

Nécessite les bibliothèques de symboles de KiCad 7 (paquet kicad-symbols), chemin
modifiable par la variable KICAD7_SYMBOL_DIR.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bibliotheque_can8  # noqa: E402
import schema  # noqa: E402
from schema import S, Sheet, uid, font  # noqa: E402

HW = os.path.normpath(os.path.join(HERE, '..'))
DATE = '2026-11-20'
REV = 'v0.2'

# ------------------------------------------------------------------ empreintes
R0603 = 'Resistor_SMD:R_0603_1608Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
C1206 = 'Capacitor_SMD:C_1206_3216Metric'
C1210 = 'Capacitor_SMD:C_1210_3225Metric'
LED0603 = 'LED_SMD:LED_0603_1608Metric'
XTAL3225 = 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm'
R1206 = 'Resistor_SMD:R_1206_3216Metric'


def R(value, a, b, fp=R0603, dnp=False, **k):
    return ('Device:R', 'R', value, {1: a, 2: b}, fp, k.get('fields'), dnp)


def C(value, a, b, fp=C0603, **k):
    return ('Device:C', 'C', value, {1: a, 2: b}, fp, k.get('fields'), False)


def add(sheet, spec):
    lib, letter, value, nets, fp, fields, dnp = spec
    return sheet.add(lib, letter, value, nets, footprint=fp, fields=fields, dnp=dnp)


def decoupling(sheet, net, gnd, values):
    for v in values:
        fp = C0603 if v in ('100nF', '10nF', '1nF') else (C0805 if v in ('1uF', '2.2uF', '4.7uF', '10uF') else C1210)
        add(sheet, C(v, net, gnd, fp))


# ------------------------------------------------------------------ feuilles
def feuille_port(project):
    """Un port CAN isolé complet. Feuille réutilisée 4 fois par carte."""
    sh = Sheet('port_can', 'port_can.kicad_sch', 'Port CAN isolé (MCP2518FD + ISO1042 + UCC12050)', '',
               hier={'SCK': 'input', 'MOSI': 'input', 'MISO': 'output', '~{CS}': 'input',
                     '~{INT}': 'output'},
               globals_={'CHASSIS'},
               notes=[
                   'Côté logique (masse GND, 3,3 V) : contrôleur MCP2518FD, quartz 40 MHz dédié, LED d\'état.\n'
                   'Côté bus (masse GND_ISO, 5 V isolé VISO) : ISO1042, protection ESD, terminaison, DB9.\n'
                   'Barrière d\'isolement : ISO1042 (5 kVrms) et UCC12050 (5 kVrms renforcé). Aucune piste ni plan\n'
                   'ne doit traverser la saignée sous ces deux boîtiers (distance de fuite >= 8 mm).',
                   'DB9 mâle CiA 303-1 : 2 = CAN_L, 7 = CAN_H, 3 et 6 = CAN_GND (GND_ISO), 5 = blindage (châssis),\n'
                   '1, 4, 8, 9 non connectées. Le boîtier métallique du DB9 est relié au châssis.',
                   'Terminaison 120 ohms commutable par micro-interrupteur. LED verte = activité (GPIO0),\n'
                   'LED rouge = erreur (GPIO1), pilotées par le MCP2518FD (registre IOCON).',
                   'Quartz 40 MHz : charge 2 x 15 pF à ajuster selon le quartz retenu (CL et capacité parasite).',
               ])
    sh.pwr_flags = ['GND_ISO']
    # contrôleur CAN
    sh.add('can8:MCP2518FD-xSL', 'U', 'MCP2518FD-E/SL', {
        10: 'SCK', 11: 'MOSI', 12: 'SDO', 13: '~{CS}', 4: '~{INT}', 14: '+3V3', 7: 'GND',
        6: 'OSC1', 5: 'OSC2', 1: 'TXD', 2: 'RXD', 3: None, 9: 'LED_ACT', 8: 'LED_ERR'})
    add(sh, R('33', 'SDO', 'MISO'))
    add(sh, R('10k', '+3V3', '~{CS}'))
    add(sh, R('10k', '+3V3', '~{INT}'))
    decoupling(sh, '+3V3', 'GND', ['100nF', '1uF'])
    sh.add('Device:Crystal_GND24', 'Y', '40MHz', {1: 'OSC1', 3: 'OSC2', 2: 'GND', 4: 'GND'},
           footprint=XTAL3225)
    add(sh, C('15pF', 'OSC1', 'GND'))
    add(sh, C('15pF', 'OSC2', 'GND'))
    # LED
    add(sh, R('1k', 'LED_ACT', 'LED_ACT_A'))
    sh.add('Device:LED', 'D', 'verte', {2: 'LED_ACT_A', 1: 'GND'}, footprint=LED0603)
    add(sh, R('1k', 'LED_ERR', 'LED_ERR_A'))
    sh.add('Device:LED', 'D', 'rouge', {2: 'LED_ERR_A', 1: 'GND'}, footprint=LED0603)
    # transceiver isolé
    sh.add('can8:ISO1042BDW', 'U', 'ISO1042BDWR', {
        1: '+3V3', 2: 'GND', 8: 'GND', 3: 'TXD', 5: 'RXD', 11: 'VISO', 16: 'VISO', 13: 'CANH',
        12: 'CANL', 9: 'GND_ISO', 10: 'GND_ISO', 15: 'GND_ISO'})
    decoupling(sh, '+3V3', 'GND', ['100nF', '1uF'])
    decoupling(sh, 'VISO', 'GND_ISO', ['100nF', '1uF'])
    # alimentation isolée
    sh.add('can8:UCC12050DVE', 'U', 'UCC12050DVER', {
        3: '+5V', 1: 'EN_ISO', 4: 'GND', 5: None, 2: 'GND', 6: 'GND', 7: 'GND', 8: 'GND',
        14: 'VISO', 13: 'VISO', 9: 'GND_ISO', 15: 'GND_ISO', 16: 'GND_ISO', 10: 'GND_ISO',
        11: 'GND_ISO', 12: 'GND_ISO'})
    add(sh, R('10k', '+5V', 'EN_ISO'))
    decoupling(sh, '+5V', 'GND', ['100nF', '10uF'])
    decoupling(sh, 'VISO', 'GND_ISO', ['100nF', '10uF'])
    # côté bus
    sh.add('Power_Protection:NUP2105L', 'D', 'NUP2105L', {1: 'CANH', 2: 'CANL', 3: 'GND_ISO'})
    sh.add('Switch:SW_SPST', 'SW', 'Terminaison', {1: 'CANH', 2: 'TERM'},
           footprint='Button_Switch_SMD:SW_DIP_SPSTx01_Slide_6.7x4.1mm_W8.61mm_P2.54mm_LowProfile')
    add(sh, R('120 1%', 'TERM', 'CANL', fp=R1206))
    sh.add('Connector:DE9_Plug_MountingHoles', 'J', 'DB9 mâle', {
        2: 'CANL', 7: 'CANH', 3: 'GND_ISO', 6: 'GND_ISO', 5: 'CHASSIS', 1: None, 4: None, 8: None,
        9: None, 0: 'CHASSIS'},
        footprint='Connector_Dsub:DSUB-9_Male_Horizontal_P2.77x2.84mm_EdgePinOffset9.90mm_Housed_MountingHolesOffset11.32mm')
    return sh


def feuille_alim():
    sh = Sheet('alim', 'alimentation.kicad_sch', 'Alimentation 9-36 V -> 5 V -> 3,3 V', '10',
               globals_={'VIN_MES', 'CHASSIS', '+VIN'},
               notes=[
                   'Entrée 9 à 36 V (12/24 V véhicule ou industriel) : PTC, TVS bidirectionnelle 36 V,\n'
                   'diode série anti-inversion, puis abaisseur TPS54360 (60 V, 3,5 A, non synchrone) vers 5 V.',
                   'TPS54360 (calculs : docs/calculs-alimentation.md) : fsw 500 kHz (RT 200k), UVLO 8 V / 6,25 V (523k / 84,5k),\n'
                   'sortie 5 V (53,6k / 10,2k), L = 15 uH (Isat >= 6 A), 2 x 47 uF, compensation 9,09k + 15 nF // 68 pF (fc ~16 kHz).',
                   'PTC : Littelfuse 2920L110/60MR (1,1 A maintenu à 23 °C, 60 V). Au pire cas (9 V, 8 bus en court-circuit,\n'
                   'boîtier chaud) le courant d\'entrée approche le seuil : déclenchement possible, sans dommage (réarmable).',
                   'Budget : ~6,5 W au pire (D4). 5 V : 8 x UCC12050 + LDO 3,3 V. 3,3 V : MCU, PHY, 8 x MCP2518FD.',
                   'Châssis : trous de fixation et blindages (USB, DB9) reliés à GND par 1 Mohm // 4,7 nF 2 kV.',
               ])
    sh.pwr_flags = ['GND', '+VIN', '+5V']
    sh.add('Connector:Screw_Terminal_01x02', 'J', 'MSTB 2,5/2-GF-5,08', {1: 'VIN_BRUT', 2: 'GND'},
           footprint='Connector_Phoenix_MSTB:PhoenixContact_MSTB_2,5_2-GF-5,08_1x02_P5.08mm_Horizontal_ThreadedFlange')
    sh.add('Device:Polyfuse', 'F', '2920L110/60MR', {1: 'VIN_BRUT', 2: 'VIN_FUS'},
           footprint='Fuse:Fuse_2920_7451Metric')
    sh.add('Device:D_TVS', 'D', 'SMBJ36CA', {1: 'VIN_FUS', 2: 'GND'}, footprint='Diode_SMD:D_SMB')
    sh.add('Device:D_Schottky', 'D', 'SS310 (100V 3A)', {2: 'VIN_FUS', 1: '+VIN'}, footprint='Diode_SMD:D_SMA')
    sh.add('Device:C_Polarized', 'C', '47uF 63V', {1: '+VIN', 2: 'GND'},
           footprint='Capacitor_SMD:CP_Elec_8x10')
    add(sh, C('2.2uF 100V', '+VIN', 'GND', C1210))
    add(sh, C('100nF 100V', '+VIN', 'GND', C0805))
    # abaisseur 5 V
    sh.add('Regulator_Switching:TPS54360DDA', 'U', 'TPS54360DDA', {
        2: '+VIN', 3: 'EN', 4: 'RT', 1: 'BOOT', 8: 'SW', 5: 'FB', 6: 'COMP', 7: 'GND', 9: 'GND'})
    add(sh, R('523k 1%', '+VIN', 'EN'))
    add(sh, R('84.5k 1%', 'EN', 'GND'))
    add(sh, R('200k 1%', 'RT', 'GND'))
    add(sh, C('100nF', 'BOOT', 'SW'))
    sh.add('Device:D_Schottky', 'D', 'B560C (60V 5A)', {1: 'SW', 2: 'GND'}, footprint='Diode_SMD:D_SMC')
    sh.add('Device:L', 'L', '15uH Isat>=6A', {1: 'SW', 2: '+5V'}, footprint='Inductor_SMD:L_Bourns_SRP1038C_10.0x10.0mm')
    add(sh, R('53.6k 1%', '+5V', 'FB'))
    add(sh, R('10.2k 1%', 'FB', 'GND'))
    add(sh, R('9.09k 1%', 'COMP', 'COMP_RC'))
    add(sh, C('15nF', 'COMP_RC', 'GND'))
    add(sh, C('68pF', 'COMP', 'GND'))
    decoupling(sh, '+5V', 'GND', ['47uF', '47uF', '100nF'])
    # LDO 3,3 V
    sh.add('Regulator_Linear:AP7361C-33E', 'U', 'AP7361C-33E', {1: '+5V', 2: 'GND', 3: '+3V3'})
    decoupling(sh, '+5V', 'GND', ['4.7uF'])
    decoupling(sh, '+3V3', 'GND', ['10uF', '100nF'])
    add(sh, R('1.5k', '+3V3', 'LED_ALIM_A'))
    sh.add('Device:LED', 'D', 'verte', {2: 'LED_ALIM_A', 1: 'GND'}, footprint=LED0603)
    # mesure de la tension d'entrée
    add(sh, R('100k 1%', '+VIN', 'VIN_MES'))
    add(sh, R('8.2k 1%', 'VIN_MES', 'GND'))
    add(sh, C('100nF', 'VIN_MES', 'GND'))
    # châssis
    add(sh, R('1M', 'CHASSIS', 'GND'))
    add(sh, C('4.7nF 2kV', 'CHASSIS', 'GND', C1206))
    for _ in range(4):
        sh.add('Mechanical:MountingHole_Pad', 'H', 'M3', {1: 'CHASSIS'},
               footprint='MountingHole:MountingHole_3.2mm_M3_Pad_Via')
    return sh


SPI_PINS = {  # numéro de broche LQFP144 -> net
    # bus SPI (via résistances série 33 ohms pour SCK et MOSI)
    126: 'SPI1_SCK_M', 124: 'SPI1_MISO', 123: 'SPI1_MOSI_M',
    117: 'SPI2_SCK_M', 75: 'SPI2_MISO', 76: 'SPI2_MOSI_M',
    111: 'SPI3_SCK_M', 112: 'SPI3_MISO', 113: 'SPI3_MOSI_M',
    65: 'SPI4_SCK_M', 66: 'SPI4_MISO', 67: 'SPI4_MOSI_M',
    # chip-selects et interruptions
    78: '~{CS1}', 79: '~{CS2}', 80: '~{CS3}', 81: '~{CS4}',
    58: '~{CS5}', 59: '~{CS6}', 60: '~{CS7}', 63: '~{CS8}',
    82: '~{INT1}', 85: '~{INT2}', 86: '~{INT3}', 87: '~{INT4}',
    88: '~{INT5}', 89: '~{INT6}', 90: '~{INT7}', 91: '~{INT8}',
}
ULPI_PINS = {41: 'ULPI_CLK', 26: 'ULPI_STP', 28: 'ULPI_DIR', 29: 'ULPI_NXT', 37: 'ULPI_D0',
             46: 'ULPI_D1', 47: 'ULPI_D2', 69: 'ULPI_D3', 70: 'ULPI_D4', 73: 'ULPI_D5',
             74: 'ULPI_D6', 135: 'ULPI_D7', 96: '~{ULPI_RST}'}
MISC_PINS = {105: 'SWDIO', 109: 'SWCLK', 133: 'SWO', 136: 'DBG_TX', 137: 'DBG_RX',
             141: 'LED_ETAT', 142: 'LED_ERREUR', 44: 'VIN_MES', 10: '~{FILLE_PRESENTE}',
             23: 'HSE_IN', 24: 'HSE_OUT', 25: 'NRST', 138: 'BOOT0'}
GLOBAL_MERE = ({'VIN_MES', 'CHASSIS', '~{FILLE_PRESENTE}', '+VIN', '~{ULPI_RST}'}
               | {v for v in ULPI_PINS.values()}
               | {'SPI%d_%s' % (b, s) for b in range(1, 5) for s in ('SCK', 'MOSI', 'MISO')}
               | {'~{CS%d}' % i for i in range(1, 9)} | {'~{INT%d}' % i for i in range(1, 9)})


def feuille_mcu():
    sh = Sheet('mcu', 'mcu.kicad_sch', 'Microcontrôleur STM32H723ZGT6', '11',
               globals_=GLOBAL_MERE,
               notes=[
                   'Affectation des broches : voir docs/schema-bloc.md. SPI1 = ports 1-2, SPI2 = ports 3-4 (carte mère),\n'
                   'SPI3 = ports 5-6, SPI4 = ports 7-8 (carte fille). SPI5 (PF7/PF8/PF9) et SPI6 (PG13/PG12/PG14) restent libres.',
                   'Interruptions sur des lignes EXTI toutes différentes (2, 3, 4, 5, 6, 13, 14, 15).',
                   'ULPI : PC2_C et PC3_C passent par un interrupteur analogique interne à fermer dans le firmware\n'
                   '(SYSCFG_PMCR, bits PC2SO / PC3SO), sinon DIR et NXT ne sont pas reliés à l\'OTG_HS.',
                   'HSE 25 MHz pour l\'horloge système ; l\'horloge ULPI 60 MHz vient du PHY USB3320.',
               ])
    sh.pwr_flags = ['+3V3A']
    nets = {}
    for p in schema.lib_pins('MCU_ST_STM32H7:STM32H723ZGTx'):
        n, name = int(p['num']), p['name']
        if name in ('VDD', 'VDD33USB', 'VBAT', 'PDR_ON'):
            nets[n] = '+3V3'
        elif name in ('VSS', 'VSSA'):
            nets[n] = 'GND'
        elif name in ('VDDA', 'VREF+'):
            nets[n] = '+3V3A'
        elif name == 'VCAP':
            nets[n] = 'VCAP%d' % (1 + sum(1 for v in nets.values() if v.startswith('VCAP')))
    nets.update(SPI_PINS)
    nets.update(ULPI_PINS)
    nets.update(MISC_PINS)
    sh.add('MCU_ST_STM32H7:STM32H723ZGTx', 'U', 'STM32H723ZGT6', nets, nc_default=True)
    nvdd = sum(1 for v in nets.values() if v == '+3V3')
    decoupling(sh, '+3V3', 'GND', ['100nF'] * nvdd + ['4.7uF'])
    decoupling(sh, 'VCAP1', 'GND', ['2.2uF'])
    decoupling(sh, 'VCAP2', 'GND', ['2.2uF'])
    sh.add('Device:FerriteBead', 'FB', '600R@100MHz', {1: '+3V3', 2: '+3V3A'},
           footprint='Inductor_SMD:L_0603_1608Metric')
    decoupling(sh, '+3V3A', 'GND', ['1uF', '100nF'])
    # quartz HSE
    sh.add('Device:Crystal_GND24', 'Y', '25MHz', {1: 'HSE_IN', 3: 'HSE_OUT', 2: 'GND', 4: 'GND'},
           footprint=XTAL3225)
    add(sh, C('15pF', 'HSE_IN', 'GND'))
    add(sh, C('15pF', 'HSE_OUT', 'GND'))
    # reset, boot
    add(sh, C('100nF', 'NRST', 'GND'))
    sh.add('Switch:SW_Push', 'SW', 'RESET', {1: 'NRST', 2: 'GND'},
           footprint='Button_Switch_SMD:SW_SPST_B3U-1000P')
    add(sh, R('10k', 'BOOT0', 'GND'))
    # débogage
    sh.add('Connector:Conn_ARM_JTAG_SWD_10', 'J', 'SWD', {
        1: '+3V3', 2: 'SWDIO', 3: 'GND', 4: 'SWCLK', 5: 'GND', 6: 'SWO', 8: None, 9: 'GND', 10: 'NRST'},
        footprint='Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical')
    sh.add('Connector_Generic:Conn_01x03', 'J', 'UART debug', {1: 'DBG_TX', 2: 'DBG_RX', 3: 'GND'},
           footprint='Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical')
    # LED
    add(sh, R('1k', 'LED_ETAT', 'LED_ETAT_A'))
    sh.add('Device:LED', 'D', 'verte', {2: 'LED_ETAT_A', 1: 'GND'}, footprint=LED0603)
    add(sh, R('1k', 'LED_ERREUR', 'LED_ERREUR_A'))
    sh.add('Device:LED', 'D', 'rouge', {2: 'LED_ERREUR_A', 1: 'GND'}, footprint=LED0603)
    # résistances série SPI (côté MCU)
    for b in range(1, 5):
        add(sh, R('33', 'SPI%d_SCK_M' % b, 'SPI%d_SCK' % b))
        add(sh, R('33', 'SPI%d_MOSI_M' % b, 'SPI%d_MOSI' % b))
    add(sh, R('10k', '+3V3', '~{FILLE_PRESENTE}'))
    return sh


def feuille_usb():
    sh = Sheet('usb', 'usb.kicad_sch', 'USB 2.0 High Speed : connecteur USB-B + PHY USB3320 (ULPI)', '12',
               globals_=GLOBAL_MERE,
               notes=[
                   'USB3320 alimenté en 3,3 V externe : VBAT et VDD33 reliés au +3V3 (datasheet §5.5.1).\n'
                   'VDD18 est une ENTRÉE : régulateur 1,8 V dédié (AP2112K-1.8).\n'
                   'RVBUS = 10 kohms +/- 5 % pour un périphérique seul (Table 5-7 ; 1 kohm est réservé à l\'OTG).',
                   'REFSEL[2:0] = 111 (les trois broches au VDDIO) : référence 24 MHz (Table 5-10 de DS00001792).',
                   'Quartz 24 MHz : fondamental, CL 20 pF, ESR <= 30 ohms (Table 4-11). Charge 2 x 33 pF pour\n'
                   '3 pF de broche et ~2 pF de circuit imprimé : à ajuster si le CL du quartz retenu diffère.',
                   'Routage ULPI : 12 signaux à 60 MHz, longueurs appariées (+/- 5 mm), sur plan de masse continu,\n'
                   'le plus courts possible. Paire D+/D- en 90 ohms différentiels. Blindage USB au châssis.',
               ])
    sh.add('Connector:USB_B', 'J', 'USB-B', {1: 'USB_VBUS', 2: 'USB_DM', 3: 'USB_DP', 4: 'GND', 5: 'CHASSIS'},
           footprint='Connector_USB:USB_B_OST_USB-B1HSxx_Horizontal')
    sh.add('Power_Protection:USBLC6-2SC6', 'U', 'USBLC6-2SC6', {
        1: 'USB_DP', 6: 'USB_DP', 3: 'USB_DM', 4: 'USB_DM', 5: 'USB_VBUS', 2: 'GND'})
    sh.add('can8:USB3320C-EZK', 'U', 'USB3320C-EZK', {
        29: 'ULPI_STP', 31: 'ULPI_DIR', 2: 'ULPI_NXT', 1: 'ULPI_CLK',
        3: 'ULPI_D0', 4: 'ULPI_D1', 5: 'ULPI_D2', 6: 'ULPI_D3', 7: 'ULPI_D4', 9: 'ULPI_D5',
        10: 'ULPI_D6', 13: 'ULPI_D7', 27: '~{ULPI_RST}',
        8: '+3V3', 11: '+3V3', 14: '+3V3',
        18: 'USB_DP', 19: 'USB_DM', 22: 'PHY_VBUS', 23: '+3V3', 17: None, 16: None, 15: None,
        26: 'PHY_REFCLK', 25: 'PHY_XO', 24: 'RBIAS',
        21: '+3V3', 20: '+3V3', 32: '+3V3', 28: '+1V8_PHY', 30: '+1V8_PHY', 33: 'GND'})
    add(sh, R('10k', 'PHY_VBUS', 'USB_VBUS'))
    add(sh, R('8.06k 1%', 'RBIAS', 'GND'))
    add(sh, R('10k', '+3V3', '~{ULPI_RST}'))
    sh.add('Device:Crystal_GND24', 'Y', '24MHz', {1: 'PHY_REFCLK', 3: 'PHY_XO', 2: 'GND', 4: 'GND'},
           footprint=XTAL3225)
    add(sh, C('33pF', 'PHY_REFCLK', 'GND'))
    add(sh, C('33pF', 'PHY_XO', 'GND'))
    decoupling(sh, '+3V3', 'GND', ['2.2uF', '100nF', '100nF', '1uF'])
    sh.add('Regulator_Linear:AP2112K-1.8', 'U', 'AP2112K-1.8', {1: '+3V3', 3: '+3V3', 2: 'GND', 4: None,
                                                               5: '+1V8_PHY'})
    decoupling(sh, '+3V3', 'GND', ['1uF'])
    decoupling(sh, '+1V8_PHY', 'GND', ['1uF', '100nF', '100nF'])
    return sh


B2B = {  # broche du connecteur 2 x 20 -> net (identique sur les deux cartes)
    1: '+5V', 2: '+5V', 3: '+5V', 4: '+5V', 5: 'GND', 6: 'GND', 7: '+3V3', 8: '+3V3',
    9: 'GND', 10: 'GND', 11: 'SPI3_SCK', 12: 'GND', 13: 'SPI3_MOSI', 14: 'SPI3_MISO',
    15: 'GND', 16: 'GND', 17: '~{CS5}', 18: '~{CS6}', 19: '~{INT5}', 20: '~{INT6}',
    21: 'GND', 22: 'GND', 23: 'SPI4_SCK', 24: 'GND', 25: 'SPI4_MOSI', 26: 'SPI4_MISO',
    27: 'GND', 28: 'GND', 29: '~{CS7}', 30: '~{CS8}', 31: '~{INT7}', 32: '~{INT8}',
    33: 'GND', 34: 'GND', 35: '~{FILLE_PRESENTE}', 36: 'GND', 37: 'CHASSIS', 38: 'CHASSIS',
    39: 'GND', 40: 'GND',
}


def feuille_b2b(fille):
    nets = dict(B2B)
    g = set(GLOBAL_MERE)
    if fille:
        nets[35] = 'GND'   # la carte fille signale sa présence en tirant la ligne à la masse
    sh = Sheet('b2b', 'carte_a_carte.kicad_sch',
               'Connecteur carte à carte (2 x 20, pas 2,54 mm)', '13', globals_=g,
               notes=[
                   'Brochage commun aux deux cartes : une masse à côté de chaque horloge SPI, 4 broches 5 V\n'
                   '(UCC12050 des ports 5-8, ~0,7 A au pire), 2 broches 3,3 V (MCP2518FD et ISO1042 côté logique).',
                   'Carte mère : embase femelle (PinSocket). Carte fille : barrette mâle (PinHeader), montée en dessous.\n'
                   'Liaison la plus courte possible (entretoises de 11 mm environ, à fixer avec la mécanique).',
               ] + (['Carte fille : la broche 35 (~FILLE_PRESENTE) est reliée à la masse pour signaler sa présence.']
                    if fille else []))
    fp = ('Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical' if fille
          else 'Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical')
    sh.add('Connector_Generic:Conn_02x20_Odd_Even', 'J', 'Carte à carte', nets, footprint=fp)
    if fille:
        sh.pwr_flags = ['+5V', '+3V3', 'GND']
        decoupling(sh, '+5V', 'GND', ['22uF', '100nF'])
        decoupling(sh, '+3V3', 'GND', ['10uF', '100nF'])
        for _ in range(4):
            sh.add('Mechanical:MountingHole_Pad', 'H', 'M3', {1: 'CHASSIS'},
                   footprint='MountingHole:MountingHole_3.2mm_M3_Pad_Via')
        add(sh, R('1M', 'CHASSIS', 'GND'))
        add(sh, C('4.7nF 2kV', 'CHASSIS', 'GND', C1206))
    return sh


# ------------------------------------------------------------------ projets
PORT_BUS = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4}


def sheet_block(project, root_uuid, sname, sfile, x, y, w, h, page, pins_map, key):
    """Bloc de feuille hiérarchique + fils + étiquettes globales sur ses broches."""
    su = uid(project, 'sheetblock', key)
    items = []
    blk = [S('sheet'), [S('at'), x, y], [S('size'), w, h], [S('fields_autoplaced')],
           [S('stroke'), [S('width'), 0.1524], [S('type'), S('solid')]],
           [S('fill'), [S('color'), 0, 0, 0, 0.0]], [S('uuid'), S(su)],
           [S('property'), 'Sheetname', sname, [S('at'), x, round(y - 0.7, 3), 0], font('left bottom')],
           [S('property'), 'Sheetfile', sfile, [S('at'), x, round(y + h + 0.6, 3), 0], font('left top')]]
    for i, (pin, shape, glob) in enumerate(pins_map):
        py = round(y + 2.54 * (i + 1), 3)
        blk.append([S('pin'), pin, S(shape), [S('at'), x, py, 180], font('left'),
                    [S('uuid'), S(uid(su, 'pin', pin))]])
        items.append([S('wire'), [S('pts'), [S('xy'), x, py], [S('xy'), round(x - 5.08, 3), py]],
                      [S('stroke'), [S('width'), 0], [S('type'), S('default')]],
                      [S('uuid'), S(uid(su, 'wire', pin))]])
        items.append([S('global_label'), glob, [S('shape'), S('passive')], [S('at'), round(x - 5.08, 3), py, 180],
                      [S('fields_autoplaced')], font('right'), [S('uuid'), S(uid(su, 'gl', pin))],
                      [S('property'), 'Intersheetrefs', '${INTERSHEET_REFS}', [S('at'), 0, 0, 0],
                       font('right', hide=True)]])
    blk.append([S('instances'), [S('project'), project, [S('path'), '/' + root_uuid, [S('page'), str(page)]]]])
    return su, [blk] + items


def projet(nom, titre, feuilles, ports):
    """feuilles : liste de Sheet non réutilisées ; ports : numéros de ports (4 instances de port_can)."""
    out = os.path.join(HW, nom)
    os.makedirs(out, exist_ok=True)
    root_uuid = uid(nom, 'root')
    tb = [[S('date'), DATE], [S('rev'), REV], [S('company'), 'Usb2Can-8-Ports'],
          [S('comment'), 1, titre], [S('comment'), 2, 'Généré par hardware/outils/generer_schemas.py']]
    root_items = []
    page = 2
    x, y = 50.8, 40.64
    # feuilles simples
    for sh in feuilles:
        su, its = sheet_block(nom, root_uuid, sh.title.split(':')[0][:40], sh.file, x, y, 63.5, 12.7, page, [],
                              sh.key)
        root_items += its
        sh.uuid = uid(nom, 'file', sh.key)
        sh.instances = [('/%s/%s' % (root_uuid, su), sh.refnum, page)]
        page += 1
        y += 22.86
    # ports
    port = feuille_port(nom)
    port.uuid = uid(nom, 'file', 'port')
    x2, y2 = 203.2, 40.64
    for k in ports:
        b = PORT_BUS[k]
        pins_map = [('SCK', 'input', 'SPI%d_SCK' % b), ('MOSI', 'input', 'SPI%d_MOSI' % b),
                    ('MISO', 'output', 'SPI%d_MISO' % b), ('~{CS}', 'input', '~{CS%d}' % k),
                    ('~{INT}', 'output', '~{INT%d}' % k)]
        su, its = sheet_block(nom, root_uuid, 'Port CAN %d' % k, port.file, x2, y2, 50.8, 15.24, page,
                              pins_map, 'port%d' % k)
        root_items += its
        port.instances.append(('/%s/%s' % (root_uuid, su), str(k), page))
        page += 1
        y2 += 30.48
    root_items.append([S('text'),
                       titre + '\nVoir docs/schema-bloc.md pour le schéma-bloc, l\'affectation des broches et la nomenclature.',
                       [S('at'), 50.8, 25.4, 0], font('left bottom'), [S('uuid'), S(uid(nom, 'root-text'))]])
    root = [S('kicad_sch'), [S('version'), 20230121], [S('generator'), S('eeschema')], [S('uuid'), S(root_uuid)],
            [S('paper'), 'A4'], [S('title_block'), [S('title'), titre]] + tb, [S('lib_symbols')]] + root_items + \
           [[S('sheet_instances'), [S('path'), '/', [S('page'), '1']]]]
    schema.write(root, os.path.join(out, nom + '.kicad_sch'))
    for sh in feuilles + [port]:
        doc = schema.build_sheet(sh, nom, root_uuid, tb)
        schema.write(doc, os.path.join(out, sh.file))
    # fichiers de projet
    with open(os.path.join(out, nom + '.kicad_pro'), 'w') as f:
        json.dump({'meta': {'filename': nom + '.kicad_pro', 'version': 1},
                   'sheets': [[root_uuid, '']], 'text_variables': {}}, f, indent=2)
    with open(os.path.join(out, 'sym-lib-table'), 'w') as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "can8")(type "KiCad")'
                '(uri "${KIPRJMOD}/../bibliotheque/can8.kicad_sym")(options "")'
                '(descr "Symboles locaux du projet Usb2Can-8-Ports"))\n)\n')
    return feuilles + [port]


def nomenclature(nom, sheets):
    """Nomenclature regroupée (valeur + empreinte), écrite en CSV à côté du projet."""
    import csv
    groups = {}
    for sh in sheets:
        for i in range(len(sh.instances)):
            for part in sh.parts:
                if part.lib_id.startswith('Mechanical:'):
                    continue
                fp = part.footprint or schema.lib_props(part.lib_id)['Footprint'][2]
                k = (part.lib_id, part.value, fp, part.dnp)
                groups.setdefault(k, []).append(part.refs[i])
    path = os.path.join(HW, nom, nom + '-nomenclature.csv')
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Quantité', 'Valeur', 'Symbole', 'Empreinte', 'Non monté', 'Références'])
        for (lib, val, fp, dnp), refs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            refs.sort(key=lambda r: (len(r), r))
            w.writerow([len(refs), val, lib, fp, 'oui' if dnp else '', ' '.join(refs)])


def main():
    bibliotheque_can8.generer(os.path.join(HW, 'bibliotheque', 'can8.kicad_sym'), schema.KICAD_SYMBOLS)
    schema._libs.clear()
    schema._flat.clear()
    mere = projet('can8-mere', 'Carte mère : STM32H723 + USB HS + alimentation + ports CAN 1 à 4',
                  [feuille_alim(), feuille_mcu(), feuille_usb(), feuille_b2b(False)], [1, 2, 3, 4])
    fille = projet('can8-fille', 'Carte fille : ports CAN 5 à 8',
                   [feuille_b2b(True)], [5, 6, 7, 8])
    nomenclature('can8-mere', mere)
    nomenclature('can8-fille', fille)
    return mere, fille


if __name__ == '__main__':
    main()
