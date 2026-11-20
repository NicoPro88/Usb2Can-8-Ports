# can8-mere v0.3 : pas encore fabricable

Le routage n'est pas terminé : **10 liaisons restent à tirer** (DRC de KiCad, liaisons
manquantes ; détails dans docs/routage.md). Les fichiers Gerber et de perçage ne sont donc
volontairement pas fournis pour cette carte.

Une fois les liaisons terminées dans KiCad (DRC sans liaison manquante), régénérer les sorties :

    sh hardware/outils/exporter.sh v0.3 can8-mere

Les autres fichiers de ce dossier (schéma, vue PDF des couches, nomenclature, placement CMS,
rendus) correspondent à l'état actuel de la carte.
