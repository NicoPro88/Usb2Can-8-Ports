"""Génère la bibliothèque de symboles locale can8.kicad_sym.

Symboles absents de la bibliothèque standard de KiCad 7 :
  - USB3320C-EZK  : PHY USB 2.0 High Speed ULPI (Microchip), QFN-32
  - ISO1042BDW    : transceiver CAN FD isolé (TI), SOIC-16 large
  - UCC12050DVE   : convertisseur DC/DC isolé 500 mW (TI), SOIC-16 large
  - MCP2518FD-xSL : contrôleur CAN FD SPI (Microchip), SOIC-14
                    (copie du MCP2517FD-xSL de KiCad, brochage identique)

Brochages relevés dans les datasheets :
  - USB3320 : Microchip DS00001792E, Table 2-1
  - ISO1042 : TI SLLSF09, section « Pin Configuration and Functions », boîtier DW
  - UCC12050 : TI SNVSB38D, Table 5-1
"""
import copy
import os

from sexp import Sym, dump, find, parse

S = Sym
FONT = [S('effects'), [S('font'), [S('size'), 1.27, 1.27]]]
FONT_HIDE = [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], S('hide')]


def _prop(name, value, x, y, hide=False):
    return [S('property'), name, value, [S('at'), x, y, 0], FONT_HIDE if hide else FONT]


def _pin(ptype, x, y, rot, name, num, hide=False):
    p = [S('pin'), S(ptype), S('line'), [S('at'), x, y, rot], [S('length'), 2.54]]
    if hide:
        p.append(S('hide'))
    p += [[S('name'), name, FONT], [S('number'), str(num), FONT]]
    return p


def make_ic(name, ref, footprint, datasheet, desc, left, right, top=(), bottom=(), width=None):
    """left/right/top/bottom : listes de (numéro, nom, type) ou None pour un espace."""
    pitch = 2.54
    n_side = max(len(left), len(right), 1)
    longest = max([len(p[1]) for p in list(left) + list(right) if p] + [4])
    w = width or max(15.24, 2 * round((longest * 1.0 + 4) / 2.54) * 2.54 / 2 * 2)
    w = round(w / 5.08) * 5.08
    n_tb = max(len(top), len(bottom), 0)
    w = max(w, (n_tb + 1) * pitch)
    h = (n_side + 1) * pitch
    h = round(h / 5.08 + 0.49) * 5.08
    pins = []
    y0 = h / 2 - pitch
    for i, p in enumerate(left):
        if p:
            pins.append(_pin(p[2], -w / 2 - 2.54, round(y0 - i * pitch, 2), 0, p[1], p[0]))
    for i, p in enumerate(right):
        if p:
            pins.append(_pin(p[2], w / 2 + 2.54, round(y0 - i * pitch, 2), 180, p[1], p[0]))
    x0 = -((len(top) - 1) * pitch) / 2
    for i, p in enumerate(top):
        if p:
            pins.append(_pin(p[2], round(x0 + i * pitch, 2), h / 2 + 2.54, 270, p[1], p[0]))
    x0 = -((len(bottom) - 1) * pitch) / 2
    for i, p in enumerate(bottom):
        if p:
            pins.append(_pin(p[2], round(x0 + i * pitch, 2), -h / 2 - 2.54, 90, p[1], p[0]))
    sym = [S('symbol'), name, [S('pin_names'), [S('offset'), 1.016]],
           [S('in_bom'), S('yes')], [S('on_board'), S('yes')],
           _prop('Reference', ref, -w / 2, h / 2 + 1.27),
           _prop('Value', name, w / 2, h / 2 + 1.27),
           _prop('Footprint', footprint, 0, -h / 2 - 5.08, True),
           _prop('Datasheet', datasheet, 0, -h / 2 - 7.62, True),
           _prop('ki_description', desc, 0, 0, True),
           [S('symbol'), name + '_0_1',
            [S('rectangle'), [S('start'), -w / 2, h / 2], [S('end'), w / 2, -h / 2],
             [S('stroke'), [S('width'), 0.254], [S('type'), S('default')]],
             [S('fill'), [S('type'), S('background')]]]],
           [S('symbol'), name + '_1_1'] + pins]
    # justification des champs Reference / Value
    sym[5][4] = [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('justify'), S('left')]]
    sym[6][4] = [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('justify'), S('right')]]
    return sym


