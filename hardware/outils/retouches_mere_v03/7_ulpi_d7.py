"""7_ulpi_d7.py carte : raccourcit le bout de ULPI_D7 qui dépassait de 0,25 mm sa jonction (avertissement
« piste en l'air » du DRC) ; la carte est modifiée en place."""
import os, sys, pcbnew
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import router as R
b = pcbnew.LoadBoard(sys.argv[1]); FM, TM = pcbnew.FromMM, pcbnew.ToMM
for t in b.GetTracks():
    if t.GetNetname() == 'ULPI_D7' and t.GetClass() == 'PCB_TRACK' and t.GetLayer() == pcbnew.F_Cu:
        for get, put in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
            p = get()
            if abs(TM(p.x) - 101.75) < 0.01 and abs(TM(p.y) - 54.3) < 0.01:
                put(pcbnew.VECTOR2I(p.x, FM(54.55))); print('stub D7 raccourci')
R.remplir(b); pcbnew.SaveBoard(sys.argv[1], b)
