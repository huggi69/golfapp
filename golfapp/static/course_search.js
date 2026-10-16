// Formular "Platz hinzufügen" automatisch füllen – aus zwei Quellen:
//  1. Platzsuche über die offene API von handicap.report (CORS, ohne Schlüssel)
//     Doku: https://handicap.report/api/v1/
//  2. Foto der Scorekarte, ausgelesen auf dem Server (POST /courses/scan, Claude)
(() => {
  const $ = id => document.getElementById(id);
  const info = $('hr-info');
  if (!info) return;

  function message(text, cls) {
    info.textContent = text;
    info.className = 'hr-info ' + (cls || '');
  }

  // Beide Quellen lassen sich kombinieren, in beliebiger Reihenfolge. Je Feld gilt:
  //   Löcher (Par, Hcp-Reihenfolge): Foto vor API – die Karte zeigt den gespielten Platz genau
  //   Abschläge (CR, Slope):         API vor Foto – handicap.report pflegt die offiziellen Werte
  //   Name:                          API vor Foto
  const RANK = { holes: { foto: 2, api: 1 }, tees: { api: 2, foto: 1 }, name: { api: 2, foto: 1 } };
  const LABEL = { foto: 'Foto', api: 'handicap.report' };
  let filled = {};       // Feld -> Quelle, die es zuletzt gefüllt hat
  let teesPar = null;    // Par laut API-Abschlag, zum Abgleich mit der Karte
  const wins = (field, source) => !filled[field] || RANK[field][source] >= RANK[field][filled[field]];

  // Gemeinsames Füllen: {name, pars: [..]|null, stroke_index: [..]|null,
  //   tees: [{name, course_rating, slope, par?, unsicher?}], warnings: [..]}
  function fillForm(data, source) {
    const warnings = [...(data.warnings || [])];
    if (data.name && wins('name', source)) { $('new-name').value = data.name; filled.name = source; }
    if (data.pars && wins('holes', source)) {
      $('new-pars').value = data.pars.join(',');
      $('new-si').value = data.stroke_index ? data.stroke_index.join(',') : '';
      filled.holes = source;
    }

    const tees = data.tees || [];
    if (tees.length && wins('tees', source)) {
      $('new-tees').value = JSON.stringify(tees.map(({ name, course_rating, slope }) => ({ name, course_rating, slope })));
      filled.tees = source;
      if (source === 'api') teesPar = (tees.find(t => t.par) || {}).par || null;
      renderTees(tees);
    }
    if (!filled.tees) warnings.push('Keine Abschläge mit Course Rating und Slope – Platz oben suchen oder nach dem Speichern ergänzen.');

    // Passt der gewählte API-Platz zur fotografierten Karte?
    const parSum = $('new-pars').value.split(',').map(Number).reduce((a, b) => a + b, 0);
    if (filled.holes === 'foto' && filled.tees === 'api' && teesPar && parSum && teesPar !== parSum) {
      warnings.push(`Achtung: Par laut Karte ${parSum}, laut handicap.report ${teesPar} – richtigen Platz gewählt?`);
    }
    const origin = ['holes', 'tees'].filter(f => filled[f])
      .map(f => `${f === 'holes' ? 'Löcher' : 'Abschläge'}: ${LABEL[filled[f]]}`).join(' · ');
    message((origin ? origin + '. ' : '') +
      (warnings.length ? warnings.join(' ') : 'Bitte prüfen und „Hinzufügen“ tippen.'),
      warnings.length ? 'warn' : 'ok');
    $('new-name').scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  function renderTees(tees) {
    const preview = $('hr-tees');
    preview.innerHTML = '';
    if (tees.length) {
      const head = document.createElement('div');
      head.className = 'play-label';
      head.textContent = 'Abschläge (werden mit angelegt)';
      preview.appendChild(head);
      tees.forEach(t => {
        const row = document.createElement('div');
        row.className = 'small';
        row.textContent = `${t.name}: CR ${String(t.course_rating).replace('.', ',')} / Slope ${t.slope}` +
          (t.par ? ` · Par ${t.par}` : '') + (t.unsicher ? ' · ungeprüft' : '');
        preview.appendChild(row);
      });
    }
  }

  $('hr-reset').addEventListener('click', () => {
    $('new-tees').value = '';
    $('hr-tees').innerHTML = '';
    filled = {};
    teesPar = null;
    message('');
  });

  // ---- 1. Platzsuche handicap.report -----------------------------------------
  const API = 'https://handicap.report/api/v1/courses.php';
  const input = $('hr-search'), list = $('hr-results');

  async function getJson(params) {
    const res = await fetch(API + '?' + new URLSearchParams(params), { credentials: 'omit' });
    if (!res.ok) throw new Error(res.status);
    return res.json();
  }
  // Index-Antwort: Liste direkt oder in einem Feld verpackt
  const asList = d => Array.isArray(d) ? d : (d.courses || d.results || d.items || d.data || []);
  const genderLabel = g => ({ M: 'Herren', F: 'Damen' }[g] || '');

  let timer = null, lastQuery = '';
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) { list.innerHTML = ''; return; }
    timer = setTimeout(() => search(q), 350);
  });

  async function search(q) {
    lastQuery = q;
    message('Suche …');
    let courses;
    try {
      courses = asList(await getJson({ q }));
    } catch (e) {
      message('handicap.report ist gerade nicht erreichbar – Daten bitte von Hand eintragen.', 'warn');
      return;
    }
    if (q !== lastQuery) return;  // ältere Antwort, inzwischen weitergetippt
    list.innerHTML = '';
    courses.slice(0, 20).forEach(c => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'hr-result';
      const title = document.createElement('strong');
      title.textContent = c.club || c.id;
      const sub = document.createElement('span');
      sub.className = 'muted small';
      sub.textContent = [c.ort, c.holeCount ? c.holeCount + ' Loch' : '', c.courseName,
        c.hasHoles === false ? 'ohne Lochdaten' : ''].filter(Boolean).join(' · ');
      b.append(title, sub);
      b.addEventListener('click', () => choose(c.id));
      list.appendChild(b);
    });
    message(courses.length ? `${courses.length} Treffer – Platz antippen zum Übernehmen.` : 'Keine Treffer.');
  }

  async function choose(id) {
    message('Lade Platzdaten …');
    let c;
    try {
      c = await getJson({ id });
    } catch (e) {
      message('Platzdaten konnten nicht geladen werden.', 'warn');
      return;
    }
    const warnings = [];
    const holes = Array.isArray(c.holes) ? [...c.holes].sort((a, b) => a.number - b.number) : [];
    let pars = null, si = null;
    if (holes.length === 9 || holes.length === 18) {
      if (holes.every(h => Number.isInteger(h.par))) pars = holes.map(h => h.par);
      else warnings.push('Par je Loch unvollständig – bitte prüfen.');
      if (holes.every(h => Number.isInteger(h.strokeIndex))) si = holes.map(h => h.strokeIndex);
      else warnings.push('Keine Handicap-Reihenfolge vorhanden – Nettopunkte werden dann von Hand erfasst.');
    } else {
      warnings.push(`Keine Lochdaten für ${c.holeCount || '?'} Loch – Par bitte von der Scorekarte eintragen.`);
    }
    list.innerHTML = '';
    // Löcher aus dem Foto bleiben stehen – dann sind fehlende Lochdaten der API kein Problem
    if (filled.holes === 'foto') warnings.length = 0;
    fillForm({
      name: [c.club, c.courseName].filter(Boolean).join(' – '),
      pars, stroke_index: si, warnings,
      tees: (c.tees || []).filter(t => typeof t.cr === 'number' && Number.isInteger(t.slope)).map(t => ({
        name: [t.name, genderLabel(t.gender)].filter(Boolean).join(' '),
        course_rating: t.cr, slope: t.slope, par: t.par, unsicher: !!t.unsicher,
      })),
    }, 'api');
  }

  // Nach dem Foto: Club bei handicap.report suchen. Namen auf Karten sind oft lang
  // ("Golfclub Grevenmühle e.V.") – ohne Treffer mit dem prägnantesten Wort erneut suchen.
  async function suggestTees(name, scanText, scanClass) {
    const GENERIC = /^(golf|club|golfclub|golfplatz|gc|gut|e\.?v\.?|und|am|an|der|die|das|von)$/i;
    const keyword = name.split(/[\s,–-]+/).filter(w => w.length >= 4 && !GENERIC.test(w))
      .sort((a, b) => b.length - a.length)[0];
    for (const q of [name, keyword].filter(Boolean)) {
      input.value = q;
      await search(q);
      if (list.children.length) break;
    }
    const hint = list.children.length
      ? ' Für die Abschläge den passenden Platz unten antippen.'
      : ' Platz bei handicap.report nicht gefunden – Suchbegriff oben anpassen.';
    message(scanText + hint, scanClass.replace('hr-info', '').trim());
    // Treffer stehen über dem Formular – dorthin scrollen, damit man den Platz gleich antippen kann
    if (list.children.length) info.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  // ---- 2. Foto der Scorekarte ------------------------------------------------
  const photo = $('scan-photo');
  if (!photo) return;  // Bilderkennung auf dem Server nicht eingerichtet

  // Handyfotos sind oft 4–12 MB: im Browser auf max. 2400 px verkleinern und als JPEG senden
  async function shrink(file, maxSide = 2400) {
    const img = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
  }

  photo.addEventListener('change', async () => {
    const file = photo.files[0];
    if (!file) return;
    const label = $('scan-label');
    label.classList.add('busy');
    message('Lese Scorekarte … das dauert meist 10–40 Sekunden.');
    try {
      let blob;
      try { blob = await shrink(file); } catch (e) { blob = file; }  // Format unbekannt: Original senden
      const form = new FormData();
      form.append('image', blob, 'scorekarte.jpg');
      const res = await fetch(photo.dataset.url, { method: 'POST', body: form, credentials: 'same-origin' });
      let data = {};
      try { data = await res.json(); } catch (e) { /* z.B. Login abgelaufen */ }
      if (!res.ok) {
        message(data.error || (res.status === 401 ? 'Bitte neu anmelden.' : `Fehler ${res.status}`), 'warn');
        return;
      }
      fillForm(data, 'foto');
      // Für die offiziellen Abschläge gleich den erkannten Club bei handicap.report suchen
      if (data.name && filled.tees !== 'api') suggestTees(data.name, info.textContent, info.className);
    } catch (e) {
      message('Foto konnte nicht gesendet werden – Internetverbindung prüfen.', 'warn');
    } finally {
      label.classList.remove('busy');
      photo.value = '';
    }
  });
})();
