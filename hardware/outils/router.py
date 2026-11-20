#!/usr/bin/env python3
"""Routage des cartes mère et fille (API pcbnew de KiCad 9, Freerouting 2.5, grille.py).

    python3 hardware/outils/router.py preparer  can8-mere   # retouches, pré-routage, éventail, DSN
    freerouting -de routage/can8-mere.dsn -do routage/can8-mere.ses -mp 10
    python3 hardware/outils/router.py importer  can8-mere   # import de la session Freerouting
    python3 hardware/outils/router.py completer can8-mere   # liaisons restantes (routeur sur grille)
    python3 hardware/outils/router.py finir     can8-mere   # plans externes, couture, sérigraphie
    python3 hardware/outils/router.py rapport   can8-mere   # longueurs ULPI / USB, statistiques

À lancer sur une carte placée et non routée (sortie de placer.py passée par
maj_empreintes_k9.py). Une fois la carte retouchée à la main dans KiCad, ne plus relancer.

« preparer » :
  - In1 (GND / GND_ISO) et In2 (+3V3 / VISO) déclarées couches de plans : aucun signal ;
  - quelques retouches de placement (étage à découpage resserré, USBLC6 dans l'axe de la paire USB) ;
  - pré-routage à la main, pistes verrouillées : paire USB D+/D- (0,2 mm, écart 0,25 mm,
    ≈ 90 ohms différentiels avec l'empilage ci-dessous, à confirmer par le fabricant),
    étage TPS54360 (boucle d'entrée et nœud SW courts et larges), entrée 9-36 V, sortie 5 V ;
  - zones interdites PROVISOIRES sur F.Cu autour du nœud SW et de la boucle d'entrée,
    pour que le routeur automatique n'y fasse passer aucun autre signal ;
  - éventail : une via vers son plan pour chaque pastille CMS de GND, +3V3, GND_ISO, VISO ;
  - export Specctra DSN.

« importer » : import de la session Freerouting, retrait des zones interdites provisoires.

« completer » : rétreints de Freerouting élargis à 0,15 mm, pistes en défaut retirées, puis
  les liaisons encore signalées par le DRC sont tirées par grille.py (A* sur F.Cu/B.Cu) ;
  DRC relancé à chaque tour.

« finir » : plans GND / GND_ISO sur F.Cu et B.Cu, vias de couture, repères de sérigraphie
  rangés (ou masqués s'il n'y a pas de place), empilage 4 couches écrit dans la carte.
"""
import math
import os
import sys

import pcbnew

HW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OX, OY = 50.0, 40.0          # origine de la carte sur la feuille (comme placer.py)
PROVISOIRE = 'PROVISOIRE routage'


def MM(v):
    return pcbnew.FromMM(v)


def V(x, y):
    return pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))


def XY(v):
    return pcbnew.ToMM(v.x) - OX, pcbnew.ToMM(v.y) - OY


def chemin_carte(nom):
    # ROUTAGE_CARTE : autre fichier à traiter (essais sur une copie)
    return os.environ.get('ROUTAGE_CARTE') or os.path.join(HW, nom, nom + '.kicad_pcb')


def dossier_routage(nom):
    d = os.environ.get('ROUTAGE_DOSSIER') or os.path.join(HW, nom, 'routage')
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------- outils
class Carte:
    def __init__(self, board):
        self.b = board
        self.fp = {f.GetReference(): f for f in board.GetFootprints()}

    def pad(self, ref, num):
        for p in self.fp[ref].Pads():
            if p.GetNumber() == str(num):
                return p
        raise KeyError('%s-%s' % (ref, num))

    def net(self, ref, num):
        return self.pad(ref, num).GetNet()

    def placer(self, ref, x, y, rot):
        f = self.fp[ref]
        f.SetOrientationDegrees(rot)
        f.SetPosition(V(x, y))

    def piste(self, net, pts, w, couche=pcbnew.F_Cu):
        faites = []
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(V(x1, y1))
            t.SetEnd(V(x2, y2))
            t.SetWidth(MM(w))
            t.SetLayer(couche)
            t.SetNet(net)
            t.SetLocked(True)
            self.b.Add(t)
            faites.append(t)
        return faites

    def via(self, net, x, y, d=0.6, trou=0.3, verrou=True):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(V(x, y))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(MM(d))
        v.SetDrill(MM(trou))
        v.SetNet(net)
        v.SetLocked(verrou)
        self.b.Add(v)
        return v

    def zone(self, net, couche, pts, prio=0, nom='', thermique=True, pont=0.5, isolement=None):
        z = pcbnew.ZONE(self.b)
        z.SetLayer(couche)
        if net is not None:
            z.SetNet(net)
        z.SetZoneName(nom)
        z.SetAssignedPriority(prio)
        z.SetMinThickness(MM(0.25))
        if isolement is not None:
            z.SetLocalClearance(MM(isolement))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermique else pcbnew.ZONE_CONNECTION_FULL)
        z.SetThermalReliefGap(MM(0.4))
        z.SetThermalReliefSpokeWidth(MM(pont))
        o = z.Outline()
        o.NewOutline()
        for x, y in pts:
            o.Append(MM(OX + x), MM(OY + y))
        self.b.Add(z)
        return z

    def interdit(self, pts, couches=(pcbnew.F_Cu,), nom=PROVISOIRE, vias=True):
        z = pcbnew.ZONE(self.b)
        z.SetIsRuleArea(True)
        ls = pcbnew.LSET()
        for c in couches:
            ls.AddLayer(c)
        z.SetLayerSet(ls)
        z.SetZoneName(nom)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(vias)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        o = z.Outline()
        o.NewOutline()
        for x, y in pts:
            o.Append(MM(OX + x), MM(OY + y))
        self.b.Add(z)
        return z


