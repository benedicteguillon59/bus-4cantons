#!/usr/bin/env python3
"""Télécharge le GTFS régional (Hauts-de-France, Nord, périmètre 2) et produit data.json
pour les lignes 854 et 870 : Bouvines Église / Tournebride <-> Villeneuve d'Ascq 4 Cantons.

Usage : python build_data.py
Sans dépendance externe (bibliothèque standard uniquement).
"""
import csv
import io
import re
import json
import sys
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

GTFS_URL = "https://geocatalogue.hautsdefrance.fr/gtfs/RHDF_GTFS_COM_SCO_59_P2.zip"
ROUTES = {"854", "870"}

# Arrêts (stop_id du GTFS) -> lieu affiché
PLACES = {
    "BV": {"name": "Bouvines Église", "stops": {"59:00102", "59:02521"}},
    "TB": {"name": "Tournebride", "stops": {"59:00538", "59:02957", "59:00533", "59:02952"}},
}
CQ_STOPS = {"59:00642", "59:03061", "59:03089"}  # VILLENEUVE D ASCQ - 4 Cantons Stade P. Mauroy


def read_csv(z, name):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))


def pretty_stop(name):
    """« MOUCHIN - Place » -> « Mouchin - Place » ; le terminus 4 Cantons devient « 4 Cantons »."""
    if "4 Cantons" in name:
        return "4 Cantons"
    town, _, rest = name.partition(" - ")
    small = {"En", "Le", "La", "Les", "De", "Du", "Sur", "Lez", "Sous"}
    words = [w if w in small and i else w for i, w in enumerate(town.title().split())]
    words = [w.lower() if (i and w in small) else w for i, w in enumerate(words)]
    town = re.sub(r"\bD (?=[A-Z])", "d'", " ".join(words)).replace("Melantois", "Mélantois")
    return f"{town} - {rest}" if rest else town


def hms(s):
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + int(sec)


def t_of(row, prefer):
    order = ("departure_time", "arrival_time") if prefer == "dep" else ("arrival_time", "departure_time")
    for k in order:
        if row[k].strip():
            return hms(row[k])
    return None


def expand_services(z, needed, first_day):
    """service_id -> liste triée de dates AAAAMMJJ (calendar.txt + exceptions calendar_dates.txt)."""
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    dates = defaultdict(set)
    for r in read_csv(z, "calendar.txt"):
        if r["service_id"] not in needed:
            continue
        d = datetime.strptime(r["start_date"], "%Y%m%d").date()
        end = datetime.strptime(r["end_date"], "%Y%m%d").date()
        while d <= end:
            if d >= first_day and r[days[d.weekday()]] == "1":
                dates[r["service_id"]].add(int(d.strftime("%Y%m%d")))
            d += timedelta(days=1)
    for r in read_csv(z, "calendar_dates.txt"):
        if r["service_id"] not in needed:
            continue
        v = int(r["date"])
        if r["exception_type"] == "1":
            dates[r["service_id"]].add(v)
        else:
            dates[r["service_id"]].discard(v)
    return {k: sorted(v) for k, v in dates.items()}


CAL_URL = "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-calendrier-scolaire/records"


