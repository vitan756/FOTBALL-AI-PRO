import math
from datetime import date, timedelta
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="FOOTBALL AI PRO", page_icon="⚽", layout="wide")

BASE_URL = "https://v3.football.api-sports.io"
@st.cache_data(ttl=86400, show_spinner=False)
def api_get(endpoint, api_key, params=None):
    headers = {"x-apisports-key": api_key}
    try:
        response = requests.get(
            f"{BASE_URL}/{endpoint}",
            headers=headers,
            params=params or {},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Nu s-a putut contacta API-FOOTBALL: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(f"API-FOOTBALL a trimis un răspuns invalid (HTTP {response.status_code}).")

    if response.status_code != 200:
        raise RuntimeError(f"API-FOOTBALL HTTP {response.status_code}: {payload}")

    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-FOOTBALL a raportat: {errors}")

    return payload.get("response", []), payload.get("results", 0)

def poisson(lam, goals):
    return math.exp(-lam) * (lam ** goals) / math.factorial(goals)

def match_probabilities(home_lambda, away_lambda, max_goals=8):
    p_home = p_draw = p_away = 0.0
    totals = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    gg = 0.0
    scores = []
    for h in range(max_goals + 1):
        ph = poisson(home_lambda, h)
        for a in range(max_goals + 1):
            p = ph * poisson(away_lambda, a)
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
            if h + a > 1:
                totals[1.5] += p
            if h + a > 2:
                totals[2.5] += p
            if h + a > 3:
                totals[3.5] += p
            if h > 0 and a > 0:
                gg += p
            scores.append((p, h, a))
    total = p_home + p_draw + p_away
    def extra_markets(home_lambda, away_lambda):
    """
    Piețe suplimentare calculate din distribuția Poisson.
    Valorile returnate sunt procente 0-100.
    """
    def matrix(lam_h, lam_a, max_goals=10):
        rezultate = []
        total = 0.0
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                p = poisson(lam_h, h) * poisson(lam_a, a)
                rezultate.append((h, a, p))
                total += p

        if total <= 0:
            return []

        return [(h, a, p / total) for h, a, p in rezultate]

    def prob(conditie, distributie):
        return sum(p for h, a, p in distributie if conditie(h, a)) * 100

    def procent(valoare):
        return round(valoare, 1)

    dist = matrix(home_lambda, away_lambda)

    rezultate = {}

    # Rezultat și șanse duble
    p1 = prob(lambda h, a: h > a, dist)
    px = prob(lambda h, a: h == a, dist)
    p2 = prob(lambda h, a: h < a, dist)

    rezultate["1X"] = procent(p1 + px)
    rezultate["X2"] = procent(px + p2)
    rezultate["12"] = procent(p1 + p2)

    # Draw No Bet: egalul înseamnă banii înapoi
    total_decis = p1 + p2
    rezultate["DNB gazde"] = procent(
        p1 / total_decis * 100 if total_decis else 0
    )
    rezultate["DNB oaspeți"] = procent(
        p2 / total_decis * 100 if total_decis else 0
    )

    # Total goluri
    for linie in [0.5, 1.5, 2.5, 3.5, 4.5]:
        peste = prob(lambda h, a: h + a > linie, dist)
        rezultate[f"Peste {linie}"] = procent(peste)
        rezultate[f"Sub {linie}"] = procent(100 - peste)

    # Goluri echipe
    for linie in [0.5, 1.5]:
        rezultate[f"Gazde peste {linie}"] = procent(
            prob(lambda h, a: h > linie, dist)
        )
        rezultate[f"Oaspeți peste {linie}"] = procent(
            prob(lambda h, a: a > linie, dist)
        )

    # Combinații calculate direct din scoruri
    rezultate["1X + Peste 1.5"] = procent(
        prob(lambda h, a: h >= a and h + a >= 2, dist)
    )
    rezultate["X2 + Sub 3.5"] = procent(
        prob(lambda h, a: h <= a and h + a <= 3, dist)
    )
    rezultate["1 + Peste 1.5"] = procent(
        prob(lambda h, a: h > a and h + a >= 2, dist)
    )
    rezultate["2 + Peste 1.5"] = procent(
        prob(lambda h, a: h < a and h + a >= 2, dist)
    )

    # Pauză: estimare matematică la 45% din golurile așteptate
    dist_pauza = matrix(home_lambda * 0.45, away_lambda * 0.45)

    rezultate["Pauză 1"] = procent(
        prob(lambda h, a: h > a, dist_pauza)
    )
    rezultate["Pauză X"] = procent(
        prob(lambda h, a: h == a, dist_pauza)
    )
    rezultate["Pauză 2"] = procent(
        prob(lambda h, a: h < a, dist_pauza)
    )

    for linie in [0.5, 1.5]:
        peste = prob(
            lambda h, a: h + a > linie,
            dist_pauza
        )
        rezultate[f"Pauză peste {linie}"] = procent(peste)
        rezultate[f"Pauză sub {linie}"] = procent(100 - peste)

    return rezultate
    if total:
        p_home, p_draw, p_away = p_home/total, p_draw/total, p_away/total
    return {
        "1": p_home, "X": p_draw, "2": p_away,
        "GG": gg, "NG": 1-gg,
        "Over 1.5": totals[1.5], "Over 2.5": totals[2.5], "Over 3.5": totals[3.5],
        "Under 1.5": 1-totals[1.5], "Under 2.5": 1-totals[2.5], "Under 3.5": 1-totals[3.5],
        "scores": sorted(scores, reverse=True)[:5],
    }

def completed_fixtures(rows):
    done = []
    for item in rows:
        fixture = item.get("fixture", {})
        status = fixture.get("status", {}).get("short", "")
        goals = item.get("goals", {})
        if status in ("FT", "AET", "PEN") and goals.get("home") is not None and goals.get("away") is not None:
            done.append(item)
    return sorted(done, key=lambda x: x.get("fixture", {}).get("timestamp", 0), reverse=True)


def team_recent(team_id, api_key, today):
    all_rows = []

    for season in (2022, 2023, 2024):
        rows, _ = api_get(
            "fixtures",
            api_key,
            {
                "team": team_id,
                "season": season,
                "timezone": "Europe/Bucharest",
            },
        )
        all_rows.extend(rows)

    unique = {}
    for item in all_rows:
        fixture_id = item.get("fixture", {}).get("id")
        if fixture_id is not None:
            unique[fixture_id] = item

    return completed_fixtures(list(unique.values()))[:10]
def team_rates(fixtures, team_id, home_venue):
    scored, conceded = [], []
    for item in fixtures:
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        is_home = teams.get("home", {}).get("id") == team_id
        own = goals.get("home") if is_home else goals.get("away")
        opp = goals.get("away") if is_home else goals.get("home")
        if own is not None and opp is not None:
            scored.append(float(own))
            conceded.append(float(opp))
    if not scored:
        return None
    return sum(scored)/len(scored), sum(conceded)/len(conceded)

def expected_goals(home_rows, away_rows, home_id, away_id):
    h_all = team_rates(home_rows, home_id, True)
    a_all = team_rates(away_rows, away_id, False)
    if not h_all or not a_all:
        raise RuntimeError("Nu există suficiente meciuri terminate în ultimele 365 de zile pentru ambele echipe.")
    # Estimare simplificată din golurile marcate și primite recent.
    h_attack = (h_all[0] + a_all[1]) / 2
    a_attack = (a_all[0] + h_all[1]) / 2
    return max(0.15, min(4.0, h_attack)), max(0.15, min(4.0, a_attack))

st.title("⚽ FOOTBALL AI PRO")
st.caption("Analiză statistică orientativă pe baza meciurilor recente. Nu garantează rezultate și nu reprezintă recomandare de pariere.")

with st.sidebar:
    st.header("Conectare API")
    api_key = st.text_input("API-Football Key", type="password", help="Cheia rămâne doar în sesiunea curentă.")
    ninjas_key = st.text_input("API Ninjas Key", type="password")
    st.caption("Nu trimite cheia nimănui și nu o publica pe GitHub.")
    st.divider()
    st.write("Plan Free: aplicația folosește intervale de date, nu parametrul `last`.")

    if not api_key: 
        st.info("Introdu cheia APINinjas în meniul din stânga.")

tab1, tab2, tab3 = st.tabs(["Meciuri", "Analiză manuală", "Test API"])
with tab1:
    selected_date = st.date_input("Data meciurilor", value=date.today())
    if st.button("Încarcă meciurile", type="primary"):
        try:
            rows, _ = api_get("fixtures", api_key, {
                "date": selected_date.isoformat(),
                "timezone": "Europe/Bucharest",
            })
            st.session_state["fixtures_for_date"] = rows
            st.session_state["fixtures_date"] = selected_date.isoformat()
        except Exception as exc:
            st.error(str(exc))

    rows = st.session_state.get("fixtures_for_date", [])
    if st.session_state.get("fixtures_date") == selected_date.isoformat() and rows:
        options = []
        lookup = {}
        for item in rows:
            fixture = item.get("fixture", {})
            teams = item.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            label = f'{home.get("name", "Gazde")} - {away.get("name", "Oaspeți")} | {fixture.get("date", "")[:16]}'
            options.append(label)
            lookup[label] = item
        chosen = st.selectbox("Alege meciul", options)
        match = lookup[chosen]
        home = match["teams"]["home"]
        away = match["teams"]["away"]
        st.subheader(f'{home.get("name")} - {away.get("name")}')
        if st.button("Analizează meciul selectat", type="primary"):
            try:
                with st.spinner("Analizez ultimele meciuri disponibile..."):
                    home_recent = team_recent(home["id"], api_key, selected_date)
                    away_recent = team_recent(away["id"], api_key, selected_date)
                    hl, al = expected_goals(home_recent, away_recent, home["id"], away["id"])
                    probs = match_probabilities(hl, al)
      
                c1, c2, c3 = st.columns(3)
                c1.metric("Victorie gazde (1)", f"{probs['1']*100:.1f}%")
                c2.metric("Egal (X)", f"{probs['X']*100:.1f}%")
                c3.metric("Victorie oaspeți (2)", f"{probs['2']*100:.1f}%")
                st.write(f"Goluri estimate: **{hl:.2f} – {al:.2f}**")
                st.subheader("Piețe statistice")
                market_rows = [
                    {"Piață": key, "Probabilitate": f"{probs[key]*100:.1f}%"}
                    for key in ["GG", "NG", "Over 1.5", "Under 1.5", "Over 2.5", "Under 2.5", "Over 3.5", "Under 3.5"]
                ]
                st.dataframe(pd.DataFrame(market_rows), use_container_width=True, hide_index=True)
                st.subheader("Scoruri exacte cu probabilitate estimată")
                st.dataframe(pd.DataFrame([
                    {"Scor": f"{h}-{a}", "Probabilitate": f"{p*100:.1f}%"}
                    for p, h, a in probs["scores"]
                ]), use_container_width=True, hide_index=True)
                st.caption(f"Eșantion folosit: {len(home_recent)} meciuri pentru gazde și {len(away_recent)} pentru oaspeți.")
            except Exception as exc:
                st.error(f"Analiza nu a putut fi calculată: {exc}")
    elif st.session_state.get("fixtures_date") == selected_date.isoformat():
        st.warning("Nu au fost găsite meciuri pentru data aleasă.")

with tab2:
    st.subheader("Analiză manuală")
    c1, c2 = st.columns(2)
    with c1:
        home_name = st.text_input("Echipa gazdă", "Gazde")
        home_scored = st.number_input("Media golurilor marcate de gazde", min_value=0.0, max_value=5.0, value=1.4, step=0.1)
        home_conceded = st.number_input("Media golurilor primite de gazde", min_value=0.0, max_value=5.0, value=1.1, step=0.1)
    with c2:
        away_name = st.text_input("Echipa oaspete", "Oaspeți")
        away_scored = st.number_input("Media golurilor marcate de oaspeți", min_value=0.0, max_value=5.0, value=1.2, step=0.1)
        away_conceded = st.number_input("Media golurilor primite de oaspeți", min_value=0.0, max_value=5.0, value=1.3, step=0.1)
    if st.button("Calculează analiza manuală"):
        hl = max(0.15, (home_scored + away_conceded)/2)
        al = max(0.15, (away_scored + home_conceded)/2)
        probs = match_probabilities(hl, al)
        st.write(f"**{home_name} – {away_name}** | Goluri estimate: {hl:.2f} – {al:.2f}")
        st.write(f"1: **{probs['1']*100:.1f}%** · X: **{probs['X']*100:.1f}%** · 2: **{probs['2']*100:.1f}%**")
        st.write(f"GG: **{probs['GG']*100:.1f}%** · Over 2.5: **{probs['Over 2.5']*100:.1f}%**")

with tab3:
    st.subheader("Verificare conexiune API")
    if st.button("Testează cheia API"):
        try:
            leagues, count = api_get("leagues", api_key, {"current": "true"})
            st.success(f"Conexiune reușită. API-ul a returnat {count} competiții.")
        except Exception as exc:
            st.error(str(exc))

# SURSA GRATUITA OPENLIGADB
@st.cache_data(ttl=3600)
def meciuri_gratuite(sezon):
    url = f"https://api.openligadb.de/getavailableleagues/{sezon}"
    raspuns = requests.get(url, timeout=20)
    raspuns.raise_for_status()
    ligi = raspuns.json()
    return pd.DataFrame([
        {
            "Campionat": liga.get("leagueName", ""),
            "Cod": liga.get("leagueShortcut", ""),
            "Sezon": liga.get("leagueSeason", sezon)
        }
        for liga in ligi
    ])

st.divider()
st.subheader("⚽ Sursă gratuită de campionate")
sezon_gratuit = st.selectbox(
    "Alege sezonul",
    [2026, 2025, 2024, 2023, 2022]
)

if st.button("Încarcă campionatele gratuite"):
    try:
        campionate = meciuri_gratuite(sezon_gratuit)
        if campionate.empty:
            st.warning("Nu sunt campionate disponibile pentru acest sezon.")
        else:
            st.dataframe(campionate, use_container_width=True)
    except Exception as e:
        st.error(f"Eroare la sursa gratuită: {e}")

# MECIURI GRATUITE OPENLIGADB
@st.cache_data(ttl=1800)
def incarca_meciuri_gratuite(cod_liga, sezon):
    url = f"https://api.openligadb.de/getmatchdata/{cod_liga}/{sezon}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    date = r.json()

    rezultate = []
    for m in date:
        echipa1 = m.get("team1", {}).get("teamName", "")
        echipa2 = m.get("team2", {}).get("teamName", "")
        scoruri = m.get("matchResults", [])
        scor = next(
            (x for x in scoruri if x.get("resultTypeID") == 2),
            scoruri[-1] if scoruri else {}
        )
        rezultate.append({
            "Data": m.get("matchDateTime", ""),
            "Gazde": echipa1,
            "Oaspeți": echipa2,
            "Goluri gazde": scor.get("pointsTeam1"),
            "Goluri oaspeți": scor.get("pointsTeam2")
        })

    return pd.DataFrame(rezultate)


st.divider()
st.subheader("⚽ MECIURI DIN SURSA GRATUITĂ")

try:
    lista_ligi = meciuri_gratuite(sezon_gratuit)

    if not lista_ligi.empty:
        liga_aleasa = st.selectbox(
            "Alege campionatul",
            lista_ligi.to_dict("records"),
            format_func=lambda x: x["Campionat"]
        )

        if st.button("Încarcă meciurile campionatului"):
            meciuri = incarca_meciuri_gratuite(
                liga_aleasa["Cod"],
                liga_aleasa["Sezon"]
            )
            if meciuri.empty:
                st.warning("Nu există meciuri pentru acest campionat.")
            else:
                st.dataframe(meciuri, use_container_width=True)
    else:
        st.warning("Nu există campionate disponibile.")
except Exception as e:
    st.error(f"Eroare la încărcarea meciurilor: {e}")


# ==========================================
# MOTOR DE PREDICTII GRATUITE - FOOTBALL AI PRO
# ==========================================

from datetime import datetime, timezone

@st.cache_data(ttl=1800)
def openliga_istoric(cod, sezon):
    url = f"https://api.openligadb.de/getmatchdata/{cod}/{sezon}"
    raspuns = requests.get(url, timeout=25)
    raspuns.raise_for_status()
    date_meciuri = raspuns.json()
    return date_meciuri if isinstance(date_meciuri, list) else []

def openliga_scor(meci):
    rezultate = meci.get("matchResults", [])

    finale = [
        x for x in rezultate
        if x.get("resultTypeID") == 2
    ]

    if not finale:
        return None

    scor = finale[-1]

    gazde = scor.get("pointsTeam1")
    oaspeti = scor.get("pointsTeam2")

    if gazde is None or oaspeti is None:
        return None

    return int(gazde), int(oaspeti)
def openliga_data(meci):
    try:
        text_data = meci.get("matchDateTime", "")
        rezultat = datetime.fromisoformat(
            text_data.replace("Z", "+00:00")
        )

        if rezultat.tzinfo is None:
            rezultat = rezultat.replace(tzinfo=timezone.utc)

        return rezultat.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None

    scor = finale[-1]

    gazde = scor.get("pointsTeam1")
    oaspeti = scor.get("pointsTeam2")

    if gazde is None or oaspeti is None:
        return None

    return int(gazde), int(oaspeti)


def openliga_data(meci):
    try:
        text_data = meci.get("matchDateTime", "")
        return datetime.fromisoformat(
            text_data.replace("Z", "+00:00")
        )
    except (ValueError, TypeError):
        return None

def openliga_data(meci):
    try:
        text_data = meci.get("matchDateTime", "")
        rezultat = datetime.fromisoformat(
            text_data.replace("Z", "+00:00")
        )

        if rezultat.tzinfo is None:
            rezultat = rezultat.replace(tzinfo=timezone.utc)

        return rezultat.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


def openliga_forma(meciuri, echipa, pana_la):
    if pana_la.tzinfo is None:
        pana_la = pana_la.replace(tzinfo=timezone.utc)
    else:
        pana_la = pana_la.astimezone(timezone.utc)

    goluri_marcate = []
    goluri_primite = []
    meciuri_echipa = []

    for meci in meciuri:
        data = openliga_data(meci)
        scor = openliga_scor(meci)

        if data is None or scor is None:
            continue

        if data >= pana_la:
            continue

        gazde = meci.get("team1", {}).get("teamName", "")
        oaspeti = meci.get("team2", {}).get("teamName", "")

        if gazde == echipa:
            meciuri_echipa.append((data, scor[0], scor[1]))
        elif oaspeti == echipa:
            meciuri_echipa.append((data, scor[1], scor[0]))

    meciuri_echipa.sort(key=lambda x: x[0], reverse=True)

    for _, marcate, primite in meciuri_echipa[:8]:
        goluri_marcate.append(marcate)
        goluri_primite.append(primite)

    if len(goluri_marcate) < 3:
        return None

    return (
        sum(goluri_marcate) / len(goluri_marcate),
        sum(goluri_primite) / len(goluri_primite),
        len(goluri_marcate)
    )

st.divider()
st.header("🔮 PREDICȚII GRATUITE")

st.caption(
    "Model Poisson calculat din ultimele 8 meciuri disponibile "
    "pentru fiecare echipă. Sunt afișate doar meciurile viitoare "
    "pentru care există suficient istoric."
)

try:
    ligi_pred = meciuri_gratuite(sezon_gratuit)

    if not ligi_pred.empty:

        liga_selectata = st.selectbox(
            "Campionat pentru predicții",
            ligi_pred.to_dict("records"),
            format_func=lambda x: x["Campionat"],
            key="campionat_motor_predictii"
        )

        if st.button(
            "CALCULEAZĂ PREDICȚII",
            type="primary",
            key="buton_motor_predictii"
        ):

            with st.spinner("Analizez meciurile și forma echipelor..."):

                toate_meciurile = openliga_istoric(
                    liga_selectata["Cod"],
                    liga_selectata["Sezon"]
                )

                acum = datetime.now(timezone.utc)

                viitoare = []

                for meci in toate_meciurile:
                    data = openliga_data(meci)

                    if data is None:
                        continue

                    if data > acum and openliga_scor(meci) is None:
                        if (
                            meci.get("team1", {}).get("teamName")
                            and meci.get("team2", {}).get("teamName")
                        ):
                            viitoare.append(meci)

                viitoare.sort(
                    key=lambda x: x.get("matchDateTime", "")
                )

                predictii = []

                for meci in viitoare:

                    data_meci = openliga_data(meci)

                    gazde = meci["team1"]["teamName"]
                    oaspeti = meci["team2"]["teamName"]

                    forma_gazde = openliga_forma(
                        toate_meciurile,
                        gazde,
                        data_meci
                    )

                    forma_oaspeti = openliga_forma(
                        toate_meciurile,
                        oaspeti,
                        data_meci
                    )

                    if not forma_gazde or not forma_oaspeti:
                        continue

                    goluri_gazde = (
                        forma_gazde[0] + forma_oaspeti[1]
                    ) / 2

                    goluri_oaspeti = (
                        forma_oaspeti[0] + forma_gazde[1]
                    ) / 2

                    lambda_gazde = max(
                        0.15,
                        min(4.0, goluri_gazde)
                    )

                    lambda_oaspeti = max(
                        0.15,
                        min(4.0, goluri_oaspeti)
                    )

                    probabilitati = match_probabilities(
                        lambda_gazde,
                        lambda_oaspeti
                    )

                    scor_probabil = probabilitati["scores"][0]

                    predictii.append({
                        "Data": data_meci.strftime("%d.%m.%Y %H:%M"),
                        "Meci": f"{gazde} - {oaspeti}",
                        "1": f'{probabilitati["1"] * 100:.1f}%',
                        "X": f'{probabilitati["X"] * 100:.1f}%',
                        "2": f'{probabilitati["2"] * 100:.1f}%',
                        "GG": f'{probabilitati["GG"] * 100:.1f}%',
                        "Peste 2.5": f'{probabilitati["Over 2.5"] * 100:.1f}%',
                        "Scor estimat": (
                            f"{scor_probabil[1]}-{scor_probabil[2]}"
                        ),
                        "Meciuri analizate": (
                            f"{forma_gazde[2]} / {forma_oaspeti[2]}"
                        )
                    })

            if predictii:
                st.success(
                    f"Au fost calculate {len(predictii)} predicții."
                )

                tabel_predictii = pd.DataFrame(predictii)

                st.dataframe(
                    tabel_predictii,
                    use_container_width=True,
                    hide_index=True
                )

                st.download_button(
                    "Descarcă predicțiile CSV",
                    data=tabel_predictii.to_csv(
                        index=False
                    ).encode("utf-8-sig"),
                    file_name="football_ai_pro_predictii.csv",
                    mime="text/csv"
                )

            else:
                st.warning(
                    "Nu există meciuri viitoare cu suficient istoric "
                    "pentru predicții în acest campionat."
                )

except Exception as eroare:
    st.error(
        f"Eroare la motorul de predicții gratuite: {eroare}"
    )
    
