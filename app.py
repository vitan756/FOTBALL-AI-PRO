import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

API_BASE = "https://v3.football.api-sports.io"
TIMEZONE = "Europe/Bucharest"

st.set_page_config(page_title="FOOTBALL AI PRO", page_icon="⚽", layout="wide")

def api_get(endpoint: str, params: Optional[dict] = None, api_key: str = "") -> dict:
    if not api_key.strip():
        raise ValueError("Introdu cheia API-FOOTBALL în bara laterală.")
    headers = {"x-apisports-key": api_key.strip()}
    try:
        r = requests.get(f"{API_BASE}/{endpoint.lstrip('/')}", headers=headers,
                         params=params or {}, timeout=25)
        if r.status_code == 401:
            raise ValueError("Cheie API invalidă sau neacceptată (401). Verifică cheia în Dashboard.")
        if r.status_code == 403:
            raise ValueError("Acces refuzat (403). Planul API poate să nu includă acest endpoint.")
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise ValueError(f"API-FOOTBALL: {data['errors']}")
        return data
    except requests.RequestException as e:
        raise ValueError(f"Nu am putut contacta API-FOOTBALL: {e}")

def response_rows(data: dict) -> list:
    return data.get("response") or []

def safe_float(v, default=None):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default

def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def goal_matrix(lh: float, la: float, max_goals: int = 8):
    return [[poisson_pmf(i, lh) * poisson_pmf(j, la)
             for j in range(max_goals + 1)] for i in range(max_goals + 1)]

def probabilities(lh: float, la: float) -> dict:
    m = goal_matrix(lh, la)
    home = draw = away = over15 = over25 = over35 = btts = 0.0
    scores = []
    for h in range(len(m)):
        for a in range(len(m[h])):
            p = m[h][a]
            if h > a: home += p
            elif h == a: draw += p
            else: away += p
            if h + a >= 2: over15 += p
            if h + a >= 3: over25 += p
            if h + a >= 4: over35 += p
            if h > 0 and a > 0: btts += p
            scores.append((p, h, a))
    total = home + draw + away
    if total:
        home, draw, away = home/total, draw/total, away/total
    return {
        "1": home, "X": draw, "2": away, "GG": btts,
        "Peste 1.5": over15, "Peste 2.5": over25, "Peste 3.5": over35,
        "Sub 2.5": 1-over25, "Scoruri": sorted(scores, reverse=True)[:5]
    }

def match_goals(row: dict) -> Tuple[Optional[int], Optional[int]]:
    goals = row.get("goals") or {}
    return goals.get("home"), goals.get("away")

def finished_rows(rows: list) -> list:
    out = []
    for x in rows:
        status = ((x.get("fixture") or {}).get("status") or {}).get("short")
        gh, ga = match_goals(x)
        if status in ("FT", "AET", "PEN") and gh is not None and ga is not None:
            out.append(x)
    return out

def form_stats(rows: list, team_id: int, venue: Optional[str] = None) -> dict:
    rows = finished_rows(rows)
    selected = []
    for r in rows:
        teams = r.get("teams") or {}
        is_home = (teams.get("home") or {}).get("id") == team_id
        if venue == "home" and not is_home: continue
        if venue == "away" and is_home: continue
        selected.append(r)
    if not selected:
        return {"played": 0, "gf": 1.25, "ga": 1.25, "w": 0, "d": 0, "l": 0, "corners": None}
    gf = ga = w = d = l = 0
    for r in selected:
        gh, ga_ = match_goals(r)
        is_home = (r.get("teams", {}).get("home", {}).get("id") == team_id)
        scored, conceded = (gh, ga_) if is_home else (ga_, gh)
        gf += scored; ga += conceded
        if scored > conceded: w += 1
        elif scored == conceded: d += 1
        else: l += 1
    n = len(selected)
    return {"played": n, "gf": gf/n, "ga": ga/n, "w": w, "d": d, "l": l, "corners": None}

def fixture_label(f: dict) -> str:
    teams = f.get("teams") or {}
    home = (teams.get("home") or {}).get("name", "?")
    away = (teams.get("away") or {}).get("name", "?")
    fx = f.get("fixture") or {}
    dt = fx.get("date", "")
    league = (f.get("league") or {}).get("name", "")
    return f"{home} – {away} | {league} | {dt[:16].replace('T',' ')}"

def percent(v):
    return f"{v*100:.1f}%"

st.title("⚽ FOOTBALL AI PRO")
st.caption("Analiză statistică asistată de API-FOOTBALL. Probabilitățile sunt estimări, nu garanții.")

