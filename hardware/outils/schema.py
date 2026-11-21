"""Petit moteur de génération de schémas KiCad 7 (format 20230121).

Chaque composant est placé tel quel (sans rotation) ; chaque broche reçoit un
petit fil et une étiquette de net (locale, globale ou hiérarchique) ou un
symbole d'alimentation. Les broches inutilisées reçoivent un drapeau « non
connecté ». Le placement est automatique, en lignes, à partir de l'encombrement
estimé de chaque composant.
"""
import copy
import math
import os
import uuid as _uuid

from sexp import Sym, dump, find, parse, pins

S = Sym
NS = _uuid.UUID('6f1c3a52-6c1e-4b4a-9a39-0c8a5b3c2d10')
KICAD_SYMBOLS = os.environ.get('KICAD7_SYMBOL_DIR', '/usr/share/kicad/symbols')
LOCAL_LIB = os.path.join(os.path.dirname(__file__), '..', 'bibliotheque', 'can8.kicad_sym')

POWER = {'+3V3': 'power:+3V3', '+5V': 'power:+5V', 'GND': 'power:GND'}
PAPERS = [('A4', 297, 210), ('A3', 420, 297), ('A2', 594, 420), ('A1', 841, 594), ('A0', 1189, 841)]
STUB = 2.54
G = 2.54


def uid(*parts):
    return str(_uuid.uuid5(NS, '/'.join(str(p) for p in parts)))


def snap(v, g=G):
    return round(round(v / g) * g, 3)


def font(justify=None, hide=False):
    e = [S('effects'), [S('font'), [S('size'), 1.27, 1.27]]]
    if justify:
        e.append([S('justify')] + [S(j) for j in justify.split()])
    if hide:
        e.append(S('hide'))
    return e


# ---------------------------------------------------------------- bibliothèques
_libs = {}


def _load(lib):
    if lib not in _libs:
        path = LOCAL_LIB if lib == 'can8' else os.path.join(KICAD_SYMBOLS, lib + '.kicad_sym')
        t = parse(open(path).read())[0]
        _libs[lib] = {s[1]: s for s in find(t, 'symbol')}
    return _libs[lib]


_flat = {}

# Symboles renommés dans KiCad 8+ : nom KiCad 9 -> nom dans la bibliothèque KiCad 7 lue ici.
# Le schéma porte le nom KiCad 9 (« mise à jour depuis la bibliothèque » possible),
# le dessin vient de la bibliothèque KiCad 7 (mêmes broches aux mêmes positions).
RENOMMES = {'Connector:DE9_Pins_MountingHoles': 'DE9_Plug_MountingHoles'}


def lib_symbol(lib_id):
    """Symbole aplati (héritage « extends » résolu), nommé « Lib:Nom »."""
    if lib_id in _flat:
        return _flat[lib_id]
    lib, name = lib_id.split(':', 1)
    src = _load(lib)[RENOMMES.get(lib_id, name)]
    ext = find(src, 'extends')
    if ext:
        pname = ext[0][1]
        parent = lib_symbol(lib + ':' + pname)
        props = {p[1]: p for p in find(parent, 'property')}
        for p in find(src, 'property'):
            props[p[1]] = p
        out = [S('symbol'), lib_id]
        for e in parent[2:]:
            if isinstance(e, list) and e[0] == 'property':
                continue
            if isinstance(e, list) and e[0] == 'symbol':
                e = copy.deepcopy(e)
                e[1] = name + e[1][len(pname):]
            out.append(e)
        # les propriétés juste après les drapeaux
        idx = next(i for i, e in enumerate(out) if isinstance(e, list) and e[0] == 'symbol')
        out[idx:idx] = [copy.deepcopy(p) for p in props.values()]
    else:
        out = copy.deepcopy(src)
        out[1] = lib_id
        for e in out[2:]:
            if isinstance(e, list) and e[0] == 'symbol' and src[1] != name:
                e[1] = name + e[1][len(src[1]):]
    out = [e for e in out if not (isinstance(e, list) and e[0] == 'extends')]
    _flat[lib_id] = out
    return out


def lib_pins(lib_id):
    return pins(lib_symbol(lib_id))


