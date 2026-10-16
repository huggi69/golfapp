// Platzsuche über die offene API von handicap.report (CORS, ohne Schlüssel).
// Füllt das Formular "Platz hinzufügen": Name, Par je Loch, Stroke-Index und Abschläge.
// Doku: https://handicap.report/api/v1/
(() => {
  const API = 'https://handicap.report/api/v1/courses.php';
  const $ = id => document.getElementById(id);
  const input = $('hr-search'), list = $('hr-results'), info = $('hr-info');
  if (!input) return;

  function message(text, cls) {
    info.textContent = text;
    info.className = 'hr-info ' + (cls || '');
  }

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
    $('new-name').value = [c.club, c.courseName].filter(Boolean).join(' – ');

    const holes = Array.isArray(c.holes)
      ? [...c.holes].sort((a, b) => a.number - b.number) : [];
    if (holes.length === 9 || holes.length === 18) {
      if (holes.every(h => Number.isInteger(h.par))) $('new-pars').value = holes.map(h => h.par).join(',');
      else warnings.push('Par je Loch unvollständig – bitte prüfen.');
      if (holes.every(h => Number.isInteger(h.strokeIndex))) {
        $('new-si').value = holes.map(h => h.strokeIndex).join(',');
      } else {
        $('new-si').value = '';
        warnings.push('Keine Handicap-Reihenfolge vorhanden – Nettopunkte werden dann von Hand erfasst.');
      }
    } else {
      warnings.push(`Keine Lochdaten für ${c.holeCount || '?'} Loch – Par bitte von der Scorekarte eintragen.`);
    }

    const tees = (c.tees || []).filter(t => typeof t.cr === 'number' && Number.isInteger(t.slope))
      .map(t => ({
        name: [t.name, genderLabel(t.gender)].filter(Boolean).join(' '),
        course_rating: t.cr, slope: t.slope, par: t.par, unsicher: !!t.unsicher,
      }));
    $('new-tees').value = JSON.stringify(tees.map(({ name, course_rating, slope }) => ({ name, course_rating, slope })));

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
    } else {
      warnings.push('Keine Abschläge mit Course Rating und Slope gefunden.');
    }

    list.innerHTML = '';
    message(warnings.length ? warnings.join(' ') : 'Übernommen – bitte prüfen und „Hinzufügen“ tippen.',
      warnings.length ? 'warn' : 'ok');
    $('new-name').scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  // Bei manueller Änderung des Namens bleiben die übernommenen Abschläge erhalten;
  // "Zurücksetzen" verwirft sie.
  $('hr-reset').addEventListener('click', () => {
    $('new-tees').value = '';
    $('hr-tees').innerHTML = '';
    message('');
  });
})();