with st.sidebar:
    st.header("Conectare API")
    api_key = st.text_input("API-FOOTBALL Key", type="password",
                            value=st.session_state.get("api_key", ""),
                            help="Cheia rămâne în sesiunea curentă. Nu o publica și nu o trimite nimănui.")
    if api_key:
        st.session_state["api_key"] = api_key
    st.caption("API: v3.football.api-sports.io")
    st.divider()
    st.subheader("Data meciurilor")
    match_date = st.date_input("Alege data", value=date.today())
    st.caption("Fus orar: Europe/Bucharest")

tab1, tab2, tab3, tab4 = st.tabs(["Meciuri automate", "Analiză manuală", "Validare istorică", "Despre model"])

with tab1:
    st.subheader("Meciuri preluate automat")
    c1, c2 = st.columns([1, 3])
    with c1:
        load_matches = st.button("Încarcă meciurile", type="primary", use_container_width=True)
    if load_matches:
        try:
            data = api_get("fixtures", {"date": match_date.isoformat(), "timezone": TIMEZONE}, api_key)
            rows = response_rows(data)
            st.session_state["fixtures"] = rows
            st.session_state["fixture_date"] = match_date.isoformat()
            st.success(f"Am primit {len(rows)} meciuri de la API.")
            if not rows:
                st.info("API-ul nu a returnat meciuri pentru data aleasă. Încearcă altă dată sau verifică planul API.")
        except Exception as e:
            st.error(str(e))
    rows = st.session_state.get("fixtures", [])
    if rows:
        labels = [fixture_label(f) for f in rows]
        idx = st.selectbox("Alege meciul", range(len(rows)), format_func=lambda i: labels[i])
        selected = rows[idx]
        if st.button("Analizează meciul selectat", type="primary"):
            try:
                fx = selected.get("fixture", {})
                lg = selected.get("league", {})
                teams = selected.get("teams", {})
                home = teams.get("home", {})
                away = teams.get("away", {})
                league_id = lg.get("id")
                season = lg.get("season")
                home_id, away_id = home.get("id"), away.get("id")
                # Last 10 completed matches for both teams; limited calls.
                hdata = api_get("fixtures", {"team": home_id, "last": 10, "status": "FT", "timezone": TIMEZONE}, api_key)
                adata = api_get("fixtures", {"team": away_id, "last": 10, "status": "FT", "timezone": TIMEZONE}, api_key)
                hrows, arows = response_rows(hdata), response_rows(adata)
                hs = form_stats(hrows, home_id)
                ass = form_stats(arows, away_id)
                hhome = form_stats(hrows, home_id, "home")
                aaway = form_stats(arows, away_id, "away")
                # Blend overall recent form with venue-specific form when enough matches exist.
                hgf = 0.65*hs["gf"] + 0.35*(hhome["gf"] if hhome["played"] else hs["gf"])
                hga = 0.65*hs["ga"] + 0.35*(hhome["ga"] if hhome["played"] else hs["ga"])
                agf = 0.65*ass["gf"] + 0.35*(aaway["gf"] if aaway["played"] else ass["gf"])
                aga = 0.65*ass["ga"] + 0.35*(aaway["ga"] if aaway["played"] else ass["ga"])
                # Use current league goal averages if available, otherwise conservative fallback.
                league_avg_home, league_avg_away = 1.45, 1.15
                try:
                    ldata = api_get("leagues", {"id": league_id, "season": season}, api_key)
                    cov = (response_rows(ldata)[0].get("seasons") or []) if response_rows(ldata) else []
                    # League averages are not reliably exposed by all competitions; keep transparent fallback.
                except Exception:
                    pass
                # Attack/defence blend, shrunk toward league scoring baseline.
                lam_h = max(0.15, min(4.0, 0.55*((hgf + aga)/2) + 0.45*league_avg_home))
                lam_a = max(0.15, min(4.0, 0.55*((agf + hga)/2) + 0.45*league_avg_away))
                probs = probabilities(lam_h, lam_a)
                # Optional independent API predictions/injuries/odds endpoints.
                api_prediction = None
                injuries = []
                odds = []
                try:
                    pdat = api_get("predictions", {"fixture": fx.get("id")}, api_key)
                    api_prediction = response_rows(pdat)[0] if response_rows(pdat) else None
                except Exception as e:
                    st.warning(f"Predicția furnizată de API nu este disponibilă: {e}")
                try:
                    idat = api_get("injuries", {"fixture": fx.get("id")}, api_key)
                    injuries = response_rows(idat)
                except Exception:
                    injuries = []
                try:
                    odat = api_get("odds", {"fixture": fx.get("id"), "page": 1}, api_key)
                    odds = response_rows(odat)
                except Exception:
                    odds = []
                st.session_state["analysis"] = {
                    "home": home.get("name"), "away": away.get("name"), "league": lg.get("name"),
                    "season": season, "lam_h": lam_h, "lam_a": lam_a, "probs": probs,
                    "hs": hs, "ass": ass, "api_prediction": api_prediction,
                    "injuries": injuries, "odds": odds, "fixture_id": fx.get("id")
                }
            except Exception as e:
                st.error(f"Nu am putut calcula analiza: {e}")
    a = st.session_state.get("analysis")
    if a:
        st.divider()
        st.header(f"{a['home']} – {a['away']}")
        st.caption(f"{a['league']} | Sezon API: {a['season']} | ID meci: {a['fixture_id']}")
        k1, k2, k3 = st.columns(3)
        k1.metric("Goluri estimate gazde", f"{a['lam_h']:.2f}")
        k2.metric("Goluri estimate oaspeți", f"{a['lam_a']:.2f}")
        k3.metric("Total goluri estimate", f"{a['lam_h']+a['lam_a']:.2f}")
        p = a["probs"]
        st.subheader("Probabilități model Poisson")
        cols = st.columns(3)
        for col, key, label in zip(cols, ["1","X","2"], ["Victorie gazde","Egal","Victorie oaspeți"]):
            col.metric(label, percent(p[key]))
        cols = st.columns(5)
        for col, key in zip(cols, ["GG","Peste 1.5","Peste 2.5","Peste 3.5","Sub 2.5"]):
            col.metric(key, percent(p[key]))
        st.subheader("Scoruri exacte cu probabilitate estimată")
        st.table(pd.DataFrame([{"Scor": f"{h}-{g}", "Probabilitate": percent(prob)} for prob,h,g in p["Scoruri"]]))
        st.subheader("Forma ultimelor meciuri")
        f1, f2 = st.columns(2)
        f1.write(f"**{a['home']}** — {a['hs']['played']} meciuri: {a['hs']['w']}V / {a['hs']['d']}E / {a['hs']['l']}Î; goluri marcate {a['hs']['gf']:.2f}/meci, primite {a['hs']['ga']:.2f}/meci.")
        f2.write(f"**{a['away']}** — {a['ass']['played']} meciuri: {a['ass']['w']}V / {a['ass']['d']}E / {a['ass']['l']}Î; goluri marcate {a['ass']['gf']:.2f}/meci, primite {a['ass']['ga']:.2f}/meci.")
        if a["injuries"]:
            st.subheader("Accidentări / suspendări returnate de API")
            inj_rows = []
            for x in a["injuries"]:
                player = x.get("player", {})
                team = x.get("team", {})
                inj_rows.append({"Echipă": team.get("name"), "Jucător": player.get("name"),
                                 "Tip": player.get("type"), "Motiv": player.get("reason")})
            st.dataframe(pd.DataFrame(inj_rows), use_container_width=True)
        else:
            st.info("API-ul nu a returnat accidentări pentru acest meci. Absența datelor nu înseamnă că echipele nu au accidentați.")
        if a["api_prediction"]:
            st.subheader("Predicția separată a API-ului")
            pred = a["api_prediction"].get("predictions", {})
            st.write(pred.get("advice", "API-ul nu a furnizat un sfat textual."))
            st.json(pred)
        else:
            st.caption("Predicția separată API nu a fost disponibilă pentru acest meci/plan.")
        if a["odds"]:
            st.subheader("Cote returnate de API")
            st.caption("Disponibilitatea cotelor depinde de competiție, bookmaker și abonament.")
            st.json(a["odds"][:2])
        st.warning("Modelul propriu este o estimare Poisson simplificată, bazată pe ultimele rezultate. Nu este încă validat statistic pe toate ligile și nu reprezintă garanție de câștig.")

