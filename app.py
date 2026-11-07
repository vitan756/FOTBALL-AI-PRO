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
    
# ==========================================
# MODULE SUPLIMENTARE FOOTBALL AI PRO
# Nu modifica motorul principal
# ==========================================

if "predictii" in globals() and predictii:

    import pandas as pd

    rezultate_extra = []

    for meci in predictii:

        try:
            p1 = float(meci["1"].replace("%", ""))
            px = float(meci["X"].replace("%", ""))
            p2 = float(meci["2"].replace("%", ""))
            gg = float(meci["GG"].replace("%", ""))
            over25 = float(meci["Peste 2.5"].replace("%", ""))

            optiuni = {
                "1X": p1 + px,
                "X2": px + p2,
                "12": p1 + p2,
                "GG": gg,
                "NG": 100 - gg,
                "Peste 2.5": over25,
                "Sub 2.5": 100 - over25
            }

            principal = max(optiuni, key=optiuni.get)
            procent = optiuni[principal]

            if procent >= 75:
                risc = "Mic"
            elif procent >= 60:
                risc = "Mediu"
            else:
                risc = "Mare"

            rezultate_extra.append({
                "Data": meci["Data"],
                "Meci": meci["Meci"],
                "1X": f"{optiuni['1X']:.1f}%",
                "X2": f"{optiuni['X2']:.1f}%",
                "12": f"{optiuni['12']:.1f}%",
                "GG": f"{gg:.1f}%",
                "NG": f"{100-gg:.1f}%",
                "Peste 2.5": f"{over25:.1f}%",
                "Sub 2.5": f"{100-over25:.1f}%",
                "Pronostic principal": principal,
                "Probabilitate": f"{procent:.1f}%",
                "Risc": risc,
                "Scor estimat": meci["Scor estimat"]
            })

        except (KeyError, ValueError, TypeError):
            continue

    if rezultate_extra:

        st.divider()
        st.header("FOOTBALL AI PRO - MODULE SUPLIMENTARE")

        st.subheader("Top 20 pronosticuri")

        top20_extra = sorted(
            rezultate_extra,
            key=lambda x: float(
                x["Probabilitate"].replace("%", "")
            ),
            reverse=True
        )[:20]

        tabel_extra = pd.DataFrame(top20_extra)

        st.dataframe(
            tabel_extra,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Descarcă Top 20 CSV",
            data=tabel_extra.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="football_ai_pro_top20.csv",
            mime="text/csv",
            key="descarca_top20_extra"
            )
        
# ==========================================
# MODUL PIEȚE GOLURI - FOOTBALL AI PRO
# ==========================================

if "predictii" in globals() and predictii:

    import math
    import pandas as pd
    import streamlit as st

    rezultate_goluri = []

    for meci in predictii:

        try:
            over25 = float(
                meci["Peste 2.5"].replace("%", "")
            ) / 100

            # Estimare lambda total din probabilitatea Peste 2.5
            stanga = 0.01
            dreapta = 10.0

            for _ in range(100):
                mijloc = (stanga + dreapta) / 2

                sub25_model = math.exp(-mijloc) * (
                    1 + mijloc + (mijloc ** 2) / 2
                )

                over25_model = 1 - sub25_model

                if over25_model < over25:
                    stanga = mijloc
                else:
                    dreapta = mijloc

            lam_total = (stanga + dreapta) / 2

            sub05 = math.exp(-lam_total)
            sub15 = sub05 * (1 + lam_total)

            sub35 = sub15 * (
                1 + (lam_total ** 2) / 2
            )

            optiuni_goluri = {
                "Peste 0.5": 1 - sub05,
                "Sub 0.5": sub05,
                "Peste 1.5": 1 - sub15,
                "Sub 1.5": sub15,
                "Peste 2.5": over25,
                "Sub 2.5": 1 - over25,
                "Peste 3.5": 1 - sub35,
                "Sub 3.5": sub35
            }

            rezultate_goluri.append({
                "Meci": meci["Meci"],
                "Data": meci["Data"],
                "Peste 0.5": f"{optiuni_goluri['Peste 0.5']*100:.1f}%",
                "Sub 0.5": f"{optiuni_goluri['Sub 0.5']*100:.1f}%",
                "Peste 1.5": f"{optiuni_goluri['Peste 1.5']*100:.1f}%",
                "Sub 1.5": f"{optiuni_goluri['Sub 1.5']*100:.1f}%",
                "Peste 2.5": f"{optiuni_goluri['Peste 2.5']*100:.1f}%",
                "Sub 2.5": f"{optiuni_goluri['Sub 2.5']*100:.1f}%",
                "Peste 3.5": f"{optiuni_goluri['Peste 3.5']*100:.1f}%",
                "Sub 3.5": f"{optiuni_goluri['Sub 3.5']*100:.1f}%"
            })

        except (KeyError, ValueError, TypeError):
            continue

    if rezultate_goluri:

        st.divider()
        st.header("ANALIZĂ AVANSATĂ - TOTAL GOLURI")

        tabel_goluri = pd.DataFrame(rezultate_goluri)

        st.dataframe(
            tabel_goluri,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Descarcă analiza golurilor CSV",
            data=tabel_goluri.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="football_ai_pro_goluri.csv",
            mime="text/csv",
            key="descarca_goluri_extra"
        )
        