def lib_props(lib_id):
    return {p[1]: p for p in find(lib_symbol(lib_id), 'property')}


# ---------------------------------------------------------------- géométrie
DIRS = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}  # écran (y vers le bas)


def pin_geom(p, sx, sy):
    """Point de connexion absolu et direction « vers l'extérieur » (angle écran)."""
    x, y = sx + p['x'], sy - p['y']
    out = int((p['rot'] + 180) % 360)
    return round(x, 3), round(y, 3), out


def text_len(s):
    return len(s) * 1.0 + 1.5


class Part:
    def __init__(self, lib_id, letter, value, nets, footprint=None, fields=None, dnp=False,
                 nc_default=False, note=None):
        self.lib_id, self.letter, self.value = lib_id, letter, value
        self.nets = {str(k): v for k, v in nets.items()}
        self.footprint = footprint
        self.fields = fields or {}
        self.dnp = dnp
        self.nc_default = nc_default
        self.note = note
        self.pins = lib_pins(lib_id)
        nums = {p['num'] for p in self.pins}
        for k in self.nets:
            if k not in nums:
                raise ValueError('%s : broche %s inconnue' % (lib_id, k))
        if not nc_default:
            missing = [p['num'] for p in self.pins if p['num'] not in self.nets and p['type'] != 'no_connect']
            if missing:
                raise ValueError('%s %s : broches sans net %s' % (lib_id, value, missing))

    def net_of(self, num):
        return self.nets.get(num)

    def bbox(self):
        xs = [p['x'] for p in self.pins] + [0]
        ys = [-p['y'] for p in self.pins] + [0]
        # corps du symbole (approximé par ses broches) + champs
        x0, x1, y0, y1 = min(xs) - 2, max(xs) + 2, min(ys) - 4, max(ys) + 4
        for p in self.pins:
            x, y, d = pin_geom(p, 0, 0)
            net = self.net_of(p['num'])
            ext = STUB + (text_len(net) + 3 if net else 1)
            if net in POWER:
                ext = STUB + 5
            dx, dy = DIRS[d]
            x0, x1 = min(x0, x + dx * ext), max(x1, x + dx * ext)
            y0, y1 = min(y0, y + dy * ext - 1.5), max(y1, y + dy * ext + 1.5)
        return x0, y0, x1, y1


class Sheet:
    def __init__(self, key, file, title, refnum, hier=(), globals_=(), paper=None, notes=()):
        self.key, self.file, self.title = key, file, title
        self.refnum = refnum            # préfixe numérique des références, ex. "11"
        self.hier = dict(hier)          # net -> forme (input/output/...)
        self.globals = set(globals_)
        self.parts = []
        self.notes = list(notes)
        self.paper = paper
        self.extra = []                 # éléments graphiques additionnels
        self.instances = []             # (chemin, préfixe, page)

    def add(self, *a, **k):
        p = Part(*a, **k)
        self.parts.append(p)
        return p


def label_kind(sheet, net):
    if net in POWER:
        return 'power'
    if net in sheet.hier:
        return 'hier'
    if net in sheet.globals:
        return 'global'
    return 'local'


def layout(sheet):
    boxes = [p.bbox() for p in sheet.parts]
    start = [n for n, _, _ in PAPERS].index(sheet.paper or 'A4')
    for name, W, H in PAPERS[start:]:
        margin, top = 25.4, 30.48
        x, y, row_h = margin, top, 0
        pos = []
        ok = True
        for (x0, y0, x1, y1) in boxes:
            w, h = x1 - x0, y1 - y0
            if x + w > W - margin and x > margin:
                x, y, row_h = margin, y + row_h + 7.62, 0
            sx, sy = snap(x - x0), snap(y - y0)
            pos.append((sx, sy))
            x += w + 7.62
            row_h = max(row_h, h)
        notes_h = 5 * sum(n.count('\n') + 2 for n in sheet.notes)
        if y + row_h + notes_h > H - 40:
            ok = False
        if ok:
            return name, W, H, pos, y + row_h
    raise RuntimeError('feuille trop grande : ' + sheet.key)