def usb3320():
    left = [(29, 'STP', 'input'), (31, 'DIR', 'output'), (2, 'NXT', 'output'),
            (1, 'CLKOUT', 'output'), None,
            (3, 'DATA0', 'bidirectional'), (4, 'DATA1', 'bidirectional'),
            (5, 'DATA2', 'bidirectional'), (6, 'DATA3', 'bidirectional'),
            (7, 'DATA4', 'bidirectional'), (9, 'DATA5', 'bidirectional'),
            (10, 'DATA6', 'bidirectional'), (13, 'DATA7', 'bidirectional'), None,
            (27, '~{RESETB}', 'input'), None,
            (8, 'REFSEL0', 'input'), (11, 'REFSEL1', 'input'), (14, 'REFSEL2', 'input')]
    right = [(18, 'DP', 'bidirectional'), (19, 'DM', 'bidirectional'),
             (22, 'VBUS', 'passive'), (23, 'ID', 'input'), (17, 'CPEN', 'output'), None,
             (16, 'SPK_R', 'passive'), (15, 'SPK_L', 'passive'), None,
             (26, 'REFCLK', 'input'), (25, 'XO', 'passive'), None,
             (24, 'RBIAS', 'passive'), (12, 'NC', 'no_connect')]
    top = [(21, 'VBAT', 'power_in'), (20, 'VDD33', 'power_in'), (32, 'VDDIO', 'power_in'),
           (28, 'VDD18', 'power_in'), (30, 'VDD18', 'power_in')]
    bottom = [(33, 'GND', 'power_in')]
    return make_ic('USB3320C-EZK', 'U', 'Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm',
                   'https://ww1.microchip.com/downloads/en/DeviceDoc/00001792E.pdf',
                   'PHY USB 2.0 High Speed ULPI, QFN-32 (EP = GND)', left, right, top, bottom,
                   width=25.4)


def iso1042_dw():
    left = [(1, 'VCC1', 'power_in'), None, (3, 'TXD', 'input'), (5, 'RXD', 'output'), None,
            (2, 'GND1', 'power_in'), (8, 'GND1', 'power_in'), None,
            (4, 'NC', 'no_connect'), (6, 'NC', 'no_connect'), (7, 'NC', 'no_connect')]
    right = [(11, 'VCC2', 'power_in'), (16, 'VCC2', 'power_in'), (13, 'CANH', 'bidirectional'),
             (12, 'CANL', 'bidirectional'), None,
             (9, 'GND2', 'power_in'), (10, 'GND2', 'power_in'), (15, 'GND2', 'power_in'), None,
             (14, 'NC', 'no_connect')]
    return make_ic('ISO1042BDW', 'U', 'Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm',
                   'https://www.ti.com/lit/ds/symlink/iso1042.pdf',
                   'Transceiver CAN FD isolé 5 kVrms, SOIC-16 large (DW)', left, right, width=20.32)


def ucc12050():
    left = [(3, 'VINP', 'power_in'), (1, 'EN', 'input'), (4, 'SYNC', 'input'),
            (5, '~{SYNC_OK}', 'open_collector'), None,
            (2, 'GNDP', 'power_in'), (6, 'NC', 'passive'), (7, 'NC', 'passive'), (8, 'NC', 'passive')]
    right = [(14, 'VISO', 'power_out'), (13, 'SEL', 'input'), None,
             (9, 'GNDS', 'power_in'), (15, 'GNDS', 'power_in'), (16, 'GNDS', 'power_in'),
             (10, 'NC', 'passive'), (11, 'NC', 'passive'), (12, 'NC', 'passive')]
    return make_ic('UCC12050DVE', 'U', 'Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm',
                   'https://www.ti.com/lit/ds/symlink/ucc12050.pdf',
                   'Convertisseur DC/DC isolé 500 mW, 5 kVrms renforcé, SOIC-16 large', left, right,
                   width=20.32)


def mcp2518fd_sl(kicad_symbols):
    lib = parse(open(os.path.join(kicad_symbols, 'Interface_CAN_LIN.kicad_sym')).read())[0]
    src = next(s for s in find(lib, 'symbol') if s[1] == 'MCP2517FD-xSL')
    s = copy.deepcopy(src)
    s[1] = 'MCP2518FD-xSL'
    for e in s:
        if isinstance(e, list) and e[0] == 'symbol':
            e[1] = e[1].replace('MCP2517FD-xSL', 'MCP2518FD-xSL')
        if isinstance(e, list) and e[0] == 'property':
            if e[1] == 'Value':
                e[2] = 'MCP2518FD-xSL'
            elif e[1] == 'Datasheet':
                e[2] = 'https://ww1.microchip.com/downloads/en/DeviceDoc/MCP2518FD-External-CAN-FD-Controller-with-SPI-Interface-20006027B.pdf'
            elif e[1] == 'ki_description':
                e[2] = 'Contrôleur CAN FD externe à interface SPI, SOIC-14 (brochage identique au MCP2517FD)'
    return s


def generer(path, kicad_symbols):
    lib = [S('kicad_symbol_lib'), [S('version'), 20220914], [S('generator'), S('can8_outils')],
           usb3320(), iso1042_dw(), ucc12050(), mcp2518fd_sl(kicad_symbols)]
    with open(path, 'w') as f:
        f.write(dump(lib) + '\n')