# ==========================================
# MODUL INTELIGENT - FOOTBALL AI PRO
# TOP 10 SI ANALIZA AVANSATA
# ==========================================

if "predictii" in globals() and isinstance(predictii, list) and predictii:

    import pandas as pd
    import streamlit as st

    analiza_inteligenta = []

    for meci in predictii:

        try:
            p1 = float(meci["1"].replace("%", ""))
            px = float(meci["X"].replace("%", ""))
            p2 = float(meci["2"].replace("%", ""))
            gg = float(meci["GG"].replace("%", ""))
            over25 = float(meci["Peste 2.5"].replace("%", ""))

            variante = {
                "1": p1,
                "X": px,
                "2": p2,
                "1X": p1 + px,
                "X2": px + p2,
                "12": p1 + p2,
                "GG": gg,
                "NG": 100 - gg,
                "Peste 2.5": over25,
                "Sub 2.5": 100 - over25
            }

            cel_mai_bun = max(
                variante,
                key=variante.get
            )

            probabilitate = variante[cel_mai_bun]

            if probabilitate >= 75:
                risc = "Mic"
            elif probabilitate >= 60:
                risc = "Mediu"
            else:
                risc = "Mare"

            analiza_inteligenta.append({
                "Meci": meci["Meci"],
                "Data": meci["Data"],
                "Pronostic principal": cel_mai_bun,
                "Probabilitate": probabilitate,
                "Risc": risc,
                "Scor estimat": meci.get(
                    "Scor estimat",
                    "Nedisponibil"
                ),
                "GG": gg,
                "Peste 2.5": over25
            })

        except (KeyError, ValueError, TypeError):
            continue

    if analiza_inteligenta:

        st.divider()
        st.header("🧠 ANALIZĂ INTELIGENTĂ")

        analiza_inteligenta.sort(
            key=lambda x: x["Probabilitate"],
            reverse=True
        )

        top10_inteligent = analiza_inteligenta[:10]

        tabel_inteligent = pd.DataFrame(
            top10_inteligent
        )

        tabel_inteligent["Probabilitate"] = (
            tabel_inteligent["Probabilitate"].map(
                lambda x: f"{x:.1f}%"
            )
        )

        tabel_inteligent["GG"] = (
            tabel_inteligent["GG"].map(
                lambda x: f"{x:.1f}%"
            )
        )

        tabel_inteligent["Peste 2.5"] = (
            tabel_inteligent["Peste 2.5"].map(
                lambda x: f"{x:.1f}%"
            )
        )

        st.subheader("TOP 10 OPORTUNITĂȚI")

        st.dataframe(
            tabel_inteligent,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Descarcă analiza inteligentă",
            data=tabel_inteligent.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="football_ai_pro_analiza.csv",
            mime="text/csv",
            key="descarca_analiza_inteligenta"
        )

        st.info(
            "Pauză/Final și golurile din prima repriză "
            "nu sunt calculate: motorul actual nu are "
            "date istorice separate pentru reprize."
        )
        