def remplir(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# ---------------------------------------------------------------------------- carte mère
def preparer_mere(c):
    # --- retouches de placement -------------------------------------------------
    # USBLC6 tourné à 0° : D+ (1 -> 6) sur la rangée du haut, D- (3 -> 4) sur celle du bas,
    # la paire traverse le composant sans se croiser entre le connecteur et le PHY.
    c.placer('U1201', 41.0, 19.0, 0)
    # TPS54360 : condensateur d'entrée contre VIN, diode de roue libre sous le circuit,
    # condensateur de bootstrap en travers de l'extrémité broches 1/8, réseau de
    # compensation éloigné du nœud SW.
    c.placer('C1004', 126.0, 30.9, 180)
    c.placer('D1003', 124.3, 35.2, 0)
    c.placer('C1002', 131.5, 29.4, -90)
    c.placer('C1003', 134.3, 29.4, -90)
    c.placer('C1001', 137.0, 36.6, -90)
    c.placer('R1006', 118.2, 24.2, 180)
    c.placer('C1005', 117.4, 21.85, 90)

    # --- paire USB ---------------------------------------------------------------
    dp, dm = c.net('U1202', 18), c.net('U1202', 19)
    w = 0.2
    c.piste(dp, [(37.25, 13.06), (38.6, 13.06), (38.6, 17.5), (39.15, 18.05), (39.86, 18.05)], w)
    c.piste(dp, [(39.86, 18.05), (42.14, 18.05)], w)
    c.piste(dp, [(42.14, 18.05), (48.35, 18.05), (49.05, 18.75), (49.56, 18.75)], w)
    c.piste(dm, [(37.25, 15.06), (37.25, 19.4), (37.8, 19.95), (39.86, 19.95)], w)
    c.piste(dm, [(39.86, 19.95), (42.14, 19.95)], w)
    c.piste(dm, [(42.14, 19.95), (44.2, 19.95), (45.65, 18.5), (48.3, 18.5), (49.05, 19.25),
                 (49.56, 19.25)], w)
    gnd = c.net('U1201', 2)
    c.piste(gnd, [(39.86, 19.0), (38.5, 19.0)], 0.3)
    c.via(gnd, 38.5, 19.0)
    vbus = c.net('U1201', 5)
    c.piste(vbus, [(42.14, 19.0), (43.3, 19.0)], 0.3)
    c.via(vbus, 43.3, 19.0)
    # pastille thermique du PHY
    for dx in (-0.6, 0.6):
        for dy in (-0.6, 0.6):
            c.via(gnd, 52.0 + dx, 20.0 + dy)

    # --- étage à découpage TPS54360 ------------------------------------------------
    sw, boot, vin = c.net('U1001', 8), c.net('U1001', 1), c.net('U1001', 2)
    c.piste(sw, [(123.3, 28.91), (123.3, 30.0)], 0.6)
    c.piste(sw, [(123.3, 30.0), (124.2, 30.9), (125.22, 30.9)], 0.5)
    c.piste(sw, [(123.3, 30.0), (121.9, 31.4), (121.9, 34.2)], 1.5)
    c.piste(sw, [(121.9, 31.4), (117.3, 31.4), (115.2, 29.3), (115.2, 27.8)], 1.5)
    c.piste(boot, [(128.7, 28.91), (128.7, 30.9), (126.78, 30.9)], 0.5)
    c.piste(vin, [(128.7, 27.64), (131.5, 27.64)], 0.6)
    c.piste(vin, [(131.5, 27.93), (134.3, 27.93), (137.0, 27.93), (137.0, 33.35)], 1.0)
    c.piste(vin, [(147.0, 24.0), (147.0, 31.2), (137.0, 31.2)], 1.0)
    fus = c.net('F1001', 2)
    c.piste(fus, [(139.0, 20.89), (139.0, 24.0), (143.0, 24.0)], 1.5)
    brut = c.net('F1001', 1)
    c.piste(brut, [(139.0, 10.05), (139.0, 14.11)], 1.5)
    c.piste(gnd, [(131.5, 30.87), (131.5, 32.4), (128.7, 35.2), (127.7, 35.2)], 1.5)
    c.piste(gnd, [(134.3, 30.35), (131.5, 30.35)], 1.0)
    c.piste(gnd, [(123.3, 27.64), (124.6, 27.64)], 0.5)
    for x, y in [(126.9, 37.1), (128.3, 37.1), (132.7, 32.0), (134.3, 31.8), (135.6, 42.0),
                 (137.0, 42.0), (138.4, 42.0), (140.6, 28.15)]:
        c.via(gnd, x, y)
    # sortie 5 V
    p5 = c.net('L1001', 2)
    c.piste(p5, [(105.53, 27.0), (100.72, 27.0)], 1.5)
    c.piste(p5, [(102.47, 27.0), (102.47, 29.5)], 1.0)
    for x, y in [(97.78, 27.9), (98.3, 30.4)]:
        c.via(gnd, x, y)

    # --- zones interdites provisoires (F.Cu, pistes et vias) ------------------------
    c.interdit(rect(112.8, 29.8, 123.0, 37.4))     # nœud SW et cathode de la diode
    c.interdit(rect(129.6, 26.9, 136.0, 33.0))     # boucle d'entrée


def eventail(c, isolement=0.25, largeur=0.3):
    """Via vers son plan pour chaque pastille CMS d'un net de plan (GND, +3V3, GND_ISO, VISO).

    La via est posée au plus près, d'abord dans l'axe de la pastille vers l'extérieur du
    composant, puis en tournant autour, sans toucher le cuivre d'un autre net, hors des zones
    interdites, à l'intérieur du plan de son net. Les pistes et vias sont verrouillées : le
    routeur automatique n'a plus qu'à router les signaux sur F.Cu et B.Cu.
    Renvoie (vias posées, pastilles sans place)."""
    b = c.b
    plans = {}
    for z in b.Zones():
        if not z.GetIsRuleArea() and z.GetLayer() in (pcbnew.In1_Cu, pcbnew.In2_Cu):
            plans.setdefault(z.GetNetCode(), []).append(z)
    obst = Obstacles(b)
    interdits = [z for z in b.Zones() if z.GetIsRuleArea()]
    poly, dist_bord = distance_bords(b)

    def dans_plan(net, x, y, marge):
        return any(all(z.Outline().Contains(V(x + dx, y + dy))
                       for dx, dy in ((-marge, 0), (marge, 0), (0, -marge), (0, marge)))
                   for z in plans[net])

    def libre(net, x, y, seg, pad=None):
        if dist_bord(x, y) < 1.0 or not poly.Contains(V(x, y)):
            return False
        if any(k.Outline().Collide(V(x, y), MM(0.35)) for k in interdits):
            return False
        if not dans_plan(net, x, y, 0.6):
            return False
        return obst.libre(x, y, 0.3, isolement, net, seg, pad)

    poses, rates = 0, []
    for fp in b.GetFootprints():
        if fp.IsFlipped():
            continue
        cx, cy = XY(fp.GetPosition())
        for p in fp.Pads():
            net = p.GetNetCode()
            if net not in plans or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not p.IsOnLayer(pcbnew.F_Cu):
                continue
            forme = p.GetEffectiveShape(pcbnew.F_Cu)
            # déjà relié : via (ou trou métallisé du même net) dans la pastille, ou piste qui y arrive
            deja = any(t.GetNetCode() == net and forme.Collide(t.GetEffectiveShape(pcbnew.F_Cu), 0)
                       for t in obst.autour(*XY(p.GetPosition())) if t is not p and
                       (t.GetClass() in ('PCB_VIA', 'PCB_TRACK') or (t.GetClass() == 'PAD' and t.HasHole())))
            if deja:
                continue
            px, py = XY(p.GetPosition())
            sx, sy = pcbnew.ToMM(p.GetSize(pcbnew.F_Cu).x), pcbnew.ToMM(p.GetSize(pcbnew.F_Cu).y)
            ang = p.GetOrientation().AsDegrees() + (0 if sx >= sy else 90)
            ux, uy = math.cos(math.radians(ang)), -math.sin(math.radians(ang))
            demi = max(sx, sy) / 2
            if (px - cx) * ux + (py - cy) * uy < 0:
                ux, uy = -ux, -uy
            if abs((px - cx) * ux + (py - cy) * uy) < 0.3 and min(sx, sy) > 2.0:
                # pastille thermique centrale : via dans la pastille
                if libre(net, px, py, None, p):
                    obst.ajouter(c.via(p.GetNet(), px, py))
                    poses += 1
                continue
            fait = False
            for extra in (0.0, 0.25, 0.5, 0.9, 1.4):
                for da in (0, 30, -30, 60, -60, 90, -90, 135, -135, 180):
                    a = math.radians(da)
                    vx = ux * math.cos(a) - uy * math.sin(a)
                    vy = ux * math.sin(a) + uy * math.cos(a)
                    # distance du centre de la pastille au bord, dans cette direction
                    d = (abs(vx * ux + vy * uy) * demi + abs(-vx * uy + vy * ux) * min(sx, sy) / 2)
                    d = min(d, math.hypot(demi, min(sx, sy) / 2)) + isolement + 0.3 + extra
                    x, y = px + vx * d, py + vy * d
                    w = min(largeur, min(sx, sy))
                    seg = pcbnew.SHAPE_SEGMENT(V(px, py), V(x, y), MM(w))
                    if libre(net, x, y, seg, p):
                        for t in c.piste(p.GetNet(), [(px, py), (x, y)], w):
                            obst.ajouter(t)
                        v = c.via(p.GetNet(), x, y)
                        obst.ajouter(v)
                        poses += 1
                        fait = True
                        break
                if fait:
                    break
            if not fait:
                # repli : piste droite vers une via du même net à moins de 3 mm (via d'un condensateur
                # de découplage voisin le plus souvent)
                w = min(0.25, min(sx, sy))
                vias = sorted({id(t): t for t in obst.proches(px, py, 3.0)
                               if t.GetClass() == 'PCB_VIA' and t.GetNetCode() == net}.values(),
                              key=lambda t: math.hypot(XY(t.GetPosition())[0] - px, XY(t.GetPosition())[1] - py))
                for t in vias:
                    x, y = XY(t.GetPosition())
                    seg = pcbnew.SHAPE_SEGMENT(V(px, py), V(x, y), MM(w))
                    if obst.libre_piste(seg, net, isolement, p):
                        for tr in c.piste(p.GetNet(), [(px, py), (x, y)], w):
                            obst.ajouter(tr)
                        fait = True
                        poses += 1
                        break
            if not fait:
                rates.append('%s-%s' % (fp.GetReference(), p.GetNumber()))
    return poses, rates


ULPI = ['ULPI_CLK', 'ULPI_DIR', 'ULPI_NXT', 'ULPI_STP'] + ['ULPI_D%d' % i for i in range(8)]


def ulpi(board):
    """Pré-routage des 12 liaisons ULPI (USB3320 U1202 -> STM32 U1101), avant le routage
    automatique : routeur sur grille, F.Cu de préférence (au-dessus du plan de masse ; B.Cu
    coûte 3 fois plus, une via autant que 2 mm de piste), l'horloge d'abord. Pistes verrouillées."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from grille import Grille
    g = Grille(board)
    rates = []
    # amorces : la sortie de chaque broche ULPI est réservée avant de router
    bouts = {}
    for nom in ULPI:
        pads = {p.GetParentFootprint().GetReference(): p
                for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == nom}
        bouts[nom] = []
        for ref in ('U1202', 'U1101'):
            t = g.bout(pads[ref])
            if t is not None:
                t.SetLocked(True)
            bouts[nom].append(t or pads[ref])
    for nom in ULPI:
        a, b = bouts[nom]
        res = (g.relier(a, b, [0.2], 0.15, cout=(1.0, 3.0), marges=(6.0, 15.0)) or
               g.relier(a, b, [0.2], 0.15, cout=(1.0, 1.5), marges=(30.0,)))
        if res:
            for t in res:
                t.SetLocked(True)
        else:
            rates.append(nom)
    print('ULPI : %d liaisons pré-routées, sans chemin : %s' % (len(ULPI) - len(rates), ' '.join(rates) or 'aucune'))


def preparer(nom):
    board = pcbnew.LoadBoard(chemin_carte(nom))
    c = Carte(board)
    # In1 : plan de masse plein (référence des pistes de F.Cu : USB, ULPI, SPI).
    # In2 : plan +3V3 (logique) et VISO (bus). Les deux restent des plans pleins : quand
    # Freerouting peut tirer des pistes sur In2, il découpe le plan +3V3 et utilise moins B.Cu
    # (essai sur la carte fille : 44 liaisons non routées au lieu de 19).
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    if nom == 'can8-mere':
        preparer_mere(c)
        remplir(board)
        ulpi(board)
    remplir(board)
    n, rates = eventail(c)
    print('%s : %d vias vers les plans, pastilles sans place : %s' % (nom, n, ' '.join(rates) or 'aucune'))
    remplir(board)
    pcbnew.SaveBoard(chemin_carte(nom), board)
    dsn = os.path.join(dossier_routage(nom), nom + '.dsn')
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit('export DSN impossible')
    print('%s : préparée, DSN exporté dans %s' % (nom, dsn))


# ---------------------------------------------------------------------------- import
def importer(nom):
    board = pcbnew.LoadBoard(chemin_carte(nom))
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    ses = os.path.join(dossier_routage(nom), nom + '.ses')
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit('import SES impossible')
    for z in list(board.Zones()):
        if z.GetIsRuleArea() and z.GetZoneName() == PROVISOIRE:
            board.Remove(z)
    # ULPI : verrouillé seulement pour que Freerouting n'y touche pas
    for t in board.GetTracks():
        if t.GetNetname() in ULPI:
            t.SetLocked(False)
    remplir(board)
    pcbnew.SaveBoard(chemin_carte(nom), board)
    print('%s : session importée' % nom)


# ---------------------------------------------------------------------------- liaisons restantes
def drc(chemin, sortie):
    """DRC de kicad-cli (erreurs seulement), rapport JSON."""
    import json
    import subprocess
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-error', '-o', sortie, chemin],
                   check=True, stdout=subprocess.DEVNULL)
    return json.load(open(sortie, encoding='utf-8'))


def elaguer(board, retirer):
    """Retire, jusqu'à stabilité, les pistes non verrouillées dont une extrémité n'est reliée à
    rien et les vias non verrouillées reliées sur moins de deux couches : restes de liaisons
    dont une partie a été supprimée au DRC. Ils gênent le routage et faussent les liaisons
    manquantes (le DRC propose de partir du bout de piste au lieu de la pastille)."""
    cuivre = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    n = 0
    while True:
        board.BuildConnectivity()
        c = board.GetConnectivity()
        morts = []
        for t in board.GetTracks():
            if t.IsLocked():
                continue
            if t.GetClass() == 'PCB_TRACK':
                if c.TestTrackEndpointDangling(t, True):
                    morts.append(t)
            elif t.GetClass() == 'PCB_VIA':
                if sum(1 for L in cuivre if c.IsConnectedOnLayer(t, L)) < 2:
                    morts.append(t)
        if not morts:
            return n
        for t in morts:
            retirer(t)
        n += len(morts)


def degrouper(board, retirer, plans, rayon=1.2, seuil=4):
    """Retire les grappes de vias non verrouillées d'un net de plan (au moins seuil vias du même
    net à moins de rayon mm les unes des autres, chaînées par des pistes au fil des tours) et
    les pistes non verrouillées de ce net qui y aboutissent. Les pastilles concernées sont
    ensuite reliées au plan par une seule via chacune ; la place libérée sert aux autres nets."""
    vias = [t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA' and not t.IsLocked()
            and t.GetNetCode() in plans]
    pos = [(t, t.GetPosition()) for t in vias]
    grappe = [t for t, p in pos
              if sum(1 for u, q in pos if u.GetNetCode() == t.GetNetCode() and (q - p).EuclideanNorm() < MM(rayon)) >= seuil]
    if not grappe:
        return 0
    points = {(t.GetNetCode(), p.x, p.y) for t, p in pos if t in grappe}
    n = 0
    for t in list(board.GetTracks()):
        if t.GetClass() == 'PCB_TRACK' and not t.IsLocked() and t.GetNetCode() in plans and \
                ((t.GetNetCode(), t.GetStart().x, t.GetStart().y) in points or
                 (t.GetNetCode(), t.GetEnd().x, t.GetEnd().y) in points):
            retirer(t)
            n += 1
    for t in grappe:
        retirer(t)
    return n + len(grappe)


def completer(nom, tours=14, negocie=False, in2=False):
    """Termine le routage après Freerouting, avec le routeur sur grille (grille.py) :
    élargit à 0,15 mm les rétreints de Freerouting (0,1 mm près des pastilles), supprime les
    pistes non verrouillées en défaut au DRC, puis tire les liaisons que le DRC signale encore
    (vers le plan du net pour GND, +3V3, GND_ISO, VISO ; d'élément à élément pour les autres)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from grille import Grille
    import numpy as np
    chemin = chemin_carte(nom)
    rapport = os.path.join(dossier_routage(nom), 'drc-completer.json')
    board = pcbnew.LoadBoard(chemin)
    plans = {z.GetNetCode() for z in board.Zones()
             if not z.GetIsRuleArea() and z.GetLayer() in (pcbnew.In1_Cu, pcbnew.In2_Cu)}
    fines = [t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK' and t.GetWidth() < MM(0.15)]
    for t in fines:
        t.SetWidth(MM(0.15))
    print('%s : %d rétreints élargis à 0,15 mm' % (nom, len(fines)))

    import json
    classes = {c['name']: c for c in json.load(open(os.path.splitext(chemin)[0] + '.kicad_pro'))
               ['net_settings']['classes']}

    def largeurs(item):
        nc = classes.get(item.GetNetClassName().split(',')[0], classes['Default'])
        w = nc['track_width']
        return sorted({x for x in (w, 0.3, 0.25, 0.2) if x <= w}, reverse=True), nc['clearance']

    def index():
        d = {}
        for fp in board.GetFootprints():
            for p in fp.Pads():
                d[p.m_Uuid.AsString()] = p
        for t in board.GetTracks():
            d[t.m_Uuid.AsString()] = t
        for z in board.Zones():
            d[z.m_Uuid.AsString()] = z
        return d

    def retirer(it):
        board.Remove(it)
        corbeille.append(it)

    def arracher(it, rayon=0.3, maxi=6):
        """Retire les pistes et vias non verrouillées d'autres nets à moins de rayon mm du cuivre
        de it (sortie de broche bouchée) : elles seront re-routées au tour suivant."""
        gene = []
        for t in list(board.GetTracks()):
            if t.IsLocked() or t.GetNetCode() == it.GetNetCode():
                continue
            if any(t.IsOnLayer(L) and it.IsOnLayer(L) and
                   t.GetEffectiveShape(L).Collide(it.GetEffectiveShape(L), MM(rayon))
                   for L in (pcbnew.F_Cu, pcbnew.B_Cu)):
                gene.append(t)
        if len(gene) > maxi:
            return 0
        for t in gene:
            retirer(t)
        return len(gene)

    def degager_sortie(p, longueur=1.6):
        """Pastille d'un boîtier à pas fin (QFN, LQFP) enfermée : retire les pistes et vias non
        verrouillées d'autres nets dans le couloir de sortie de la broche (vers l'extérieur du
        boîtier, sur la largeur de la pastille + 0,15 mm de chaque côté)."""
        if p is None or p.GetClass() != 'PAD':
            return 0
        fp = p.GetParentFootprint()
        if fp is None or len(fp.Pads()) < 8:
            return 0
        c, q = fp.GetPosition(), p.GetPosition()
        dx, dy = pcbnew.ToMM(q.x - c.x), pcbnew.ToMM(q.y - c.y)
        if math.hypot(dx, dy) < 1.0:
            return 0
        ux, uy = ((1 if dx > 0 else -1), 0) if abs(dx) >= abs(dy) else (0, (1 if dy > 0 else -1))
        taille = p.GetSize(pcbnew.F_Cu) if hasattr(p, 'GetSize') else p.GetSize()
        larg = pcbnew.ToMM(min(taille.x, taille.y)) + 0.3
        fin = pcbnew.VECTOR2I(q.x + MM(longueur * ux), q.y + MM(longueur * uy))
        couloir = pcbnew.SHAPE_SEGMENT(q, fin, MM(larg))
        gene = []
        for t in list(board.GetTracks()):
            if t.IsLocked() or t.GetNetCode() == p.GetNetCode():
                continue
            if t.GetClass() == 'PCB_VIA' or t.GetLayer() == pcbnew.F_Cu:
                if t.GetEffectiveShape(pcbnew.F_Cu).Collide(couloir, 0):
                    gene.append(t)
        for t in gene:
            retirer(t)
        return len(gene)

    # éléments retirés de la carte : gardés en vie jusqu'à la fin (sinon Python les détruit
    # alors que KiCad les référence encore, et l'API renvoie ensuite des objets sans type)
    corbeille = []
    echecs, prioritaires, degages = set(), set(), {}
    hist = None     # historique des conflits du routage négocié, d'un tour à l'autre
    d = degrouper(board, retirer, plans)
    if d:
        print('%s : %d vias et pistes en grappe retirées (nets de plan)' % (nom, d))
    etroites = [0]  # liaisons tirées en passage étroit (0,15 mm, petites vias)
    sur_in2 = [0]   # liaisons passant par In2
    import shutil
    meilleur = None     # meilleur état rencontré (liaisons manquantes + défauts), gardé sur disque
    for tour in range(tours):
        remplir(board)
        e = elaguer(board, retirer)
        if e:
            print('  %d restes de pistes et vias en l\'air retirés' % e)
            remplir(board)
        pcbnew.SaveBoard(chemin, board)
        r = drc(chemin, rapport)
        ids = index()
        paires = [[ids.get(x['uuid']) for x in u['items']] for u in r['unconnected_items']]
        paires = [p for p in paires if None not in p]
        fautes = [v for v in r['violations'] if v['type'] in ('clearance', 'track_width', 'shorting_items',
                                                                 'tracks_crossing', 'hole_clearance',
                                                                 'hole_to_hole', 'copper_edge_clearance')]
        print('%s, tour %d : %d liaisons manquantes, %d défauts de piste'
              % (nom, tour + 1, len(paires), len(fautes)))
        if meilleur is None or len(paires) + len(fautes) < meilleur:
            meilleur = len(paires) + len(fautes)
            shutil.copyfile(chemin, chemin + '.meilleur')
        if not paires and not fautes:
            break
        # pistes en défaut (non verrouillées) : supprimées, la liaison sera retirée au tour suivant
        suppr = 0
        for v in fautes:
            for x in v['items']:
                it = ids.pop(x['uuid'], None)
                if it is None or it.GetClass() not in ('PCB_TRACK', 'PCB_ARC', 'PCB_VIA'):
                    continue
                if not it.IsLocked():
                    retirer(it)
                    suppr += 1
                elif it.GetClass() == 'PCB_VIA' and it.GetNetCode() in plans:
                    # via d'éventail trop près d'une pastille d'une autre classe : retirée avec sa
                    # piste, la pastille sera reliée au plan par une autre via
                    pos = it.GetPosition()
                    for t in list(board.GetTracks()):
                        if t.GetClass() == 'PCB_TRACK' and t.GetNetCode() == it.GetNetCode() and \
                                pos in (t.GetStart(), t.GetEnd()):
                            ids.pop(t.m_Uuid.AsString(), None)
                            retirer(t)
                    retirer(it)
                    suppr += 1
        if suppr:
            print('  %d pistes en défaut supprimées' % suppr)
            continue
        g = Grille(board)
        if hist is None:
            hist = {L: np.zeros((g.H, g.W), np.float32) for L in (pcbnew.F_Cu, pcbnew.B_Cu)}
        g.hist = hist
        faites, ratees, degager = 0, [], []
        vus = set()

        def cle(a, b):
            return (a.GetNetname(), XY(a.GetPosition()), XY(b.GetPosition()) if b is not None else None)
        paires.sort(key=lambda p: (cle(*p) not in prioritaires,
                                   (p[0].GetPosition() - p[1].GetPosition()).EuclideanNorm()))

        arr = 0
        reprises = []       # liaisons sans chemin dans la grille normale

        def echec(a, b):
            """Dernier recours pour la liaison a - b (b = None : de a vers le plan) : routage
            négocié si demandé (le chemin traverse des pistes non verrouillées d'autres nets, qui
            sont arrachées et re-routées au tour suivant), sinon une fois par liaison, retrait
            des pistes non verrouillées collées à a et b, puis abandon."""
            nonlocal arr
            k = cle(a, b)
            n = degages.get(k, 0)
            if negocie and b is not None and b.GetClass() != 'ZONE' and n < 4:
                degages[k] = n + 1
                prioritaires.add(k)
                ls, cl = largeurs(a)
                r = g.relier_souple(a, b, min(ls), cl, retirer, penalite=10.0 + 10.0 * n)
                if r:
                    arr += r[1]
                    return True
            elif not negocie and n < 2:
                degages[k] = n + 1
                degager.append((a, b))
                prioritaires.add(k)
                ratees.append(a.GetNetname())
                return False
            echecs.add(k)
            ratees.append(a.GetNetname())
            return False

        def pastille_seule(it):
            return it is not None and it.GetClass() not in ('ZONE', 'PCB_VIA') and \
                not (it.GetClass() == 'PAD' and it.HasHole())

        for a, b in paires:
            if cle(a, b) in echecs:
                continue
            net = a.GetNetCode()
            if net in plans:
                # d'abord une piste courte vers l'élément voisin (souvent une via du plan ou la
                # pastille d'un condensateur de découplage), sinon une via dans le plan
                ls, cl = largeurs(a)
                if cle(a, b) not in prioritaires and b is not None and b.GetClass() != 'ZONE' and \
                        g.relier(a, b, [w for w in (0.3, 0.25, 0.2) if w <= max(ls)] or [0.2], cl, marges=(2.0,),
                                 vias=False):
                    faites += 1
                    continue
                vp = False
                for it in (a, b):
                    if not pastille_seule(it):
                        continue
                    k = it.m_Uuid.AsString()
                    if k in vus or cle(it, None) in echecs:
                        continue
                    vus.add(k)
                    ls, cl = largeurs(it)
                    if g.vers_plan(it, [w for w in (0.3, 0.25, 0.2) if w <= max(ls)] or [0.2], cl):
                        faites += 1
                        vp = True
                        break
                if not vp:
                    reprises.append((a, b))
            else:
                ls, cl = largeurs(a)
                if g.relier(a, b, ls, cl):
                    faites += 1
                else:
                    reprises.append((a, b))
        if reprises:
            # passages étroits : pistes de 0,15 mm et vias de 0,45 / 0,2 mm (minimums des règles)
            gf = Grille(board, fin=True)
            # en tout dernier recours (in2) : une piste courte dans le plan +3V3 de In2
            gi = Grille(board, fin=True, couches=(pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)) if in2 else None
            for a, b in reprises:
                cl = largeurs(a)[1]
                ok = b is not None and b.GetClass() != 'ZONE' and \
                    gf.relier(a, b, [0.15], cl, marges=(4.0, 12.0), vias=a.GetNetCode() not in plans)
                if not ok and a.GetNetCode() in plans:
                    for it in (a, b):
                        if pastille_seule(it) and cle(it, None) not in echecs:
                            ok = gf.vers_plan(it, [0.15], largeurs(it)[1])
                            if ok:
                                break
                if ok and gi is not None:
                    for it in ok:
                        gi.ajouter(it)
                if not ok and gi is not None and a.GetNetCode() not in plans and \
                        b is not None and b.GetClass() != 'ZONE':
                    ok = gi.relier(a, b, [0.15], cl, cout=(1.0, 1.0, 3.0), marges=(4.0, 12.0))
                    if ok:
                        sur_in2[0] += 1
                        for it in ok:
                            gf.ajouter(it)
                if ok:
                    faites += 1
                    etroites[0] += 1
                elif b is not None and b.GetClass() != 'ZONE':
                    if echec(a, b):
                        faites += 1
                else:
                    for it in (a, b):
                        if pastille_seule(it):
                            echec(it, None)
        arr += sum(degager_sortie(it) + arracher(it) for a, b in degager for it in (a, b) if it is not None)
        print('  %d liaisons tirées, %d impossibles %s ; %d pistes voisines retirées pour les dégager'
              % (faites, len(ratees), ' '.join(ratees[:12]), arr))
        if faites == 0 and arr == 0:
            break
    remplir(board)
    elaguer(board, retirer)
    remplir(board)
    pcbnew.SaveBoard(chemin, board)
    r = drc(chemin, rapport)
    manquantes = len(r['unconnected_items'])
    erreurs = len([v for v in r['violations'] if v['severity'] == 'error'])
    print('%s, fin : %d liaisons manquantes, %d erreurs (%d liaisons en passage étroit, dont %d par In2)'
          % (nom, manquantes, erreurs, etroites[0], sur_in2[0]))
    if manquantes + erreurs > meilleur:
        shutil.copyfile(chemin + '.meilleur', chemin)
        print('  moins bien qu\'au meilleur tour : carte du meilleur tour reprise (%d)' % meilleur)
    os.remove(chemin + '.meilleur')


# ---------------------------------------------------------------------------- finitions
CUIVRE = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
# pastilles de puissance reliées en plein (sans freins thermiques) au plan de masse de F.Cu
PLEIN = {'can8-mere': [('D1003', '2'), ('C1001', '2'), ('C1002', '2'), ('C1003', '2'),
                       ('C1007', '2'), ('C1008', '2'), ('U1001', '7'), ('U1001', '9')]}


def contour(z):
    o = z.Outline().Outline(0)
    return [XY(o.CPoint(i)) for i in range(o.PointCount())]


def plans_externes(c, nom):
    """Copie sur F.Cu et B.Cu des plans de masse de In1 (GND, GND_ISO de chaque port)."""
    for z in [z for z in c.b.Zones() if not z.GetIsRuleArea() and z.GetLayer() == pcbnew.In1_Cu]:
        for couche, suffixe in ((pcbnew.F_Cu, 'dessus'), (pcbnew.B_Cu, 'dessous')):
            c.zone(z.GetNet(), couche, contour(z), prio=0, nom='%s %s' % (z.GetZoneName(), suffixe),
                   isolement=0.3)
    for ref, num in PLEIN.get(nom, []):
        for p in c.fp[ref].Pads():
            if p.GetNumber() == num:
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)


class Obstacles:
    """Index spatial (grille de 2 mm) des pastilles, pistes et vias, pour placer les vias de couture."""
    PAS = 2.0

    def __init__(self, board):
        self.cases = {}
        for fp in board.GetFootprints():
            for p in fp.Pads():
                self.ajouter(p)
        for t in board.GetTracks():
            self.ajouter(t)

    def _cases(self, bb, marge):
        x0, y0 = XY(bb.GetOrigin())
        x1, y1 = XY(bb.GetEnd())
        for i in range(int(math.floor((x0 - marge) / self.PAS)), int(math.floor((x1 + marge) / self.PAS)) + 1):
            for j in range(int(math.floor((y0 - marge) / self.PAS)), int(math.floor((y1 + marge) / self.PAS)) + 1):
                yield i, j

    def ajouter(self, item):
        for k in self._cases(item.GetBoundingBox(), 1.0):
            self.cases.setdefault(k, []).append(item)

    def autour(self, x, y):
        return self.cases.get((int(math.floor(x / self.PAS)), int(math.floor(y / self.PAS))), [])

    def proches(self, x, y, r):
        out = []
        n = int(math.ceil(r / self.PAS))
        i0, j0 = int(math.floor(x / self.PAS)), int(math.floor(y / self.PAS))
        for i in range(i0 - n, i0 + n + 1):
            for j in range(j0 - n, j0 + n + 1):
                out += self.cases.get((i, j), [])
        return out

    def libre_piste(self, seg, net, isolement, ignore=None):
        """Piste seg sur F.Cu sans toucher le cuivre d'un autre net."""
        a, b2 = XY(seg.GetSeg().A), XY(seg.GetSeg().B)
        r = math.hypot(a[0] - b2[0], a[1] - b2[1]) / 2 + 1
        ign = ignore.m_Uuid.AsString() if ignore is not None else None
        vus = set()
        for item in self.proches((a[0] + b2[0]) / 2, (a[1] + b2[1]) / 2, r):
            if id(item) in vus:
                continue
            vus.add(id(item))
            if item.GetNetCode() == net or (ign is not None and item.m_Uuid.AsString() == ign):
                continue
            if item.IsOnLayer(pcbnew.F_Cu) and item.GetEffectiveShape(pcbnew.F_Cu).Collide(seg, MM(isolement)):
                return False
        return True

    def libre(self, x, y, rayon, isolement, net=None, seg=None, ignore=None):
        """Via de rayon donné en (x, y) (et piste seg sur F.Cu) sans toucher le cuivre d'un autre
        net (ou de tout net si net est None)."""
        cercle = pcbnew.SHAPE_CIRCLE(V(x, y), MM(rayon))
        items = list(self.autour(x, y))
        if seg is not None:
            a, b2 = seg.GetSeg().A, seg.GetSeg().B
            for q in (a, b2):
                items += self.autour(*XY(q))
        vus = set()
        ign = ignore.m_Uuid.AsString() if ignore is not None else None
        for item in items:
            if id(item) in vus:
                continue
            vus.add(id(item))
            if (ign is not None and item.m_Uuid.AsString() == ign) or (net is not None and item.GetNetCode() == net and item.GetClass() == 'PCB_TRACK'
                                  and seg is None):
                continue
            for couche in CUIVRE:
                if item.IsOnLayer(couche) and item.GetEffectiveShape(couche).Collide(cercle, MM(isolement)):
                    return False
            if seg is not None and item.IsOnLayer(pcbnew.F_Cu) and \
                    item.GetEffectiveShape(pcbnew.F_Cu).Collide(seg, MM(isolement)):
                return False
        return True


def distance_bords(board):
    poly = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(poly)
    segs = []
    for i in range(poly.OutlineCount()):
        chaines = [poly.Outline(i)] + [poly.Hole(i, h) for h in range(poly.HoleCount(i))]
        for ch in chaines:
            for k in range(ch.SegmentCount()):
                segs.append(ch.CSegment(k))

    def dist(x, y):
        p = V(x, y)
        return min(pcbnew.ToMM(s.Distance(p)) for s in segs)
    return poly, dist


def couture(c, pas=4.0, rayon=0.3, isolement=0.3):
    """Vias de couture entre les plans de masse des couches externes et de In1."""
    b = c.b
    obst = Obstacles(b)
    interdits = [z for z in b.Zones() if z.GetIsRuleArea()]
    poly, dist_bord = distance_bords(b)
    n = 0
    for z in [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetLayer() == pcbnew.In1_Cu]:
        pts = contour(z)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x = math.floor(min(xs) / pas) * pas + pas / 2
        while x < max(xs):
            y = math.floor(min(ys) / pas) * pas + pas / 2
            while y < max(ys):
                ok = all(z.Outline().Contains(V(x + dx, y + dy)) for dx, dy in
                         ((-1, -1), (1, -1), (1, 1), (-1, 1)))
                ok = ok and poly.Contains(V(x, y)) and dist_bord(x, y) > 1.2
                ok = ok and not any(k.GetLayerSet().Contains(pcbnew.F_Cu) and
                                    k.Outline().Collide(V(x, y), MM(rayon + 0.3)) for k in interdits)
                if ok and obst.libre(x, y, rayon, isolement):
                    v = c.via(z.GetNet(), x, y, verrou=False)
                    obst.ajouter(v)
                    n += 1
                y += pas
            x += pas
    return n


def serigraphie(c, hauteur=0.8, epaisseur=0.12, jeu=0.15):
    """Range les repères : au-dessus, en dessous, à gauche ou à droite du composant, à la première
    place libre (ni pastille, ni dessin de sérigraphie, ni autre repère, ni bord de carte).
    Sans place libre, le repère est masqué sur la sérigraphie (il reste sur la couche Fab)."""
    b = c.b
    poly, dist_bord = distance_bords(b)
    obst = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    cuivre = {pcbnew.F_SilkS: pcbnew.F_Cu, pcbnew.B_SilkS: pcbnew.B_Cu}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            for s, cu in cuivre.items():
                if p.IsOnLayer(cu):
                    obst[s].append(p.GetEffectiveShape(cu))
        for g in fp.GraphicalItems():
            if g.GetLayer() in obst and g.GetClass() != 'PCB_TEXT':
                obst[g.GetLayer()].append(g.GetEffectiveShape(g.GetLayer()))
    for d in b.GetDrawings():
        if d.GetLayer() in obst:
            obst[d.GetLayer()].append(d.GetEffectiveShape(d.GetLayer()))

    def boite(t):
        bb = t.GetBoundingBox()
        return pcbnew.SHAPE_RECT(bb.GetOrigin(), bb.GetWidth(), bb.GetHeight()), bb

    masques = 0
    fps = sorted(b.GetFootprints(), key=lambda f: -f.GetCourtyard(f.GetSide()).BBox().GetArea())
    for fp in fps:
        t = fp.Reference()
        couche = t.GetLayer()
        if couche not in obst or not t.IsVisible():
            continue
        t.SetTextSize(pcbnew.VECTOR2I(MM(hauteur), MM(hauteur)))
        t.SetTextThickness(MM(epaisseur))
        t.SetTextAngleDegrees(0)
        t.SetKeepUpright(True)
        cy = fp.GetCourtyard(pcbnew.F_CrtYd if couche == pcbnew.F_SilkS else pcbnew.B_CrtYd).BBox()
        if cy.GetWidth() == 0:
            cy = fp.GetBoundingBox(False)
        x0, y0 = XY(cy.GetOrigin())
        x1, y1 = XY(cy.GetEnd())
        xc, yc = (x0 + x1) / 2, (y0 + y1) / 2
        t.SetPosition(V(xc, yc))
        _, bb = boite(t)
        w, h = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
        essais = [(xc, y0 - h / 2 - 0.2), (xc, y1 + h / 2 + 0.2), (x0 - w / 2 - 0.2, yc),
                  (x1 + w / 2 + 0.2, yc), (x0 + w / 2, y0 - h / 2 - 0.2), (x1 - w / 2, y0 - h / 2 - 0.2),
                  (x0 + w / 2, y1 + h / 2 + 0.2), (x1 - w / 2, y1 + h / 2 + 0.2)]
        place = False
        for x, y in essais:
            t.SetPosition(V(x, y))
            r, bb = boite(t)
            coins = [XY(bb.GetOrigin()), XY(bb.GetEnd())]
            if not all(poly.Contains(V(px, py)) and dist_bord(px, py) > 0.3
                       for px in (coins[0][0], coins[1][0]) for py in (coins[0][1], coins[1][1])):
                continue
            if any(o.Collide(r, MM(jeu)) for o in obst[couche]):
                continue
            place = True
            obst[couche].append(r)
            break
        if not place:
            t.SetPosition(V(xc, yc))
            t.SetVisible(False)
            masques += 1
    return masques


EMPILAGE = """\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "prepreg") (thickness 0.0994) (material "FR4 3313") (epsilon_r 4.1) (loss_tangent 0.02))
\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 2" (type "core") (thickness 1.265) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 3" (type "prepreg") (thickness 0.0994) (material "FR4 3313") (epsilon_r 4.1) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))
\t\t\t(copper_finish "ENIG")
\t\t\t(dielectric_constraints no)
\t\t)
"""


def empilage(chemin):
    """Empilage 4 couches 1,6 mm de type JLC04161H-3313 (prépreg 0,1 mm sous les couches externes),
    écrit dans le réglage de la carte : il sert au calcul d'impédance et aux plans de fabrication."""
    texte = open(chemin, encoding='utf-8').read()
    if '(stackup' not in texte:
        texte = texte.replace('\t(setup\n', '\t(setup\n' + EMPILAGE, 1)
        open(chemin, 'w', encoding='utf-8').write(texte)


VERSION = 'v0.3'


def version(board):
    """Révision v0.3 (routée) dans le cartouche et le texte de sérigraphie de la carte."""
    tb = board.GetTitleBlock()
    tb.SetRevision(VERSION)
    tb.SetTitle(tb.GetTitle().replace('placement des composants (non routé)', 'circuit imprimé'))
    for d in board.GetDrawings():
        if d.GetClass() == 'PCB_TEXT' and 'v0.2' in d.GetText():
            d.SetText(d.GetText().replace('v0.2', VERSION))


def finir(nom):
    board = pcbnew.LoadBoard(chemin_carte(nom))
    c = Carte(board)
    version(board)
    plans_externes(c, nom)
    n = couture(c)
    m = serigraphie(c)
    remplir(board)
    pcbnew.SaveBoard(chemin_carte(nom), board)
    empilage(chemin_carte(nom))
    print('%s : plans des couches externes ajoutés, %d vias de couture, %d repères masqués'
          % (nom, n, m))


def rapport(nom):
    """Longueurs des liaisons rapides (ULPI, USB) et statistiques de routage."""
    board = pcbnew.LoadBoard(chemin_carte(nom))
    longueurs, couches = {}, {}
    vias = 0
    for t in board.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            vias += 1
            continue
        n = t.GetNetname()
        longueurs[n] = longueurs.get(n, 0) + pcbnew.ToMM(t.GetLength())
        couches.setdefault(n, set()).add(board.GetLayerName(t.GetLayer()))
    pistes = sum(1 for t in board.GetTracks() if t.GetClass() != 'PCB_VIA')
    print('%s : %d segments de piste, %d vias, %.0f mm de pistes'
          % (nom, pistes, vias, sum(longueurs.values())))
    for n in sorted(longueurs):
        if 'ULPI' in n or 'USB_D' in n:
            print('  %-32s %6.1f mm  %s' % (n.split('/')[-1], longueurs[n], ','.join(sorted(couches[n]))))
    sur_in2 = sorted({n.split('/')[-1] for n, c in couches.items() if 'In2.Cu' in c})
    print('  nets passant par In2 : %d %s' % (len(sur_in2), ' '.join(sur_in2)))


if __name__ == '__main__':
    etape, nom = sys.argv[1], sys.argv[2]
    if etape == 'completer':
        # options : --in2 (dernier recours par In2), --negocie (routage négocié)
        completer(nom, in2='--in2' in sys.argv, negocie='--negocie' in sys.argv)
    else:
        {'preparer': preparer, 'importer': importer, 'finir': finir, 'rapport': rapport}[etape](nom)
