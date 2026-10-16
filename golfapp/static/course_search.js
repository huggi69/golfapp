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

  // Gemeinsames Füllen: {name, pars: [..]|null, stroke_index: [..]|null,
  //   tees: [{name, course_rating, slope, par?, unsicher?}], warnings: [..]}
  function fillForm(data) {
    const warnings = [...(data.warnings || [])];
    if (data.name) $('new-name').value = data.name;
    if (data.pars) $('new-pars').value = data.pars.join(',');
    $('new-si').value = data.stroke_index ? data.stroke_index.join(',') : '';

    const tees = data.tees || [];
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
      warnings.push('Keine Abschläge mit Course Rating und Slope gefunden – nach dem Speichern von Hand ergänzen.');
    }
    message(warnings.length ? warnings.join(' ') : 'Übernommen – bitte prüfen und „Hinzufügen“ tippen.',
      warnings.length ? 'warn' : 'ok');
    $('new-name').scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  $('hr-reset').addEventListener('click', () => {
    $('new-tees').value = '';
    $('hr-tees').innerHTML = '';
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
    fillForm({
      name: [c.club, c.courseName].filter(Boolean).join(' – '),
      pars, stroke_index: si, warnings,
      tees: (c.tees || []).filter(t => typeof t.cr === 'number' && Number.isInteger(t.slope)).map(t => ({
        name: [t.name, genderLabel(t.gender)].filter(Boolean).join(' '),
        course_rating: t.cr, slope: t.slope, par: t.par, unsicher: !!t.unsicher,
      })),
    });
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
      fillForm(data);
    } catch (e) {
      message('Foto konnte nicht gesendet werden – Internetverbindung prüfen.', 'warn');
    } finally {
      label.classList.remove('busy');
      photo.value = '';
    }
  });
})();