# ==========================================
# MODUL PAUZA / FINAL - OPENLIGADB
# FOOTBALL AI PRO
# ADAUGARE SEPARATA LA FINAL
# ==========================================

import math
import pandas as pd
import streamlit as st
from datetime import datetime

if (
    "predictii" in globals()
    and isinstance(predictii, list)
    and predictii
    and "toate_meciurile" in globals()
    and "openliga_data" in globals()
):

    def fap_resultat(meci, tip):
        rezultate = meci.get("matchResults") or []

        for rezultat in rezultate:
            if int(rezultat.get("resultTypeID", 0)) == tip:
                return (
                    int(rezultat["pointsTeam1"]),
                    int(rezultat["pointsTeam2"])
                )

        return None

    def fap_forma_repriza(echipa, data_limita, istoric):

        rezultate = []

        for meci_istoric in istoric:
            try:
                if not meci_istoric.get("matchIsFinished"):
                    continue

                data_veche = openliga_data(meci_istoric)

                if data_veche.replace(tzinfo=None) >= data_limita:
                    continue

                pauza = fap_resultat(meci_istoric, 1)
                final = fap_resultat(meci_istoric, 2)

                if pauza is None or final is None:
                    continue

                gazde = meci_istoric["team1"]["teamName"]
                oaspeti = meci_istoric["team2"]["teamName"]

                if echipa == gazde:
                    pauza_for = pauza[0]
                    pauza_against = pauza[1]
                    final_for = final[0]
                    final_against = final[1]

                elif echipa == oaspeti:
                    pauza_for = pauza[1]
                    pauza_against = pauza[0]
                    final_for = final[1]
                    final_against = final[0]

                else:
                    continue

                rezultate.append({
                    "pauza_for": pauza_for,
                    "pauza_against": pauza_against,
                    "repriza2_for": max(0, final_for - pauza_for),
                    "repriza2_against": max(
                        0, final_against - pauza_against
                    )
                })

            except Exception:
                continue

        rezultate.sort(
            key=lambda x: x["pauza_for"] + x["pauza_against"]
        )

        return rezultate[-8:]

    def fap_media(lista, cheie):
        return sum(x[cheie] for x in lista) / len(lista)

    def fap_poisson(lam, goluri):
        return (
            math.exp(-lam) * lam ** goluri
            / math.factorial(goluri)
        )

    def fap_probabilitati(lam_gazde, lam_oaspeti):

        p1 = 0
        px = 0
        p2 = 0
        total = 0

        for g in range(9):
            for o in range(9):
                p = (
                    fap_poisson(lam_gazde, g)
                    * fap_poisson(lam_oaspeti, o)
                )

                total += p

                if g > o:
                    p1 += p
                elif g == o:
                    px += p
                else:
                    p2 += p

        if total:
            return p1 / total, px / total, p2 / total

        return 0, 0, 0

    rezultate_repriza = []
    istoric_repriza = toate_meciurile

    for predictie in predictii:

        try:
            gazde, oaspeti = predictie["Meci"].split(" - ", 1)

            data_limita = datetime.strptime(
                predictie["Data"],
                "%d.%m.%Y %H:%M"
            )

            forma_g = fap_forma_repriza(
                gazde, data_limita, istoric_repriza
            )

            forma_o = fap_forma_repriza(
                oaspeti, data_limita, istoric_repriza
            )

            if len(forma_g) < 3 or len(forma_o) < 3:
                continue

            # Goluri estimate in prima repriza
            lam_g_pauza = (
                fap_media(forma_g, "pauza_for")
                + fap_media(forma_o, "pauza_against")
            ) / 2

            lam_o_pauza = (
                fap_media(forma_o, "pauza_for")
                + fap_media(forma_g, "pauza_against")
            ) / 2

            # Goluri estimate in repriza a doua
            lam_g_r2 = (
                fap_media(forma_g, "repriza2_for")
                + fap_media(forma_o, "repriza2_against")
            ) / 2

            lam_o_r2 = (
                fap_media(forma_o, "repriza2_for")
                + fap_media(forma_g, "repriza2_against")
            ) / 2

            # Probabilitati prima repriza
            total_pauza = lam_g_pauza + lam_o_pauza

            peste05_pauza = 1 - math.exp(-total_pauza)

            sub15_pauza = math.exp(-total_pauza) * (
                1 + total_pauza
            )

            ht1, htx, ht2 = fap_probabilitati(
                lam_g_pauza, lam_o_pauza
            )

            # Probabilitate GG repriza a doua
            gg_r2 = (
                (1 - math.exp(-lam_g_r2))
                * (1 - math.exp(-lam_o_r2))
            )

            # Probabilitati final preluate din motorul existent
            ft1 = float(predictie["1"].replace("%", "")) / 100
            ftx = float(predictie["X"].replace("%", "")) / 100
            ft2 = float(predictie["2"].replace("%", "")) / 100

            # Combinatii Pauza / Final
            combinatii = {
                "1/1": ht1 * ft1,
                "1/X": ht1 * ftx,
                "1/2": ht1 * ft2,
                "X/1": htx * ft1,
                "X/X": htx * ftx,
                "X/2": htx * ft2,
                "2/1": ht2 * ft1,
                "2/X": ht2 * ftx,
                "2/2": ht2 * ft2
            }

            combinatie_principala = max(
                combinatii,
                key=combinatii.get
            )

            rezultate_repriza.append({
                "Data": predictie["Data"],
                "Meci": predictie["Meci"],
                "Peste 0.5 pauza": f"{peste05_pauza*100:.1f}%",
                "Sub 1.5 pauza": f"{sub15_pauza*100:.1f}%",
                "Pauza 1": f"{ht1*100:.1f}%",
                "Pauza X": f"{htx*100:.1f}%",
                "Pauza 2": f"{ht2*100:.1f}%",
                "GG repriza 2": f"{gg_r2*100:.1f}%",
                "Pauza/Final": combinatie_principala,
                "Probabilitate P/F": (
                    f"{combinatii[combinatie_principala]*100:.1f}%"
                ),
                "Istoric echipe": (
                    f"{len(forma_g)} / {len(forma_o)}"
                )
            })

        except Exception:
            continue

    st.divider()
    st.header("ANALIZA PAUZA / FINAL")

    if rezultate_repriza:

        tabel_repriza = pd.DataFrame(rezultate_repriza)

        st.success(
            f"Analizate {len(rezultate_repriza)} meciuri "
            "cu istoric disponibil la pauza."
        )

        st.dataframe(
            tabel_repriza,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Descarca analiza Pauza / Final CSV",
            data=tabel_repriza.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="football_ai_pro_pauza_final.csv",
            mime="text/csv",
            key="descarca_pauza_final"
        )

    else:
        st.warning(
            "Nu exista suficiente rezultate istorice la pauza "
            "pentru meciurile selectate sau campionatul nu furnizeaza "
            "datele necesare."
        )