with tab2:
    st.subheader("Analiză manuală")
    st.write("Folosește această secțiune doar dacă nu există date API pentru meci.")
    c1, c2 = st.columns(2)
    with c1:
        home_name = st.text_input("Echipa gazdă", "Gazde")
        home_scored = st.number_input("Goluri marcate / meci – gazde", 0.0, 5.0, 1.5, 0.05)
        home_conceded = st.number_input("Goluri primite / meci – gazde", 0.0, 5.0, 1.0, 0.05)
    with c2:
        away_name = st.text_input("Echipa oaspete", "Oaspeți")
        away_scored = st.number_input("Goluri marcate / meci – oaspeți", 0.0, 5.0, 1.2, 0.05)
        away_conceded = st.number_input("Goluri primite / meci – oaspeți", 0.0, 5.0, 1.3, 0.05)
    if st.button("Calculează analiza manuală"):
        lh = max(.1, (home_scored + away_conceded)/2)
        la = max(.1, (away_scored + home_conceded)/2)
        pp = probabilities(lh, la)
        st.write(f"**{home_name} – {away_name}** | goluri estimate: {lh:.2f} – {la:.2f}")
        st.json({k: percent(v) for k,v in pp.items() if k != "Scoruri"})
        st.table(pd.DataFrame([{"Scor": f"{h}-{g}", "Probabilitate": percent(prob)} for prob,h,g in pp["Scoruri"]]))

