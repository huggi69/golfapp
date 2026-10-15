// Spracheingabe für die Erfassung Loch für Loch.
//
// parseVoice("Franky 5 1, Huggi 4 2", players) ->
//   { results: [{player, strokes: 5, putts: 1}, {player, strokes: 4, putts: 2}], unknown: [] }
// Eine dritte Zahl je Spieler ("Franky 5 1 2") wird als Nettopunkte gelesen.
//
// Die Spracherkennung liefert Zahlen mal als Ziffern, mal als Wörter ("fünf eins"),
// und zieht sie manchmal zusammen ("51"). Namen werden unscharf erkannt ("Hugi", "Frank").
(function (root) {
  const NUMBER_WORDS = {
    null: 0, zero: 0,
    eins: 1, ein: 1, eine: 1, einen: 1, one: 1,
    zwei: 2, zwo: 2, two: 2,
    drei: 3, three: 3,
    vier: 4, four: 4,
    fünf: 5, fuenf: 5, five: 5,
    sechs: 6, six: 6,
    sieben: 7, seven: 7,
    acht: 8, eight: 8,
    neun: 9, nine: 9,
    zehn: 10, ten: 10,
    elf: 11, eleven: 11,
    zwölf: 12, zwoelf: 12, twelve: 12,
  };
  // Füllwörter, die zwischen Name und Zahlen auftauchen können
  const FILLER = new Set(['und', 'hat', 'mit', 'schläge', 'schlag', 'putts', 'putt', 'puts', 'put', 'and']);

  function normalize(text) {
    return String(text || '')
      .toLowerCase()
      .replace(/[.,;:!?/\-–]+/g, ' ')
      .split(/\s+/)
      .filter(Boolean);
  }

  function levenshtein(a, b) {
    const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
    for (let j = 1; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++) {
      for (let j = 1; j <= b.length; j++) {
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1,
          d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
    }
    return d[a.length][b.length];
  }

  // Bester Spieler für ein Wort oder null
  function matchPlayer(word, players) {
    if (/^\d+$/.test(word) || word in NUMBER_WORDS || FILLER.has(word) || word.length < 3) return null;
    let best = null, bestScore = Infinity;
    for (const p of players) {
      const name = p.name.toLowerCase();
      const first = name.split(/\s+/)[0];
      let score;
      if (word === name || word === first) score = 0;
      else if (first.startsWith(word) || word.startsWith(first)) score = 1;  // "frank" ~ "franky"
      else {
        const dist = Math.min(levenshtein(word, first), levenshtein(word, name));
        score = dist <= Math.max(1, Math.floor(first.length / 3)) ? 1 + dist : Infinity;
      }
      if (score < bestScore) { best = p; bestScore = score; }
    }
    return bestScore === Infinity ? null : best;
  }

  // Zahlen nach einem Namen: "5 1" | "fünf eins" | "51" (zusammengezogen) | "10 2"
  function numbersFrom(words) {
    const nums = [];
    for (const w of words) {
      if (/^\d+$/.test(w)) {
        // zwei- oder dreistellig ohne Leerzeichen erkannt -> in Schläge und Putts aufteilen
        // "51" -> 5 Schläge, 1 Putt; "13" bleibt 13 (1 Schlag mit 3 Putts gibt es nicht)
        if (w.length === 2 && nums.length === 0 && Number(w) > 12 && Number(w[1]) < Number(w[0])) {
          nums.push(Number(w[0]), Number(w[1]));
        }
        else if (w.length === 3 && nums.length === 0) nums.push(Number(w.slice(0, 2)), Number(w[2]));
        else nums.push(Number(w));
      } else if (w in NUMBER_WORDS) {
        nums.push(NUMBER_WORDS[w]);
      }
    }
    return nums;
  }

  function parseVoice(text, players) {
    const words = normalize(text);
    const groups = [];  // {player, words: []}
    const unknown = [];
    let current = null;
    for (const w of words) {
      const p = matchPlayer(w, players);
      if (p) {
        current = { player: p, words: [] };
        groups.push(current);
      } else if (current) {
        current.words.push(w);
      } else if (!FILLER.has(w)) {
        unknown.push(w);
      }
    }
    const results = [];
    for (const g of groups) {
      const [strokes, putts, net] = numbersFrom(g.words);
      if (strokes === undefined || strokes < 1 || strokes > 20) continue;
      const r = { player: g.player, strokes };
      if (putts !== undefined && putts >= 0 && putts < strokes) r.putts = putts;
      // optional dritte Zahl: Nettopunkte (nur genutzt, wenn sie nicht berechnet werden)
      if (net !== undefined && net >= 0 && net <= 10) r.net = net;
      // spätere Nennung desselben Spielers gewinnt
      const i = results.findIndex(x => x.player.id === r.player.id);
      if (i >= 0) results[i] = r; else results.push(r);
    }
    return { results, unknown };
  }

  const api = { parseVoice, matchPlayer, normalize };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Voice = api;
})(typeof window !== 'undefined' ? window : globalThis);
