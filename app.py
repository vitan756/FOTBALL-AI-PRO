import math
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

API_BASE = "https://v3.football.api-sports.io"
FINISHED = {"FT", "AET", "PEN"}

st.set_page_config(page_title="FOOTBALL AI PRO", page_icon="⚽", layout="wide")

st.title("⚽ FOOTBALL AI PRO")
st.caption("Analiză statistică orientativă pe baza meciurilor disponibile în API-FOOTBALL.")

with st.sidebar:
    st.header("Conectare API")
    api_key = st.text_input(
        "API-FOOTBALL API Key",
        type="password",
        help="Cheia este folosită doar în sesiunea curentă. Nu o publica în GitHub."
    ).strip()
    st.caption("Cheia nu este salvată în fișierul aplicației.")

def api_get(endpoint, params, key):
    """Call API-Football and return parsed JSON with actionable diagnostics."""
    if not key:
        raise RuntimeError("Lipsește cheia API. Introdu cheia în bara laterală.")
    url = f"{API_BASE}/{endpoint.lstrip('/')}"
    try:
        response = requests.get(
            url,
            headers={"x-apisports-key": key},
            params=params,
            timeout=25,
        )
    except requests.Timeout:
        raise RuntimeError("API-FOOTBALL nu a răspuns în 25 secunde. Încearcă din nou.")
    except requests.RequestException as exc:
        raise RuntimeError(f"Eroare de conexiune: {exc}")

    try:
        payload = response.json()
    except ValueError:
        excerpt = (response.text or "")[:300]
        raise RuntimeError(
            f"API a returnat un răspuns care nu este JSON (HTTP {response.status_code}): {excerpt}"
        )

    if response.status_code != 200:
        errors = payload.get("errors", payload) if isinstance(payload, dict) else payload
        raise RuntimeError(f"API-FOOTBALL HTTP {response.status_code}: {errors}")

    errors = payload.get("errors") if isinstance(payload, dict) else None
    if errors:
        raise RuntimeError(f"API-FOOTBALL a raportat: {errors}")

    if not isinstance(payload, dict) or "response" not in payload:
        raise RuntimeError("Răspuns API neașteptat: lipsește câmpul 'response'.")

    return payload

def poisson_pmf(k, lam):
    lam = max(0.05, float(lam))
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def poisson_markets(home_lam, away_lam, max_goals=10):
    scores = []
    p_home = p_draw = p_away = 0.0
    p_btts = 0.0
    totals = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    for h in range(max_goals + 1):
        ph = poisson_pmf(h, home_lam)
        for a in range(max_goals + 1):
            p = ph * poisson_pmf(a, away_lam)
            scores.append((h, a, p))
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
            if h > 0 and a > 0:
                p_btts += p
            for line in totals:
                if h + a > line:
                    totals[line] += p
    norm = p_home + p_draw + p_away
    if norm:
        p_home, p_draw, p_away = p_home/norm, p_draw/norm, p_away/norm
    return {
        "1": p_home, "X": p_draw, "2": p_away,
        "GG": p_btts, "NG": 1-p_btts,
        "over": totals,
        "scores": sorted(scores, key=lambda x: x[2], reverse=True)[:5],
    }

def finished_fixture_rows(payload):
    rows = payload.get("response", [])
    return [
        x for x in rows
        if x.get("fixture", {}).get("status", {}).get("short") in FINISHED
        and x.get("goals", {}).get("home") is not None
        and x.get("goals", {}).get("away") is not None
    ]

