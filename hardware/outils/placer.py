#!/usr/bin/env python3
"""Placement des composants des cartes mère et fille (KiCad 7, API Python pcbnew).

    python3 hardware/outils/placer.py

Régénère les schémas, lit la netlist exportée par kicad-cli, puis écrit
hardware/can8-mere/can8-mere.kicad_pcb et hardware/can8-fille/can8-fille.kicad_pcb :
contour, trous de fixation, fenêtres d'accès, zones interdites de la barrière
d'isolement, plans internes, empreintes placées avec leurs nets. Rien n'est routé :
le chevelu (ratsnest) montre les liaisons à tirer.

Les gros composants (connecteurs, circuits intégrés, alimentation) sont placés à des
positions fixées dans ce fichier. Les passifs sont placés automatiquement au plus près
des broches auxquelles ils se rattachent : découplage contre la broche d'alimentation de
son circuit, résistance série côté émetteur, condensateurs de charge contre le quartz.
Chaque passif reste dans sa zone (côté logique ou côté bus de son port, zone arrière)
et aucun courtyard n'en chevauche un autre.

Contrôles en fin de placement (code de sortie 1 en cas d'erreur) :
  - chevauchements de courtyards, composants hors carte ;
  - pastilles dans la barrière d'isolement ou entre deux ports ;
  - empilage : connecteur carte à carte aligné broche à broche avec le même net
    des deux côtés, DB9 superposés, trous de fixation communs alignés ;
  - DRC de KiCad avec les règles du projet : aucune erreur hormis les liaisons non routées,
    la sérigraphie à ranger et les plans pas encore reliés par des vias.

Coordonnées : x de gauche à droite vu de dessus, y de l'arrière (USB, alimentation)
vers l'avant (DB9). Les deux cartes partagent le même repère : un même (x, y) est sur la
même verticale une fois les cartes empilées. La carte fille couvre y = 40 à 115.

Ce script sert de point de départ. Une fois la carte retouchée dans KiCad, ne plus le relancer
sur le projet modifié.
"""
import collections
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import generer_schemas as gen  # noqa: E402
import sexp  # noqa: E402

FP_DIR = os.environ.get('KICAD7_FOOTPRINT_DIR', '/usr/share/kicad/footprints')

# ------------------------------------------------------------------ géométrie générale (mm)
OX, OY = 50.0, 40.0          # position de la carte sur la feuille
LARGEUR = 156.0
AVANT = 115.0                # bord avant (DB9) des deux cartes
ARRIERE = {'can8-mere': 0.0, 'can8-fille': 40.0}
COLONNE = {k: 24.0 + 36.0 * ((k - 1) % 4) for k in range(1, 9)}   # axe de chaque port
BARRIERE = 80.0              # axe de la barrière d'isolement (ISO1042, UCC12050)
DEMI_BARRIERE = 3.0          # bande sans cuivre : y = 77 à 83
BANDE_X = (7.0, 149.0)       # la bande laisse libres les bords (piste CHASSIS, trous)
DEMI_ECART_PORTS = 1.5       # bande sans cuivre entre deux ports côté bus
FOND_LOGIQUE = 53.0          # limite arrière des zones logiques des ports
JEU = 0.1                    # écart minimal entre courtyards
TROUS = {'can8-mere': [(4, 4), (152, 4), (4, 44), (152, 44), (4, 111), (152, 111)],
         'can8-fille': [(4, 44), (152, 44), (4, 111), (152, 111)]}
B2B_BROCHE1 = (55.87, 49.5)  # broche 1 du connecteur carte à carte (2 x 20 centré sur x = 80)
SW_Y = 95.4                  # interrupteurs de terminaison
SW_DX = {'can8-mere': -9.0, 'can8-fille': 9.0}   # fenêtre de la mère au-dessus de celui de la fille

MASSES = {'GND', 'GND_ISO'}
GROS_NETS = MASSES | {'+3V3', '+5V', 'VISO', 'CHASSIS', '+VIN'}


def MM(v):
    return pcbnew.FromMM(v)


def V(x, y):
    return pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))


def base(net):
    return net.split('/')[-1]


def est_alim(net):
    b = base(net)
    return b in GROS_NETS or b.startswith('+') or b.startswith('VCAP')


# ------------------------------------------------------------------ netlist
def netlist(nom):
    sch = os.path.join(gen.HW, nom, nom + '.kicad_sch')
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'n.net')
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '-o', out, sch], check=True,
                       capture_output=True)
        t = sexp.parse(open(out).read())[0]

    def val(node, key):
        return sexp.find(node, key)[0][1]

    comps = {}
    for c in sexp.find(sexp.find(t, 'components')[0], 'comp'):
        sp = sexp.find(c, 'sheetpath')[0]
        props = {val(p, 'name'): val(p, 'value') for p in sexp.find(c, 'property')}
        comps[val(c, 'ref')] = {
            'value': val(c, 'value'), 'footprint': val(c, 'footprint'),
            'path': val(sp, 'tstamps') + val(c, 'tstamps'),
            'sheetname': props.get('Sheetname', ''), 'sheetfile': props.get('Sheetfile', '')}
    nets = collections.OrderedDict()
    for n in sexp.find(sexp.find(t, 'nets')[0], 'net'):
        nets[val(n, 'name')] = [(val(x, 'ref'), val(x, 'pin')) for x in sexp.find(n, 'node')]
    return comps, nets