def school_holidays(today):
    """Vacances scolaires de la zone B (académie de Lille) : [{n, from, to}], `to` = jour de reprise."""
    q = urllib.parse.urlencode({
        "where": 'location="Lille" AND end_date >= "%s"' % today.isoformat(),
        "select": "description,start_date,end_date",
        "order_by": "start_date",
        "limit": "30",
    })
    try:
        req = urllib.request.Request(CAL_URL + "?" + q, headers={"User-Agent": "bus-4cantons/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.load(r)["results"]
    except Exception as e:  # le calendrier est facultatif : l'appli fonctionne sans
        print("Calendrier scolaire indisponible :", e, file=sys.stderr)
        return []
    best = {}
    for r in rows:
        a = (datetime.fromisoformat(r["start_date"]) + timedelta(hours=2)).date()   # minuit heure de Paris (UTC+1/+2)
        b = (datetime.fromisoformat(r["end_date"]) + timedelta(hours=2)).date()
        name = r["description"].strip()
        if "Pont" in name:
            continue
        k = (name, a)
        if k not in best or b > best[k]:      # doublons : on garde la reprise la plus tardive
            best[k] = b
    out = [{"n": n, "from": a.isoformat(), "to": b.isoformat()} for (n, a), b in best.items()]
    return sorted(out, key=lambda h: h["from"])[:6]


def main():
    print("Téléchargement du GTFS régional…", file=sys.stderr)
    req = urllib.request.Request(GTFS_URL, headers={"User-Agent": "bus-4cantons/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))

    place_of = {s: p for p, v in PLACES.items() for s in v["stops"]}
    watch = set(place_of) | CQ_STOPS

    trips = {r["trip_id"]: r for r in read_csv(z, "trips.txt") if r["route_id"] in ROUTES}
    stop_name = {r["stop_id"]: r["stop_name"] for r in read_csv(z, "stops.txt")}
    rows = defaultdict(list)
    last = {}  # trip_id -> (dernier stop_sequence, stop_id) = terminus
    for r in read_csv(z, "stop_times.txt"):
        if r["trip_id"] not in trips:
            continue
        seq = int(r["stop_sequence"])
        if r["trip_id"] not in last or seq > last[r["trip_id"]][0]:
            last[r["trip_id"]] = (seq, r["stop_id"])
        if r["stop_id"] in watch:
            rows[r["trip_id"]].append(r)

    items = {"to": [], "from": []}
    for tid, lst in rows.items():
        lst.sort(key=lambda r: int(r["stop_sequence"]))
        loc = [r for r in lst if r["stop_id"] in place_of]
        cq = [r for r in lst if r["stop_id"] in CQ_STOPS]
        if not loc or not cq:
            continue
        t = trips[tid]
        term = pretty_stop(stop_name.get(last[tid][1], t["trip_headsign"]))
        base = {"t": tid, "r": t["route_id"], "s": t["service_id"], "h": t["trip_headsign"], "e": term}
        cq_seq = int(cq[0]["stop_sequence"])
        before = [r for r in loc if int(r["stop_sequence"]) < cq_seq]   # on monte avant 4 Cantons
        after = [r for r in loc if int(r["stop_sequence"]) > cq_seq]    # on descend après 4 Cantons
        # vers 4 Cantons : une ligne par lieu de montée
        arr = t_of(cq[0], "arr")
        for r in before:
            d = t_of(r, "dep")
            if d is None or arr is None:
                continue
            items["to"].append({**base, "p": place_of[r["stop_id"]], "d": d, "dst": [["4C", arr]]})
        # depuis 4 Cantons : une ligne par course, avec l'heure d'arrivée à chaque lieu
        if after:
            d = t_of(cq[-1], "dep")
            dst = [[place_of[r["stop_id"]], t_of(r, "arr")] for r in after if t_of(r, "arr") is not None]
            if d is not None and dst:
                items["from"].append({**base, "p": "4C", "d": d, "dst": dst})
    for k in items:
        items[k].sort(key=lambda i: (i["s"], i["d"]))

    needed = {i["s"] for k in items for i in items[k]}
    services = expand_services(z, needed, date.today() - timedelta(days=2))
    all_dates = [d for v in services.values() for d in v]

    used = {i["r"] for k in items for i in items[k]}
    routes = {}
    for r in read_csv(z, "routes.txt"):
        if r["route_id"] in used:
            routes[r["route_id"]] = {
                "n": r["route_short_name"],
                "c": r.get("route_color") or "0A5A9C",
                "t": r.get("route_text_color") or "FFFFFF",
                "l": r["route_long_name"],
            }

    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "validFrom": min(all_dates),
        "validTo": max(all_dates),
        "places": {**{k: v["name"] for k, v in PLACES.items()}, "4C": "4 Cantons"},
        "routes": routes,
        "items": items,
        "services": services,
        "holidays": school_holidays(date.today()),
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK : {len(items['to'])} départs vers 4 Cantons, {len(items['from'])} depuis 4 Cantons, "
          f"lignes {sorted(used)}, valable {out['validFrom']} → {out['validTo']}", file=sys.stderr)


if __name__ == "__main__":
    main()