else:
    st.info(
        "Modulul Pauza / Final asteapta datele motorului principal."
                )
    
# ==========================================
# FOOTBALL AI PRO - AUTOINVATARE
# MODUL 1: MEMORIA PREDICTIILOR
# ==========================================

try:
    import pandas as pd
    import streamlit as st
    from datetime import datetime

    if "fap_memorie_predictii" not in st.session_state:
        st.session_state["fap_memorie_predictii"] = []

    if "predictii" in globals() and predictii:

        memorie = st.session_state["fap_memorie_predictii"]

        for meci in predictii:
            try:
                data_meci = str(meci.get("Data", ""))
                nume_meci = str(meci.get("Meci", ""))

                if not nume_meci:
                    continue

                identificator = data_meci + "|" + nume_meci

                exista = any(
                    x.get("ID") == identificator
                    for x in memorie
                )

                if not exista:
                    memorie.append({
                        "ID": identificator,
                        "Data": data_meci,
                        "Meci": nume_meci,
                        "Pronostic 1": meci.get("1", ""),
                        "Pronostic X": meci.get("X", ""),
                        "Pronostic 2": meci.get("2", ""),
                        "GG": meci.get("GG", ""),
                        "Peste 2.5": meci.get("Peste 2.5", ""),
                        "Scor estimat": meci.get("Scor estimat", ""),
                        "Data salvării": datetime.now().strftime(
                            "%Y-%m-%d %H:%M"
                        )
                    })

            except Exception:
                continue

    st.divider()
    st.header("🧠 AUTOÎNVĂȚARE - MEMORIA ROBOTULUI")

    memorie = st.session_state["fap_memorie_predictii"]

    st.metric(
        "Predicții memorate",
        len(memorie)
    )

    if memorie:
        tabel_memorie = pd.DataFrame(memorie)

        st.dataframe(
            tabel_memorie,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Descarcă memoria robotului CSV",
            data=tabel_memorie.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="football_ai_pro_memorie.csv",
            mime="text/csv"
        )

    else:
        st.info(
            "Robotul va memora aici predicțiile "
            "pe măsură ce sunt generate."
        )