def team_recent(team_id, key):
    payload = api_get("fixtures", {"team": team_id, "last": 10}, key)
    rows = finished_fixture_rows(payload)
    if not rows:
        raise RuntimeError(
            f"API nu a returnat meciuri încheiate pentru echipa cu ID {team_id}. "
            "Verifică accesul planului API la competiție și sezon."
        )
    scored, conceded = [], []
    home_scored, home_conceded, away_scored, away_conceded = [], [], [], []
    for item in rows:
        fixture = item["fixture"]
        teams = item["teams"]
        goals = item["goals"]
        is_home = teams["home"]["id"] == team_id
        gf = goals["home"] if is_home else goals["away"]
        ga = goals["away"] if is_home else goals["home"]
        scored.append(float(gf))
        conceded.append(float(ga))
        if is_home:
            home_scored.append(float(gf)); home_conceded.append(float(ga))
        else:
            away_scored.append(float(gf)); away_conceded.append(float(ga))

    def avg(values, fallback):
        return sum(values)/len(values) if values else fallback

    return {
        "n": len(rows),
        "gf": avg(scored, 1.2),
        "ga": avg(conceded, 1.2),
        "home_gf": avg(home_scored, avg(scored, 1.2)),
        "home_ga": avg(home_conceded, avg(conceded, 1.2)),
        "away_gf": avg(away_scored, avg(scored, 1.2)),
        "away_ga": avg(away_conceded, avg(conceded, 1.2)),
    }

def percent(x):
    return f"{100*x:.1f}%"

tab_auto, tab_manual, tab_history = st.tabs(
    ["Analiză API", "Analiză manuală", "Validare istorică"]
)

with tab_auto:
    st.subheader("Meciuri din API-FOOTBALL")
    chosen_date = st.date_input("Data meciurilor", value=date.today())
    if st.button("Încarcă meciurile", type="primary"):
        try:
            data = api_get("fixtures", {"date": chosen_date.isoformat(), "timezone": "Europe/Bucharest"}, api_key)
            fixtures = data["response"]
            st.session_state["fixtures"] = fixtures
            st.session_state["fixtures_date"] = chosen_date.isoformat()
            st.success(f"Au fost găsite {len(fixtures)} meciuri.")
        except Exception as exc:
            st.error(f"Nu am putut încărca meciurile: {exc}")

    fixtures = st.session_state.get("fixtures", [])
    if fixtures:
        options = []
        for f in fixtures:
            h = f.get("teams", {}).get("home", {}).get("name", "Gazde")
            a = f.get("teams", {}).get("away", {}).get("name", "Oaspeți")
            league = f.get("league", {}).get("name", "Competiție")
            kickoff = f.get("fixture", {}).get("date", "")
            fid = f.get("fixture", {}).get("id")
            options.append((f"{h} – {a} | {league} | {kickoff[:16]}", fid))
        labels = [x[0] for x in options]
        selected_label = st.selectbox("Selectează meciul", labels)
        selected_id = dict(options)[selected_label]
        selected = next((f for f in fixtures if f.get("fixture", {}).get("id") == selected_id), None)

        if st.button("Analizează meciul selectat", type="primary"):
            try:
                if not selected:
                    raise RuntimeError("Meciul selectat nu mai este disponibil în listă.")
                home = selected["teams"]["home"]
                away = selected["teams"]["away"]
                home_id, away_id = home["id"], away["id"]
                with st.spinner("Preiau ultimele 10 meciuri ale ambelor echipe..."):
                    hstats = team_recent(home_id, api_key)
                    astats = team_recent(away_id, api_key)

                # Venue-aware blend: overall form + venue-specific form.
                home_attack = 0.65*hstats["home_gf"] + 0.35*hstats["gf"]
                away_defence = 0.65*astats["away_ga"] + 0.35*astats["ga"]
                away_attack = 0.65*astats["away_gf"] + 0.35*astats["gf"]
                home_defence = 0.65*hstats["home_ga"] + 0.35*hstats["ga"]
                league_home_baseline, league_away_baseline = 1.45, 1.15
                home_lam = max(0.15, (home_attack * away_defence / 1.25 + league_home_baseline) / 2)
                away_lam = max(0.15, (away_attack * home_defence / 1.25 + league_away_baseline) / 2)
                probs = poisson_markets(home_lam, away_lam)

                st.success("Analiza a fost calculată.")
                st.caption(
                    f"Bază de date: ultimele {hstats['n']} meciuri pentru {home['name']} "
                    f"și ultimele {astats['n']} pentru {away['name']}."
                )
                c1, c2, c3 = st.columns(3)
                c1.metric("1 – Gazde", percent(probs["1"]))
                c2.metric("X – Egal", percent(probs["X"]))
                c3.metric("2 – Oaspeți", percent(probs["2"]))
                c4, c5 = st.columns(2)
                c4.metric("GG", percent(probs["GG"]))
                c5.metric("NG", percent(probs["NG"]))
                st.markdown("**Over / Under**")
                for line, p_over in probs["over"].items():
                    st.write(f"Over {line}: **{percent(p_over)}**  |  Under {line}: **{percent(1-p_over)}**")
                st.markdown("**Scoruri exacte cele mai probabile**")
                for h, a, p in probs["scores"]:
                    st.write(f"{h}–{a}: {percent(p)}")
                st.info(
                    f"Goluri estimate: {home['name']} {home_lam:.2f} – "
                    f"{away_lam:.2f} {away['name']}."
                )
                st.warning(
                    "Estimare Poisson simplificată pe rezultate recente. Nu include xG, "
                    "accidentări sau cote dacă acestea nu sunt furnizate separat de API. "
                    "Nu reprezintă garanție de rezultat."
                )
            except Exception as exc:
                st.error(f"Analiza nu a putut fi calculată: {exc}")
                st.caption("Mesajul de mai sus este eroarea detaliată returnată de aplicație/API.")

