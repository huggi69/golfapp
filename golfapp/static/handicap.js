// Spiegelt golfapp/handicap.py für die Live-Anzeige im Browser.
// Maßgeblich ist die Berechnung auf dem Server.
const Hcp = {
  parseNum(text) {
    text = String(text ?? '').trim().replace(',', '.');
    if (text === '') return null;
    const v = Number(text);
    return Number.isFinite(v) ? v : null;
  },
  parseIndex(text) {
    text = String(text ?? '').trim();
    const plus = text.startsWith('+');
    const v = Hcp.parseNum(text.replace(/^\+/, ''));
    if (v === null) return null;
    return plus ? -Math.abs(v) : v;
  },
  playingHandicap(index, cr, slope, par, holes) {
    if ([index, cr, slope, par].some(v => v === null || v === undefined)) return null;
    if (holes === 9) index = index / 2;
    return Math.floor(index * slope / 113 + (cr - par) + 0.5);
  },
  // si: Array von {hole, si}; Rückgabe: {hole: Vorgabeschläge}
  strokesReceived(ph, si) {
    const order = [...si].sort((a, b) => a.si - b.si || a.hole - b.hole);
    const n = order.length, res = {};
    if (!n || ph === null) return res;
    const base = Math.floor(Math.abs(ph) / n), rest = Math.abs(ph) % n;
    order.forEach((h, rank) => {
      res[h.hole] = ph >= 0 ? base + (rank < rest ? 1 : 0) : -(base + (rank >= n - rest ? 1 : 0));
    });
    return res;
  },
  stableford(par, received, strokes) {
    return Math.max(0, 2 + par + received - strokes);
  },
};