with tab3:
    st.subheader("Validare istorică – test pe sezoane anterioare")
    st.write("Alege manual liga și sezonul. Aplicația descarcă meciurile încheiate și testează un model de bază pe o împărțire cronologică 70% antrenare / 30% test. Este o verificare orientativă, nu o certificare profesională.")
    c1, c2 = st.columns(2)
    with c1:
        league_id = st.number_input("ID ligă API-FOOTBALL", min_value=1, value=39, step=1)
    with c2:
        season_year = st.number_input("Sezon (an de început)", min_value=2010, max_value=date.today().year, value=date.today().year-1, step=1)
    if st.button("Rulează test istoric"):
        try:
            hist = []
            for page in range(1, 4):
                d = api_get("fixtures", {"league": int(league_id), "season": int(season_year),
                                         "status": "FT", "page": page, "timezone": TIMEZONE}, api_key)
                hist.extend(response_rows(d))
                paging = d.get("paging") or {}
                if page >= paging.get("total", 1):
                    break
            hist = finished_rows(hist)
            hist.sort(key=lambda x: (x.get("fixture", {}).get("date") or ""))
            if len(hist) < 30:
                st.warning(f"Am găsit doar {len(hist)} meciuri. Pentru un test mai util sunt necesare cel puțin 30; verifică liga, sezonul și acoperirea planului API.")
            else:
                split = int(len(hist)*0.7)
                train, test = hist[:split], hist[split:]
                home_g = [match_goals(x)[0] for x in train]
                away_g = [match_goals(x)[1] for x in train]
                avg_h = sum(home_g)/len(home_g)
                avg_a = sum(away_g)/len(away_g)
                # Simple baseline: constant league averages; chronological holdout.
                brier_1x2 = 0.0
                exact = 0
                evaluated = 0
                for x in test:
                    gh, ga = match_goals(x)
                    pr = probabilities(avg_h, avg_a)
                    actual = [1,0,0] if gh>ga else ([0,1,0] if gh==ga else [0,0,1])
                    brier_1x2 += sum((pr[k]-actual[i])**2 for i,k in enumerate(["1","X","2"]))
                    pred = max(["1","X","2"], key=lambda k: pr[k])
                    actual_label = "1" if gh>ga else ("X" if gh==ga else "2")
                    exact += int(pred == actual_label)
                    evaluated += 1
                st.success(f"Test finalizat: {len(train)} meciuri pentru estimarea mediilor și {evaluated} meciuri de test.")
                m1,m2,m3 = st.columns(3)
                m1.metric("Brier score 1X2", f"{brier_1x2/evaluated:.4f}")
                m2.metric("Acuratețe semn 1X2", percent(exact/evaluated))
                m3.metric("Medie goluri gazde/oaspeți", f"{avg_h:.2f} / {avg_a:.2f}")
                st.caption("Brier score mai mic este mai bun. Acesta este un baseline simplu, nu backtestul modelului complet bazat pe forma fiecărei echipe.")
        except Exception as e:
            st.error(str(e))

with tab4:
    st.subheader("Ce face și ce nu face această versiune")
    st.markdown("""
- **Automat:** preia meciurile pentru data aleasă prin API-FOOTBALL.
- **Formă:** folosește ultimele 10 meciuri încheiate pentru fiecare echipă, dacă API-ul le oferă.
- **Model:** calculează probabilități 1X2, GG/NG, peste/sub goluri și scoruri probabile cu distribuția Poisson.
- **Context opțional:** încearcă să preia predicția API, absențele și cotele; disponibilitatea depinde de plan și de competiție.
- **Validare:** oferă un test cronologic simplu pe sezon istoric.
- **Limite:** xG și mediile de cornere nu sunt inventate; nu sunt încă integrate în modelul propriu. Pentru cornere și xG trebuie confirmată acoperirea exactă a sursei de date.
- **Cheia API:** se introduce în bara laterală și nu trebuie publicată în GitHub.
    """)
    st.info("Nu există predicții sigure. Folosește rezultatele doar ca analiză statistică și verifică datele înainte de orice decizie.")