# ------------------------------------------------------------------ géométrie des empreintes
def tourner(x, y, theta):
    """Rotation KiCad (sens trigonométrique à l'écran, y vers le bas)."""
    return {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}[theta % 360]


class Geo:
    """Courtyard et pastilles d'une empreinte en orientation 0, face avant."""

    def __init__(self, fp):
        xs, ys = [], []
        for g in fp.GraphicalItems():
            if g.GetLayerName() in ('F.Courtyard', 'B.Courtyard'):
                bb = g.GetBoundingBox()
                xs += [bb.GetLeft(), bb.GetRight()]
                ys += [bb.GetTop(), bb.GetBottom()]
        self.pads = [(p.GetNumber(), pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
                     for p in fp.Pads()]
        if not xs:  # pas de courtyard : pastilles + 0,25 mm
            for p in fp.Pads():
                bb = p.GetBoundingBox()
                xs += [bb.GetLeft() - MM(0.25), bb.GetRight() + MM(0.25)]
                ys += [bb.GetTop() - MM(0.25), bb.GetBottom() + MM(0.25)]
        self.rect = tuple(pcbnew.ToMM(v) for v in (min(xs), min(ys), max(xs), max(ys)))

    def rect_a(self, x, y, theta):
        x0, y0, x1, y1 = self.rect
        pts = [tourner(a, b, theta) for a in (x0, x1) for b in (y0, y1)]
        return (x + min(p[0] for p in pts), y + min(p[1] for p in pts),
                x + max(p[0] for p in pts), y + max(p[1] for p in pts))

    def pads_a(self, x, y, theta):
        out = []
        for num, px, py in self.pads:
            dx, dy = tourner(px, py, theta)
            out.append((num, x + dx, y + dy))
        return out


def charger(footprint):
    lib, name = footprint.split(':', 1)
    fp = pcbnew.FootprintLoad(os.path.join(FP_DIR, lib + '.pretty'), name)
    if fp is None:
        raise SystemExit('empreinte introuvable : ' + footprint)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def chevauche(a, b, jeu=0.0):
    return a[0] < b[2] + jeu and b[0] < a[2] + jeu and a[1] < b[3] + jeu and b[1] < a[3] + jeu


def contenu(a, zone):
    return a[0] >= zone[0] - 1e-6 and a[1] >= zone[1] - 1e-6 and a[2] <= zone[2] + 1e-6 and a[3] <= zone[3] + 1e-6


# ------------------------------------------------------------------ carte
class Carte:
    def __init__(self, nom, sheets):
        self.nom = nom
        self.dir = os.path.join(gen.HW, nom)
        self.path = os.path.join(self.dir, nom + '.kicad_pcb')
        self.comps, self.nets = netlist(nom)
        self.pin_net = {node: n for n, nodes in self.nets.items() for node in nodes}
        self.y0 = ARRIERE[nom]
        self.contour = (0.0, self.y0, LARGEUR, AVANT)
        pcbnew.KIID.SeedGenerator(1 if nom == 'can8-mere' else 2)   # identifiants reproductibles
        self.board = pcbnew.NewBoard(self.path)
        self.board.SetCopperLayerCount(4)
        self.netinfo = {}
        for n in self.nets:
            ni = pcbnew.NETINFO_ITEM(self.board, n)
            self.board.Add(ni)
            self.netinfo[n] = ni
        self.fps, self.geo = {}, {}
        for ref, c in self.comps.items():
            fp = charger(c['footprint'])
            fp.SetReference(ref)
            fp.SetValue(c['value'])
            fp.SetPath(pcbnew.KIID_PATH(c['path']))
            fp.SetProperty('Sheetname', c['sheetname'])
            fp.SetProperty('Sheetfile', c['sheetfile'])
            self.geo[ref] = Geo(fp)
            self.board.Add(fp)
            for pad in fp.Pads():
                n = self.pin_net.get((ref, pad.GetNumber()))
                if n:
                    pad.SetNet(self.netinfo[n])
            self.fps[ref] = fp
        # ordre des composants dans les feuilles (pour rattacher les découplages)
        self.info = {}
        for sh in sheets:
            for i, (_, pre, _) in enumerate(sh.instances):
                for j, part in enumerate(sh.parts):
                    self.info[part.refs[i]] = (sh, i, j, int(pre) if sh.key == 'port_can' else None)
        self.place = {}       # ref -> (x, y, theta, face)
        self.rects = {}       # ref -> rect occupé
        self.obstacles = []   # (nom, rect)
        self.cap_par_broche = collections.Counter()

    # --- positions
    def pads_places(self, ref):
        x, y, th, face = self.place[ref]
        if face == 'dessous':
            fp = self.fps[ref]
            return [(p.GetNumber(), pcbnew.ToMM(p.GetPosition().x) - OX, pcbnew.ToMM(p.GetPosition().y) - OY)
                    for p in fp.Pads()]
        return self.geo[ref].pads_a(x, y, th)

    def poser(self, ref, x, y, theta):
        x, y = round(x, 3), round(y, 3)
        self.place[ref] = (x, y, theta, 'dessus')
        self.rects[ref] = self.geo[ref].rect_a(x, y, theta)
        fp = self.fps[ref]
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(theta)

    def poser_dessous(self, ref, cible_pads):
        """Empreinte retournée sous la carte, pastilles superposées à cible_pads {num: (x, y)}."""
        fp = self.fps[ref]
        fp.SetPosition(V(0, 0))
        fp.Flip(fp.GetPosition(), True)
        for th in (0, 90, 180, 270):
            fp.SetOrientationDegrees(th)
            fp.SetPosition(V(0, 0))
            p1 = [p for p in fp.Pads() if p.GetNumber() == '1'][0].GetPosition()
            dx = cible_pads['1'][0] - (pcbnew.ToMM(p1.x) - OX)
            dy = cible_pads['1'][1] - (pcbnew.ToMM(p1.y) - OY)
            fp.SetPosition(V(dx, dy))
            ok = all(abs(pcbnew.ToMM(p.GetPosition().x) - OX - cible_pads[p.GetNumber()][0]) < 0.01 and
                     abs(pcbnew.ToMM(p.GetPosition().y) - OY - cible_pads[p.GetNumber()][1]) < 0.01
                     for p in fp.Pads())
            if ok:
                self.place[ref] = (dx, dy, th, 'dessous')
                xs = [pcbnew.ToMM(p.GetPosition().x) - OX for p in fp.Pads()]
                ys = [pcbnew.ToMM(p.GetPosition().y) - OY for p in fp.Pads()]
                # pastilles traversantes : la face avant est occupée aussi
                self.rects[ref] = (min(xs) - 1.6, min(ys) - 1.6, max(xs) + 1.6, max(ys) + 1.6)
                return
        raise SystemExit('%s : impossible de superposer les broches' % ref)

    def centroide(self, net, sauf, instance=None, prefere=('Y', 'U', 'J')):
        pts = collections.defaultdict(list)
        for ref, pin in self.nets.get(net, []):
            if ref == sauf or ref not in self.place:
                continue
            if instance is not None and self.info.get(ref, (None, None))[:2] != instance:
                continue
            lettre = re.match(r'[A-Z]+', ref).group(0)
            for num, x, y in self.pads_places(ref):
                if num == pin:
                    pts[lettre].append((x, y))
        for lettre in prefere:
            if pts.get(lettre):
                p = pts[lettre]
                return (sum(a for a, _ in p) / len(p), sum(b for _, b in p) / len(p))
        tous = [q for v in pts.values() for q in v]
        if tous:
            return (sum(a for a, _ in tous) / len(tous), sum(b for _, b in tous) / len(tous))
        return None

    def orienter(self, ref, x, y, extra=None):
        """Orientation qui rapproche le plus les broches de leurs correspondants déjà placés."""
        geo = self.geo[ref]
        cibles = {}
        for (r, pin), net in self.pin_net.items():
            if r != ref or base(net) in GROS_NETS or net.startswith('unconnected'):
                continue
            c = (extra or {}).get(base(net)) or self.centroide(net, ref, prefere=())
            if c:
                cibles[pin] = c
        best = None
        for th in (0, 90, 180, 270):
            cout = sum(math.hypot(px - cibles[n][0], py - cibles[n][1])
                       for n, px, py in geo.pads_a(x, y, th) if n in cibles)
            if best is None or cout < best[0] - 1e-6:
                best = (cout, th)
        return best[1]

    # --- placement automatique des passifs
    def libre(self, rect, zone):
        if not contenu(rect, zone):
            return False
        for r in self.rects.values():
            if chevauche(rect, r, JEU):
                return False
        for _, r in self.obstacles:
            if chevauche(rect, r, JEU):
                return False
        return True

    def cible(self, ref):
        """Point d'attache et net d'attache d'un composant à placer automatiquement."""
        sh, i, j, port = self.info[ref]
        inst = (sh, i)
        nets = sorted({self.pin_net[(r, p)] for (r, p) in self.pin_net if r == ref
                       and not self.pin_net[(r, p)].startswith('unconnected')})
        masses = [n for n in nets if base(n) in MASSES]
        alims = [n for n in nets if n not in masses and est_alim(n)]
        lettre = re.match(r'[A-Z]+', ref).group(0)
        if lettre == 'C' and masses and alims and len(nets) == 2:
            # découplage : broche d'alimentation du circuit précédent dans la feuille
            net = alims[0]
            parts = sh.parts
            proprio = None
            ordre = list(range(j - 1, -1, -1)) + list(range(j + 1, len(parts)))
            for k in ordre:
                r = parts[k].refs[i]
                if re.match(r'(U|L|J)\d', r) and r in self.place and \
                        any(self.pin_net.get((r, num)) == net for num, _, _ in self.pads_places(r)):
                    proprio = r
                    break
            if proprio:
                broches = [(num, x, y) for num, x, y in self.pads_places(proprio)
                           if self.pin_net.get((proprio, num)) == net]
                num, x, y = min(broches, key=lambda b: (self.cap_par_broche[(proprio, b[0])],
                                                         int(b[0]) if b[0].isdigit() else 999))
                self.cap_par_broche[(proprio, num)] += 1
                return (x, y), net
        specifiques = [n for n in nets if base(n) not in GROS_NETS]
        specifiques.sort(key=lambda n: len(self.nets[n]))
        for n in specifiques:
            c = self.centroide(n, ref, inst) or self.centroide(n, ref)
            if c:
                return c, n
        # à défaut : à côté du composant précédent dans la feuille
        for k in range(j - 1, -1, -1):
            r = sh.parts[k].refs[i]
            if r in self.place:
                return self.place[r][:2], None
        z = self.zone(ref)
        return ((z[0] + z[2]) / 2, (z[1] + z[3]) / 2), None

    def zone(self, ref):
        sh, i, j, port = self.info[ref]
        if port is None:
            return (0.5, self.y0 + 0.5, LARGEUR - 0.5, FOND_LOGIQUE - 0.5)
        cx = COLONNE[port]
        nets = {base(self.pin_net[(r, p)]) for (r, p) in self.pin_net if r == ref}
        if nets & {'GND_ISO', 'VISO', 'CANH', 'CANL', 'TERM'}:
            return (cx - 18 + DEMI_ECART_PORTS + 0.2, BARRIERE + DEMI_BARRIERE + 0.2,
                    cx + 18 - DEMI_ECART_PORTS - 0.2, AVANT - 0.5)
        return (max(cx - 17.5, 0.5), FOND_LOGIQUE, min(cx + 17.5, LARGEUR - 0.5),
                BARRIERE - DEMI_BARRIERE - 0.2)

    def placer_auto(self, ref, pas=0.25):
        (tx, ty), net = self.cible(ref)
        tx, ty = round(tx / pas) * pas, round(ty / pas) * pas
        geo, zone = self.geo[ref], self.zone(ref)
        attache = [num for (r, num), n in self.pin_net.items() if r == ref and n == net]
        best, r_trouve = None, None
        for dx, dy, r in OFFSETS:
            if r_trouve is not None and r > r_trouve + 2.0:
                break
            x, y = tx + dx, ty + dy
            for th in (0, 90, 180, 270):
                rect = geo.rect_a(x, y, th)
                if not self.libre(rect, zone):
                    continue
                if attache:
                    d = min(math.hypot(px - tx, py - ty) for n, px, py in geo.pads_a(x, y, th) if n in attache)
                else:
                    d = r
                cout = d + 0.2 * r + (0.01 if th in (90, 270) else 0)
                if best is None or cout < best[0]:
                    best = (cout, x, y, th)
                if r_trouve is None:
                    r_trouve = r
        if best is None:
            raise SystemExit('%s : aucune place libre près de (%.1f, %.1f)' % (ref, tx, ty))
        self.poser(ref, best[1], best[2], best[3])


def _offsets(pas=0.25, rayon=30.0):
    n = int(rayon / pas)
    pts = [(i * pas, j * pas, math.hypot(i, j) * pas) for i in range(-n, n + 1) for j in range(-n, n + 1)
           if math.hypot(i, j) * pas <= rayon]
    pts.sort(key=lambda p: (p[2], p[0], p[1]))
    return pts


OFFSETS = _offsets()


# ------------------------------------------------------------------ dessin de la carte
def segment(board, layer, a, b, w=0.1):
    s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(V(*a))
    s.SetEnd(V(*b))
    s.SetLayer(layer)
    s.SetWidth(MM(w))
    board.Add(s)


def arc(board, layer, a, m, b, w=0.1):
    s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
    s.SetArcGeometry(V(*a), V(*m), V(*b))
    s.SetLayer(layer)
    s.SetWidth(MM(w))
    board.Add(s)


def rect_arrondi(board, layer, x0, y0, x1, y1, r, w=0.1):
    k = r * (1 - math.sqrt(0.5))
    segment(board, layer, (x0 + r, y0), (x1 - r, y0), w)
    segment(board, layer, (x1, y0 + r), (x1, y1 - r), w)
    segment(board, layer, (x1 - r, y1), (x0 + r, y1), w)
    segment(board, layer, (x0, y1 - r), (x0, y0 + r), w)
    arc(board, layer, (x1 - r, y0), (x1 - k, y0 + k), (x1, y0 + r), w)
    arc(board, layer, (x1, y1 - r), (x1 - k, y1 - k), (x1 - r, y1), w)
    arc(board, layer, (x0 + r, y1), (x0 + k, y1 - k), (x0, y1 - r), w)
    arc(board, layer, (x0, y0 + r), (x0 + k, y0 + k), (x0 + r, y0), w)


def texte(board, layer, txt, x, y, h=1.2, angle=0, epaisseur=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(txt)
    t.SetPosition(V(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(h), MM(h)))
    t.SetTextThickness(MM(epaisseur or h * 0.15))
    t.SetTextAngleDegrees(angle)
    board.Add(t)


def polygone(zone, pts):
    ol = zone.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(MM(OX + x), MM(OY + y))


def zone_interdite(board, nom, x0, y0, x1, y1):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(True)
    z.SetDoNotAllowCopperPour(True)
    z.SetDoNotAllowFootprints(False)
    z.SetLayerSet(pcbnew.LSET.AllCuMask(4))
    z.SetZoneName(nom)
    polygone(z, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    board.Add(z)


def plan(board, netinfo, layer, pts, nom, priorite=0):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(netinfo)
    z.SetZoneName(nom)
    z.SetLocalClearance(MM(0.3))
    z.SetMinThickness(MM(0.25))
    z.SetAssignedPriority(priorite)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    polygone(z, pts)
    board.Add(z)


# ------------------------------------------------------------------ placement
def ref_port(lettre, k, n):
    return '%s%d%02d' % (lettre, k, n)


def placer_port(c, k):
    cx = COLONNE[k]
    r = lambda lettre, n: ref_port(lettre, k, n)  # noqa: E731
    # DB9 : broche 1 à 12,74 mm du bord avant (EdgePinOffset 9,90 mm + 2,84 mm)
    c.poser(r('J', 1), cx - 5.54, AVANT - 12.74, 0)
    # barrière : broches 1-8 (côté logique) vers l'arrière, 9-16 (côté bus) vers l'avant
    c.poser(r('U', 2), cx - 8.0, BARRIERE, 270)     # ISO1042
    c.poser(r('U', 3), cx + 8.0, BARRIERE, 270)     # UCC12050
    c.poser(r('U', 1), cx - 3.0, BARRIERE - 15.0, 90)   # MCP2518FD
    c.poser(r('SW', 1), cx + SW_DX[c.nom], SW_Y, 0)     # terminaison
    c.poser(r('D', 3), cx - 1.2, 97.6, 270)             # NUP2105L, au plus près du DB9


def placer_mere(c):
    # connecteur carte à carte, sous la carte (embase femelle), aligné sur la barrette de la fille
    c.poser_dessous('J1301', broches_b2b())
    # USB-B à l'arrière : face d'entrée au bord (y = 0)
    c.poser('J1201', 34.75, 15.06, 90)
    c.poser('U1201', 36.0, 19.6, c.orienter('U1201', 36.0, 19.6))
    # bornier d'alimentation à l'arrière droit
    c.poser('J1001', 139.0, 10.05, 180)
    c.poser('U1001', 126.0, 27.0, 180)      # TPS54360 : VIN à droite, SW en bas à gauche
    c.fps['U1001'].SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)   # vias thermiques pleins
    c.poser('D1003', 121.0, 37.5, 270)      # B560C, cathode vers SW
    c.poser('L1001', 110.0, 27.0, 180)
    c.poser('U1002', 116.0, 46.5, 0)        # LDO 3,3 V
    # liaison châssis - masse près de l'USB
    c.poser('R1010', 22.0, 5.0, 90)
    c.poser('C1014', 25.5, 5.0, 90)
    # microcontrôleur et PHY USB
    phy = (52.0, 20.0)
    extra = {}
    for n in ('ULPI_CLK', 'ULPI_STP', 'ULPI_DIR', 'ULPI_NXT', '~{ULPI_RST}') + tuple('ULPI_D%d' % i for i in range(8)):
        extra[n] = phy
    for b in range(1, 5):
        for s in ('SCK', 'MOSI'):
            extra['SPI%d_%s_M' % (b, s)] = c.centroide('SPI%d_%s' % (b, s), None, prefere=())
    c.poser('U1101', 82.0, 25.0, c.orienter('U1101', 82.0, 25.0, extra))
    c.poser('U1202', phy[0], phy[1], c.orienter('U1202', *phy))
    # SWD, UART de débogage et bouton reset : placés automatiquement près de leurs broches du MCU


def placer_fille(c):
    pads = broches_b2b()
    # barrette mâle sur le dessus, broche 1 en B2B_BROCHE1, rangée de 20 selon x
    c.poser('J1301', B2B_BROCHE1[0], B2B_BROCHE1[1], 90)
    got = {n: (x, y) for n, x, y in c.pads_places('J1301')}
    assert all(abs(got[n][0] - pads[n][0]) < 1e-6 and abs(got[n][1] - pads[n][1]) < 1e-6 for n in pads)
    c.poser('R1301', 10.5, 44.0, 90)
    c.poser('C1305', 13.5, 44.0, 90)


_B2B = {}


def broches_b2b():
    """Positions des broches de la barrette de la carte fille (référence de l'empilage)."""
    if not _B2B:
        fp = charger('Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical')
        g = Geo(fp)
        for n, x, y in g.pads_a(B2B_BROCHE1[0], B2B_BROCHE1[1], 90):
            _B2B[n] = (x, y)
    return _B2B


def priorite(c, ref):
    lettre = re.match(r'[A-Z]+', ref).group(0)
    val = c.comps[ref]['value']
    nets = {base(c.pin_net[(r, p)]) for (r, p) in c.pin_net if r == ref}
    sh, i, j, port = c.info[ref]
    decouplage = lettre == 'C' and nets & MASSES and len(nets) == 2 and any(est_alim(n) for n in nets - MASSES)
    if lettre in ('U', 'Y', 'FB'):
        rang = 0
    elif decouplage and val.startswith(('100nF', '10nF')):
        rang = 1
    elif decouplage:
        rang = 2
    else:
        rang = 3
    return (rang, sh.key != 'port_can', j, port or 0)


def construire(nom, sheets):
    c = Carte(nom, sheets)
    ports = sorted({p for (_, _, _, p) in c.info.values() if p})
    # trous de fixation
    trous = sorted(r for r in c.comps if r.startswith('H'))
    assert len(trous) == len(TROUS[nom]), (trous, TROUS[nom])
    for ref, (x, y) in zip(trous, TROUS[nom]):
        c.poser(ref, x, y, 0)
    for k in ports:
        placer_port(c, k)
    # fenêtres de la carte mère au-dessus des interrupteurs de terminaison de la fille
    fenetres = []
    if nom == 'can8-mere':
        for k in ports:
            x = COLONNE[k] + SW_DX['can8-fille']
            fenetres.append((x - 6.5, SW_Y - 3.0, x + 6.5, SW_Y + 3.0))
        c.obstacles += [('fenêtre', (x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5)) for x0, y0, x1, y1 in fenetres]
        placer_mere(c)
    else:
        placer_fille(c)
    # passifs et petits circuits
    restants = [r for r in c.comps if r not in c.place]
    restants.sort(key=lambda r: priorite(c, r))
    for ref in restants:
        c.placer_auto(ref)
    dessiner(c, ports, fenetres)
    return c


def dessiner(c, ports, fenetres):
    b = c.board
    x0, y0, x1, y1 = c.contour
    rect_arrondi(b, pcbnew.Edge_Cuts, x0, y0, x1, y1, 2.0)
    for f in fenetres:
        rect_arrondi(b, pcbnew.Edge_Cuts, *f, 1.0)
    # barrière d'isolement et séparation des ports côté bus
    zone_interdite(b, 'Barrière isolement', BANDE_X[0], BARRIERE - DEMI_BARRIERE, BANDE_X[1],
                   BARRIERE + DEMI_BARRIERE)
    for k in ports[:-1]:
        xm = COLONNE[k] + 18.0
        zone_interdite(b, 'Séparation ports %d-%d' % (k, k + 1), xm - DEMI_ECART_PORTS,
                       BARRIERE + DEMI_BARRIERE, xm + DEMI_ECART_PORTS, 99.5)
    # plans internes : In1 = masses, In2 = 3,3 V / VISO
    gnd = c.netinfo['GND']
    p3 = c.netinfo['+3V3']
    logique = [(6.5, y0 + 0.5), (149.5, y0 + 0.5), (149.5, BARRIERE - DEMI_BARRIERE),
               (6.5, BARRIERE - DEMI_BARRIERE)]
    plan(b, gnd, pcbnew.In1_Cu, logique, 'GND')
    plan(b, p3, pcbnew.In2_Cu, logique, '+3V3')
    for k in ports:
        cx = COLONNE[k]
        xa, xb = cx - 18 + DEMI_ECART_PORTS, cx + 18 - DEMI_ECART_PORTS
        xa, xb = max(xa, BANDE_X[0] + 0.5), min(xb, BANDE_X[1] - 0.5)
        ya = BARRIERE + DEMI_BARRIERE
        # en T : le plan s'arrête à 1,5 mm des pattes de fixation du DB9 (châssis)
        forme = [(xa, ya), (xb, ya), (xb, 99.5), (cx + 9.0, 99.5), (cx + 9.0, y1 - 0.5),
                 (cx - 9.0, y1 - 0.5), (cx - 9.0, 99.5), (xa, 99.5)]
        plan(b, c.netinfo['/Port CAN %d/GND_ISO' % k], pcbnew.In1_Cu, forme, 'GND_ISO port %d' % k)
        plan(b, c.netinfo['/Port CAN %d/VISO' % k], pcbnew.In2_Cu, forme, 'VISO port %d' % k)
        texte(b, pcbnew.F_SilkS, 'CAN %d' % k, cx, BARRIERE, 1.2, 90)
    # repères de la barrière (couche de documentation)
    for y in (BARRIERE - DEMI_BARRIERE, BARRIERE + DEMI_BARRIERE):
        segment(b, pcbnew.Dwgs_User, (BANDE_X[0], y), (BANDE_X[1], y), 0.15)
    texte(b, pcbnew.Dwgs_User, 'Barrière d\'isolement : bande de %g mm sans cuivre sous les ISO1042 et UCC12050'
          % (2 * DEMI_BARRIERE), LARGEUR / 2, y0 - 3, 1.5)
    titre = {'can8-mere': 'Usb2Can-8-Ports - carte mère', 'can8-fille': 'Usb2Can-8-Ports - carte fille'}[c.nom]
    tb = b.GetTitleBlock()
    tb.SetTitle(titre.replace('Usb2Can-8-Ports - c', 'C') + ' : placement des composants (non routé)')
    tb.SetRevision(gen.REV)
    tb.SetDate(gen.DATE)
    tb.SetCompany('Usb2Can-8-Ports')
    tb.SetComment(0, 'Généré par hardware/outils/placer.py')
    tb.SetComment(1, '4 couches : F.Cu signaux, In1.Cu masses, In2.Cu 3,3 V / VISO, B.Cu signaux')
    texte(b, pcbnew.F_SilkS, '%s %s' % (titre, gen.REV), 78.0 if c.nom == 'can8-fille' else 60.0,
          y0 + 2.5 if c.nom == 'can8-mere' else FOND_LOGIQUE - 1.2, 1.0)


# ------------------------------------------------------------------ contrôles
def controler(c):
    erreurs = []
    refs = sorted(c.place)
    manquants = sorted(set(c.comps) - set(c.place))
    if manquants:
        erreurs.append('non placés : %s' % manquants)
    for i, a in enumerate(refs):
        ra = c.rects[a]
        dehors = not contenu(ra, c.contour)
        connecteur_bord = a in ('J1001', 'J1201') or re.match(r'J[1-8]01$', a)
        if dehors and not connecteur_bord:
            erreurs.append('%s hors de la carte %s' % (a, tuple(round(v, 2) for v in ra)))
        for b_ in refs[i + 1:]:
            if chevauche(ra, c.rects[b_]):
                erreurs.append('courtyards %s et %s se chevauchent' % (a, b_))
        for nom, r in c.obstacles:
            if chevauche(ra, r):
                erreurs.append('%s empiète sur %s' % (a, nom))
    # pastilles dans les bandes sans cuivre
    bandes = [('barrière', (BANDE_X[0], BARRIERE - DEMI_BARRIERE, BANDE_X[1], BARRIERE + DEMI_BARRIERE))]
    for p in range(1, 4):
        xm = 42.0 + 36.0 * (p - 1)
        bandes.append(('séparation ports', (xm - DEMI_ECART_PORTS, BARRIERE + DEMI_BARRIERE,
                                            xm + DEMI_ECART_PORTS, 99.5)))
    for ref, fp in c.fps.items():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            r = (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                 pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)
            for nom, band in bandes:
                if chevauche(r, band):
                    erreurs.append('pastille %s-%s dans la bande %s' % (ref, pad.GetNumber(), nom))
    # cohérence du calcul de rotation avec KiCad
    for ref, (x, y, th, face) in c.place.items():
        if face != 'dessus':
            continue
        att = sorted(c.geo[ref].pads_a(x, y, th))
        reel = sorted((p.GetNumber(), pcbnew.ToMM(p.GetPosition().x) - OX, pcbnew.ToMM(p.GetPosition().y) - OY)
                      for p in c.fps[ref].Pads())
        if len(att) != len(reel) or any(a[0] != b_[0] or abs(a[1] - b_[1]) > 0.002 or abs(a[2] - b_[2]) > 0.002
                                        for a, b_ in zip(att, reel)):
            erreurs.append('%s : positions de pastilles incohérentes' % ref)
    return erreurs


def controler_empilage(mere, fille):
    erreurs = []

    def pads(c, ref):
        return {(round(x, 2), round(y, 2)): (n, c.pin_net.get((ref, n))) for n, x, y in c.pads_places(ref)}

    pm, pf = pads(mere, 'J1301'), pads(fille, 'J1301')
    if set(pm) != set(pf):
        erreurs.append('connecteur carte à carte : broches non superposées')
    for pos in sorted(set(pm) & set(pf)):
        (nm, netm), (nf, netf) = pm[pos], pf[pos]
        bm, bf = base(netm or ''), base(netf or '')
        if nm != nf:
            erreurs.append('carte à carte : broche %s de la mère face à la broche %s de la fille' % (nm, nf))
        if bm != bf and not (bm == '~{FILLE_PRESENTE}' and bf == 'GND'):
            erreurs.append('carte à carte, broche %s : %s (mère) face à %s (fille)' % (nm, bm, bf))
    for km, kf in zip((1, 2, 3, 4), (5, 6, 7, 8)):
        a, b = mere.place[ref_port('J', km, 1)], fille.place[ref_port('J', kf, 1)]
        if a[:3] != b[:3]:
            erreurs.append('DB9 des ports %d et %d non superposés' % (km, kf))
    tm = {mere.place[r][:2] for r in mere.comps if r.startswith('H')}
    tf = {fille.place[r][:2] for r in fille.comps if r.startswith('H')}
    if not tf <= tm:
        erreurs.append('trous de la fille sans trou en face sur la mère : %s' % sorted(tf - tm))
    return erreurs


def drc(c):
    """DRC de KiCad sur la carte relue depuis le disque (avec les règles du .kicad_pro).
    Renvoie le nombre de violations par type."""
    board = pcbnew.LoadBoard(c.path)
    with tempfile.TemporaryDirectory() as d:
        rapport = os.path.join(d, 'drc.txt')
        pcbnew.WriteDRCReport(board, rapport, pcbnew.EDA_UNITS_MILLIMETRES, True)
        txt = open(rapport).read()
    return collections.Counter(re.findall(r'^\[(\w+)\]', txt, re.M))


# ------------------------------------------------------------------ projet KiCad
REGLES = {   # classe 2/3 IPC, capacités standard d'un fabricant 4 couches
    'min_clearance': 0.15, 'min_track_width': 0.15, 'min_via_diameter': 0.45,
    'min_through_hole_diameter': 0.2, 'min_via_annular_width': 0.125, 'min_copper_edge_clearance': 0.5,
    'min_hole_clearance': 0.25, 'min_hole_to_hole': 0.25, 'min_silk_clearance': 0.0,
}
CLASSES = [
    # nom, largeur piste, isolement, via, perçage, motifs de nets
    ('Default', 0.2, 0.15, 0.6, 0.3, []),
    ('Puissance', 1.0, 0.3, 0.8, 0.4, ['/Alimentation*/VIN_BRUT', '/Alimentation*/VIN_FUS', '+VIN',
                                        '/Alimentation*/SW']),
    ('Alim', 0.5, 0.2, 0.6, 0.3, ['+5V', '+3V3', '*+3V3A', '*/+1V8_PHY', '/Port CAN */VISO']),
    ('CAN', 0.3, 0.2, 0.6, 0.3, ['/Port CAN */CANH', '/Port CAN */CANL', '/Port CAN */TERM']),
    ('USB', 0.2, 0.15, 0.6, 0.3, ['/USB*/USB_DP', '/USB*/USB_DM']),
]


def projet(c):
    """Règles de conception et classes de nets dans le .kicad_pro (KiCad 7)."""
    path = os.path.join(c.dir, c.nom + '.kicad_pro')
    d = json.load(open(path))
    rules = d.setdefault('board', {}).setdefault('design_settings', {}).setdefault('rules', {})
    rules.update(REGLES)
    ns = d.setdefault('net_settings', {})
    modele = (ns.get('classes') or [{}])[0]
    classes, motifs = [], []
    for nom, w, cl, via, drill, pats in CLASSES:
        k = dict(modele)
        k.update({'name': nom, 'track_width': w, 'clearance': cl, 'via_diameter': via, 'via_drill': drill})
        if nom == 'USB':
            k.update({'diff_pair_width': 0.2, 'diff_pair_gap': 0.15})
        classes.append(k)
        motifs += [{'netclass': nom, 'pattern': p} for p in pats]
    ns['classes'] = classes
    ns['netclass_patterns'] = motifs
    with open(path, 'w') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write('\n')


# ------------------------------------------------------------------ rendus
def rendus(c):
    """Vue de placement en PDF dans hardware/<carte>/, images PNG dans docs/placement/ (si pdftoppm)."""
    pdf = os.path.join(c.dir, c.nom + '-placement.pdf')
    subprocess.run(['kicad-cli', 'pcb', 'export', 'pdf', '-o', pdf, '--layers',
                    'Edge.Cuts,F.Fab,F.Courtyard,B.Courtyard,Dwgs.User,F.Silkscreen',
                    '--include-border-title', c.path], check=True, capture_output=True)
    if not shutil.which('pdftoppm'):
        return
    images = os.path.join(gen.HW, '..', 'docs', 'placement')
    os.makedirs(images, exist_ok=True)
    dpi = 150
    px = lambda v: str(int(round(v / 25.4 * dpi)))  # noqa: E731
    y_haut = OY + c.y0 - 7
    cadre = ['-x', px(OX - 5), '-y', px(y_haut), '-W', px(LARGEUR + 10), '-H', px(OY + AVANT + 8 - y_haut)]
    nom = c.nom.replace('can8-', '')
    subprocess.run(['pdftoppm', '-png', '-r', str(dpi), '-singlefile'] + cadre +
                   [pdf, os.path.join(images, nom)], check=True)
    with tempfile.TemporaryDirectory() as d:
        plans = os.path.join(d, 'plans.pdf')
        subprocess.run(['kicad-cli', 'pcb', 'export', 'pdf', '-o', plans, '--layers',
                        'Edge.Cuts,In1.Cu,F.Courtyard,Dwgs.User', c.path], check=True, capture_output=True)
        subprocess.run(['pdftoppm', '-png', '-r', str(dpi), '-singlefile'] + cadre +
                       [plans, os.path.join(images, nom + '-plans')], check=True)


def main():
    mere_sheets, fille_sheets = gen.main()
    cartes = {}
    ok = True
    for nom, sheets in (('can8-fille', fille_sheets), ('can8-mere', mere_sheets)):
        c = construire(nom, sheets)
        c.board.BuildConnectivity()
        filler = pcbnew.ZONE_FILLER(c.board)
        filler.Fill(c.board.Zones())
        pcbnew.SaveBoard(c.path, c.board)
        projet(c)
        erreurs = controler(c)
        types = drc(c)
        # attendus à ce stade : liaisons non routées, sérigraphie à ranger, plans pas encore reliés
        # par des vias, bibliothèques d'empreintes non déclarées dans cet environnement
        attendus = ('unconnected_items', 'silk_overlap', 'silk_over_copper', 'silk_edge_clearance',
                    'isolated_copper', 'lib_footprint_issues', 'lib_footprint_mismatch')
        graves = {k: v for k, v in types.items() if k not in attendus}
        ok &= not graves
        print('%s : %d composants placés, %d erreur(s) de placement, DRC : %s (attendus : %s)'
              % (nom, len(c.place), len(erreurs), dict(graves) or '0 erreur',
                 ', '.join('%s %d' % (k, types[k]) for k in attendus if types.get(k))))
        for e in erreurs[:40]:
            print('  ERREUR', e)
        ok &= not erreurs
        cartes[nom] = c
        rendus(c)
    e = controler_empilage(cartes['can8-mere'], cartes['can8-fille'])
    print('empilage : %d écart(s)' % len(e))
    for x in e:
        print('  ERREUR', x)
    ok &= not e
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