with tab_manual:
    st.subheader("Analiză manuală")
    col1, col2 = st.columns(2)
    with col1:
        home_name = st.text_input("Echipa gazdă", "Gazde")
        home_avg = st.number_input("Goluri marcate acasă / meci", 0.1, 5.0, 1.5, 0.1)
    with col2:
        away_name = st.text_input("Echipa oaspete", "Oaspeți")
        away_avg = st.number_input("Goluri marcate în deplasare / meci", 0.1, 5.0, 1.1, 0.1)
    if st.button("Calculează manual"):
        p = poisson_markets(home_avg, away_avg)
        st.write(f"**{home_name}** {percent(p['1'])} | **X** {percent(p['X'])} | **{away_name}** {percent(p['2'])}")
        st.write(f"GG: {percent(p['GG'])} | NG: {percent(p['NG'])}")
        for line, over in p["over"].items():
            st.write(f"Over {line}: {percent(over)} / Under {line}: {percent(1-over)}")

with tab_history:
    st.subheader("Verificare acces istoric API")
    st.write("Acest test verifică dacă API-ul permite citirea meciurilor încheiate pentru competiția și sezonul introduse.")
    league_id = st.number_input("ID competiție (league)", min_value=1, value=39, step=1)
    season = st.number_input("Sezon (an de început)", min_value=2000, max_value=2100, value=date.today().year, step=1)
    if st.button("Verifică datele istorice"):
        try:
            payload = api_get("fixtures", {"league": int(league_id), "season": int(season), "status": "FT"}, api_key)
            rows = finished_fixture_rows(payload)
            st.success(f"API a returnat {len(rows)} meciuri încheiate pentru competiția {league_id}, sezonul {season}.")
            if rows:
                sample = []
                for r in rows[:10]:
                    sample.append({
                        "Data": r["fixture"].get("date", "")[:10],
                        "Gazde": r["teams"]["home"]["name"],
                        "Oaspeți": r["teams"]["away"]["name"],
                        "Scor": f"{r['goals']['home']}–{r['goals']['away']}",
                    })
                st.dataframe(pd.DataFrame(sample), use_container_width=True)
        except Exception as exc:
            st.error(f"Testul istoric a eșuat: {exc}")

st.divider()
st.caption("FOOTBALL AI PRO • Datele și endpoint-urile disponibile depind de abonamentul API-FOOTBALL.")