except Exception as eroare_memorie:
    st.warning(
        "Modulul de memorie: " + str(eroare_memorie)
    )
    
# ==========================================
# FOOTBALL AI PRO - MODUL 2
# VERIFICAREA PRONOSTICURILOR
# ==========================================

try:
    import streamlit as st
    import pandas as pd

    if "fap_rezultate_reale" not in st.session_state:
        st.session_state["fap_rezultate_reale"] = {}

    st.divider()
    st.header("📊 VERIFICARE REZULTATE REALE")

    memorie = st.session_state.get(
        "fap_memorie_predictii", []
    )

    rezultate = st.session_state["fap_rezultate_reale"]

    if memorie:

        meciuri_neverificate = [
            m for m in memorie
            if m.get("ID") not in rezultate
        ]

        if meciuri_neverificate:

            selectat = st.selectbox(
                "Alege meciul terminat",
                meciuri_neverificate,
                format_func=lambda m: (
                    str(m.get("Data", "")) + " - "
                    + str(m.get("Meci", ""))
                ),
                key="fap_select_verificare"
            )

            st.write(
                "**Predicția robotului:**",
                selectat.get("Scor estimat", "Nedisponibil")
            )

            with st.form("fap_form_scor_real"):

                col1, col2 = st.columns(2)

                with col1:
                    goluri_gazde = st.number_input(
                        "Goluri gazde",
                        min_value=0,
                        max_value=30,
                        value=0,
                        step=1
                    )

                with col2:
                    goluri_oaspeti = st.number_input(
                        "Goluri oaspeți",
                        min_value=0,
                        max_value=30,
                        value=0,
                        step=1
                    )

                trimite = st.form_submit_button(
                    "Verifică pronosticul"
                )

                if trimite:

                    g = int(goluri_gazde)
                    o = int(goluri_oaspeti)

                    p1 = float(
                        str(selectat.get("Pronostic 1", "0"))
                        .replace("%", "").replace(",", ".")
                    )
                    px = float(
                        str(selectat.get("Pronostic X", "0"))
                        .replace("%", "").replace(",", ".")
                    )
                    p2 = float(
                        str(selectat.get("Pronostic 2", "0"))
                        .replace("%", "").replace(",", ".")
                    )

                    rezultat_real = (
                        "1" if g > o else
                        "X" if g == o else "2"
                    )

                    pronostic_1x2 = max(
                        {"1": p1, "X": px, "2": p2},
                        key=lambda x: {"1": p1, "X": px, "2": p2}[x]
                    )

                    gg_real = "DA" if g > 0 and o > 0 else "NU"
                    gg_robot = (
                        "DA" if float(
                            str(selectat.get("GG", "0"))
                            .replace("%", "").replace(",", ".")
                        ) >= 50 else "NU"
                    )

                    over_real = "DA" if g + o >= 3 else "NU"
                    over_robot = (
                        "DA" if float(
                            str(selectat.get("Peste 2.5", "0"))
                            .replace("%", "").replace(",", ".")
                        ) >= 50 else "NU"
                    )

                    rezultate[selectat["ID"]] = {
                        "Meci": selectat["Meci"],
                        "Scor real": f"{g}-{o}",
                        "Pronostic 1X2": pronostic_1x2,
                        "1X2 corect": pronostic_1x2 == rezultat_real,
                        "GG corect": gg_robot == gg_real,
                        "Peste 2.5 corect": over_robot == over_real
                    }

                    st.session_state[
                        "fap_rezultate_reale"
                    ] = rezultate

                    st.success(
                        "Scorul a fost înregistrat și verificat!"
                    )

                    st.rerun()

        else:
            st.info(
                "Toate predicțiile memorate au fost verificate."
            )

        if rezultate:

            tabel_verificare = pd.DataFrame(
                list(rezultate.values())
            )

            st.subheader("📈 Performanța robotului")

            for piata, coloana in [
                ("1X2", "1X2 corect"),
                ("GG", "GG corect"),
                ("Peste 2.5", "Peste 2.5 corect")
            ]:

                total = len(tabel_verificare)
                corecte = int(
                    tabel_verificare[coloana].sum()
                )
                procent = corecte / total * 100

                st.metric(
                    piata,
                    f"{procent:.1f}%",
                    f"{corecte} din {total} corecte"
                )

            st.dataframe(
                tabel_verificare,
                use_container_width=True,
                hide_index=True
            )

    else:
        st.info(
            "Mai întâi trebuie să existe predicții în memorie."
        )

