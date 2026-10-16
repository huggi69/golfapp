"""Scorekarte per Foto auslesen (Claude, Bildverständnis).

Das Foto geht an die Claude-API; zurück kommt über ein festes JSON-Schema (Structured Outputs)
Par und Handicap-Reihenfolge je Loch sowie – falls aufgedruckt – Course Rating und Slope je
Abschlag. Die Werte werden hier geprüft, bevor sie ins Formular übernommen werden.

Voraussetzung: ANTHROPIC_API_KEY ist in der Umgebung des Servers gesetzt.
"""

import base64
import json
import os

MODEL = "claude-opus-5-5"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # Bildgrenze der API (base64-dekodiert großzügig darunter)
MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

PROMPT = """Das Bild zeigt die Scorekarte eines Golfplatzes. Lies für jedes Loch Par und
Handicap aus. Das Handicap ist die Schwierigkeitsreihenfolge der Löcher (1 = schwerstes Loch);
auf deutschen Karten heißt die Zeile meist „Hcp“, „HCP“, „Vorgabe“ oder „S.I.“.

- Gib die Löcher in Reihenfolge 1 bis N an (9 oder 18 Löcher, je nachdem was die Karte zeigt).
- Gibt es getrennte Hcp-Zeilen für Herren und Damen, nimm die der Herren und vermerke das in warnings.
- Sind Course Rating (CR) und Slope je Abschlag aufgedruckt (z.B. nach Farbe, Herren/Damen),
  übernimm sie in tees; sonst lass tees leer.
- Erfinde keine Werte. Ist ein Wert nicht lesbar, setze 0 und nenne das Loch in warnings.
- club_name: Name des Clubs bzw. Platzes, falls auf der Karte zu sehen, sonst leer.
- warnings auf Deutsch, kurz."""

SCHEMA = {
    "type": "object",
    "properties": {
        "club_name": {"type": "string"},
        "holes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "par": {"type": "integer"},
                    "stroke_index": {"type": "integer"},
                },
                "required": ["number", "par", "stroke_index"],
                "additionalProperties": False,
            },
        },
        "tees": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "color": {"type": "string"},
                    "gender": {"type": "string", "enum": ["Herren", "Damen", "unbekannt"]},
                    "course_rating": {"type": "number"},
                    "slope": {"type": "integer"},
                },
                "required": ["color", "gender", "course_rating", "slope"],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["club_name", "holes", "tees", "warnings"],
    "additionalProperties": False,
}


class ScanError(Exception):
    """Fehler mit einer Meldung, die man dem Nutzer zeigen kann."""


def enabled():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def ask_claude(image_bytes, media_type):
    """Schickt das Foto an Claude und gibt das Roh-Ergebnis (dict nach SCHEMA) zurück."""
    import anthropic  # erst hier, damit die App auch ohne das Paket startet

    client = anthropic.Anthropic(timeout=90.0, max_retries=1)
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            # Bei einer (unwahrscheinlichen) Ablehnung übernimmt automatisch ein anderes Modell
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }],
        )
    except anthropic.AuthenticationError as e:
        raise ScanError("Der API-Schlüssel für die Bilderkennung ist ungültig.") from e
    except anthropic.RateLimitError as e:
        raise ScanError("Bilderkennung gerade ausgelastet – bitte gleich nochmal versuchen.") from e
    except anthropic.APITimeoutError as e:
        raise ScanError("Die Bilderkennung hat zu lange gebraucht – bitte nochmal versuchen.") from e
    except anthropic.APIStatusError as e:
        raise ScanError(f"Bilderkennung fehlgeschlagen (Fehler {e.status_code}).") from e
    except anthropic.APIConnectionError as e:
        raise ScanError("Bilderkennung nicht erreichbar – Internetverbindung des Servers prüfen.") from e

    if response.stop_reason == "refusal":
        raise ScanError("Das Foto konnte nicht ausgewertet werden.")
    if response.stop_reason == "max_tokens":
        raise ScanError("Die Auswertung war unvollständig – bitte nochmal versuchen.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except ValueError as e:
        raise ScanError("Die Antwort der Bilderkennung war unlesbar.") from e


def normalize(raw):
    """Prüft das Ergebnis und bringt es in das Format des Platz-Formulars.

    Rückgabe: {name, pars, stroke_index, tees: [{name, course_rating, slope}], warnings}
    pars / stroke_index sind None, wenn sie nicht vollständig und plausibel gelesen wurden.
    """
    warnings = [str(w) for w in raw.get("warnings") or [] if str(w).strip()]
    holes = sorted(
        (h for h in raw.get("holes") or [] if isinstance(h, dict) and isinstance(h.get("number"), int)),
        key=lambda h: h["number"],
    )
    pars = stroke_index = None
    if len(holes) in (9, 18) and [h["number"] for h in holes] == list(range(1, len(holes) + 1)):
        candidate = [h.get("par") for h in holes]
        if all(isinstance(p, int) and 3 <= p <= 6 for p in candidate):
            pars = candidate
        else:
            warnings.append("Par nicht für alle Löcher lesbar – bitte von Hand ergänzen.")
        si = [h.get("stroke_index") for h in holes]
        n = len(holes)
        if all(isinstance(v, int) and 1 <= v <= 18 for v in si) and len(set(si)) == n:
            stroke_index = si
        else:
            warnings.append("Handicap-Reihenfolge nicht vollständig lesbar – bitte prüfen.")
    else:
        warnings.append(f"{len(holes)} Löcher erkannt – erwartet werden 9 oder 18.")

    tees = []
    for t in raw.get("tees") or []:
        if not isinstance(t, dict):
            continue
        cr, slope = t.get("course_rating"), t.get("slope")
        if not (isinstance(cr, (int, float)) and 20 <= cr <= 90 and isinstance(slope, int) and 55 <= slope <= 155):
            continue
        gender = t.get("gender") if t.get("gender") in ("Herren", "Damen") else ""
        name = " ".join(f"{t.get('color', '')} {gender}".split()) or "Abschlag"
        tees.append({"name": name, "course_rating": round(float(cr), 1), "slope": slope})

    return {
        "name": " ".join(str(raw.get("club_name") or "").split()),
        "pars": pars,
        "stroke_index": stroke_index,
        "tees": tees,
        "warnings": warnings,
    }