def build_sheet(sheet, project, root_uuid, title_block):
    paper, W, H, pos, bottom = layout(sheet)
    items = []
    lib_ids = []
    counters = {}
    pwr_count = [0]
    insts = sheet.instances  # [(path, prefix, page)]

    def refs_for(letter):
        counters[letter] = counters.get(letter, 0) + 1
        n = counters[letter]
        return [('%s%s%02d' % (letter, pre, n)) for (_, pre, _) in insts]

    def pwr_refs():
        pwr_count[0] += 1
        return ['#PWR%s%03d' % (pre, pwr_count[0]) for (_, pre, _) in insts]

    def flg_refs():
        pwr_count[0] += 1
        return ['#FLG%s%03d' % (pre, pwr_count[0]) for (_, pre, _) in insts]

    def place_symbol(lib_id, x, y, rot, refs, value, footprint, fields, dnp, key, hide_ref=False,
                     override=None):
        if lib_id not in lib_ids:
            lib_ids.append(lib_id)
        props = lib_props(lib_id)
        u = uid(project, sheet.key, key)
        sym = [S('symbol'), [S('lib_id'), lib_id], [S('at'), x, y, rot], [S('unit'), 1],
               [S('in_bom'), S('yes')], [S('on_board'), S('yes')], [S('dnp'), S('yes' if dnp else 'no')],
               [S('uuid'), S(u)]]
        vals = {'Reference': refs[0], 'Value': value}
        if footprint is not None:
            vals['Footprint'] = footprint
        for name, p in props.items():
            if name.startswith('ki_'):
                continue
            v = vals.get(name, p[2])
            at = find(p, 'at')[0]
            px, py = float(at[1]), float(at[2])
            prot = float(at[3]) if len(at) > 3 else 0
            if rot:
                a = math.radians(rot)
                px, py = (px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a))
            eff = copy.deepcopy(find(p, 'effects')[0])
            if hide_ref and name == 'Reference' and S('hide') not in eff:
                eff.append(S('hide'))
            at_xy = [S('at'), round(x + px, 3), round(y - py, 3), prot]
            if override and name in override:
                at_xy = [S('at')] + list(override[name])
            sym.append([S('property'), name, v, at_xy, eff])
        for k2, v2 in fields.items():
            sym.append([S('property'), k2, v2, [S('at'), x, y, 0], font(hide=True)])
        for p in lib_pins(lib_id):
            sym.append([S('pin'), p['num'], [S('uuid'), S(uid(u, 'pin', p['num']))]])
        inst = [S('project'), project]
        for (path, _, _), r in zip(insts, refs):
            inst.append([S('path'), path, [S('reference'), r], [S('unit'), 1]])
        sym.append([S('instances'), inst])
        items.append(sym)

    def wire(x1, y1, x2, y2, key):
        items.append([S('wire'), [S('pts'), [S('xy'), x1, y1], [S('xy'), x2, y2]],
                      [S('stroke'), [S('width'), 0], [S('type'), S('default')]],
                      [S('uuid'), S(uid(project, sheet.key, 'w', key))]])

    def label(net, x, y, d, key):
        kind = label_kind(sheet, net)
        if kind == 'power':
            # rotation du symbole d'alimentation pour pointer vers l'extérieur
            up = net != 'GND'
            if up:
                rot = {90: 0, 180: 90, 270: 180, 0: 270}[d]
            else:
                rot = {270: 0, 0: 90, 90: 180, 180: 270}[d]
            override = None
            if d in (0, 180):
                # texte horizontal, au-delà du symbole
                dx = 1 if d == 0 else -1
                override = {'Value': (round(x + dx * (4.2 + len(net) * 0.55), 3), y, 90)}
            place_symbol(POWER[net], x, y, rot, pwr_refs(), net, None, {}, False, ('pwr',) + key,
                         hide_ref=True, override=override)
            return
        just = 'left' if d in (0, 90) else 'right'
        ang = {0: 0, 90: 90, 180: 180, 270: 270}[d]
        u = uid(project, sheet.key, 'l', key)
        if kind == 'local':
            items.append([S('label'), net, [S('at'), x, y, ang], font(just + ' bottom'), [S('uuid'), S(u)]])
        elif kind == 'global':
            items.append([S('global_label'), net, [S('shape'), S('passive')], [S('at'), x, y, ang],
                          [S('fields_autoplaced')], font(just), [S('uuid'), S(u)],
                          [S('property'), 'Intersheetrefs', '${INTERSHEET_REFS}', [S('at'), x, y, 0],
                           font(just, hide=True)]])
        else:
            items.append([S('hierarchical_label'), net, [S('shape'), S(sheet.hier[net])],
                          [S('at'), x, y, ang], font(just), [S('uuid'), S(u)]])

    for i, (part, (sx, sy)) in enumerate(zip(sheet.parts, pos)):
        refs = refs_for(part.letter)
        part.refs = refs
        fp = part.footprint
        place_symbol(part.lib_id, sx, sy, 0, refs, part.value, fp, part.fields, part.dnp, ('part', i))
        # regroupe les broches voisines d'un même côté reliées au même net
        geo = []
        for p in part.pins:
            x, y, d = pin_geom(p, sx, sy)
            geo.append((d, x, y, p, part.net_of(p['num'])))
        sides = {}
        for g in geo:
            d, x, y = g[0], g[1], g[2]
            line = round(x, 2) if d in (0, 180) else round(y, 2)
            sides.setdefault((d, line), []).append(g)
        for (d, line), lst in sides.items():
            lst.sort(key=lambda g: g[2] if d in (0, 180) else g[1])
            runs = []
            for g in lst:
                if runs and g[4] is not None and runs[-1][-1][4] == g[4]:
                    runs[-1].append(g)
                else:
                    runs.append([g])
            for run in runs:
                d0, x0, y0, p0, net = run[0]
                key = (i, p0['num'])
                if net is None:
                    items.append([S('no_connect'), [S('at'), x0, y0],
                                  [S('uuid'), S(uid(project, sheet.key, 'nc', key))]])
                    continue
                dx, dy = DIRS[d]
                ends = []
                for (_, x, y, p, _) in run:
                    ex, ey = round(x + dx * STUB, 3), round(y + dy * STUB, 3)
                    wire(x, y, ex, ey, (i, p['num']))
                    ends.append((ex, ey))
                for k in range(1, len(ends)):
                    wire(ends[k - 1][0], ends[k - 1][1], ends[k][0], ends[k][1], (i, 'bus', run[k][3]['num']))
                    if k < len(ends) - 1:
                        items.append([S('junction'), [S('at'), ends[k][0], ends[k][1]], [S('diameter'), 0],
                                      [S('color'), 0, 0, 0, 0],
                                      [S('uuid'), S(uid(project, sheet.key, 'j', i, run[k][3]['num']))]])
                # étiquette : en bas du groupe pour GND, en haut sinon
                ex, ey = ends[-1] if net == 'GND' else ends[0]
                label(net, ex, ey, d, key)

    # drapeaux d'alimentation (PWR_FLAG) demandés par la feuille
    for j, net in enumerate(getattr(sheet, 'pwr_flags', [])):
        x, y = snap(25.4 + j * 22.86), snap(H - 30.48)
        place_symbol('power:PWR_FLAG', x, y, 0, flg_refs(), 'PWR_FLAG', None, {}, False, ('flag', net),
                     hide_ref=True)
        ex, ey = x, round(y + STUB, 3)
        wire(x, y, ex, ey, ('flag', net))
        label(net, ex, ey, 270, ('flag', net))

    # notes de conception
    ty = bottom + 10
    for k, n in enumerate(sheet.notes):
        items.append([S('text'), n, [S('at'), 25.4, round(ty, 2), 0], font('left top'),
                      [S('uuid'), S(uid(project, sheet.key, 'note', k))]])
        ty += 5 * (n.count('\n') + 2)

    items += sheet.extra
    libsyms = [S('lib_symbols')] + [lib_symbol(l) for l in lib_ids]
    tb = [S('title_block'), [S('title'), sheet.title]] + title_block
    doc = [S('kicad_sch'), [S('version'), 20230121], [S('generator'), S('eeschema')],
           [S('uuid'), S(sheet.uuid)], [S('paper'), paper], tb, libsyms] + items
    return doc


def write(doc, path):
    with open(path, 'w') as f:
        f.write(dump(doc) + '\n')