except Exception as eroare_verificare:
    st.warning(
        "Eroare verificare: " + str(eroare_verificare)
    )
    
# ==========================================
# FOOTBALL AI PRO - SUPABASE
# MEMORIE PERMANENTA
# ==========================================

try:
    import requests
    import streamlit as st

    supabase_url = st.secrets.get(
        "SUPABASE_URL", ""
    ).strip().rstrip("/")

    supabase_key = st.secrets.get(
        "SUPABASE_KEY", ""
    ).strip()

    if supabase_url and supabase_key:

        memorie_supabase = st.session_state.get(
            "fap_memorie_predictii", []
        )

        antete_supabase = {
            "apikey": supabase_key,
            "Authorization": "Bearer " + supabase_key,
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=minimal"
        }

        adresa_tabel = (
            supabase_url + "/rest/v1/fap_predictii"
        )

        randuri_supabase = []

        for predictie in memorie_supabase:
            identificator = predictie.get("ID")

            if identificator:
                randuri_supabase.append({
                    "id": str(identificator),
                    "prediction": predictie
                })

        salvate_supabase = 0

        for pozitie in range(
            0, len(randuri_supabase), 100
        ):
            lot = randuri_supabase[
                pozitie:pozitie + 100
            ]

            raspuns = requests.post(
                adresa_tabel,
                params={"on_conflict": "id"},
                headers=antete_supabase,
                json=lot,
                timeout=30
            )

            raspuns.raise_for_status()
            salvate_supabase += len(lot)

        verificare_supabase = requests.get(
            adresa_tabel,
            params={"select": "id"},
            headers=antete_supabase,
            timeout=30
        )

        verificare_supabase.raise_for_status()

        total_supabase = len(
            verificare_supabase.json()
        )

        st.divider()
        st.header("☁️ MEMORIE PERMANENTĂ SUPABASE")

        st.metric(
            "Predicții găsite în baza de date",
            total_supabase
        )

        st.success(
            "Conexiunea Supabase funcționează! "
            "Predicțiile memorate au fost sincronizate."
        )

    else:
        st.warning(
            "Completează SUPABASE_URL și SUPABASE_KEY "
            "în Streamlit Secrets."
        )

except Exception as eroare_supabase:
    st.error(
        "Eroare Supabase: " + str(eroare_supabase)
    )
    
    
    
        
        
        
        
    
