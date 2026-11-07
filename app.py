
import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ==========================================
# FOOTBALL AI PRO
# ==========================================

st.set_page_config(
    page_title="FOOTBALL AI PRO",
    page_icon="⚽",
    layout="wide"
)

OPENLIGA = "https://api.openligadb.de"
FOOTBALL_API = "https://v3.football.api-sports.io"
BUCHAREST = ZoneInfo("Europe/Bucharest")


# ==========================================
# SURSA GRATUITA OPENLIGADB
# ==========================================

@st.cache_data(ttl=1800, show_spinner=False)
def incarca_campionate(sezon):
    url = f"{OPENLIGA}/getavailableleagues/{sezon}"
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    data = r.json()

    if not isinstance(data, list):
        return pd.DataFrame()

    rezultate = []

    for liga in data:
        cod = liga.get("leagueShortcut")
        nume = liga.get("leagueName")

        if cod and nume:
            rezultate.append({
                "Campionat": nume,
                "Cod": cod,
                "Sezon": liga.get("leagueSeason", sezon)
            })

    return pd.DataFrame(rezultate).drop_duplicates(
        subset=["Cod", "Sezon"]
    )


@st.cache_data(ttl=900, show_spinner=False)
def incarca_meciuri(cod, sezon):
    url = f"{OPENLIGA}/getmatchdata/{cod}/{sezon}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    return data if isinstance(data, list) else []


# ==========================================
# PRELUCRARE MECIURI
# ==========================================

def data_meci(meci):
    valoare = (
        meci.get("matchDateTimeUTC")
        or meci.get("matchDateTime")
    )

    if not valoare:
        return None

    try:
        dt = datetime.fromisoformat(
            valoare.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(BUCHAREST)

    except (ValueError, TypeError):
        return None


def scor_final(meci):
    rezultate = meci.get("matchResults", [])

    valide = []

    for rezultat in rezultate:
        gazde = rezultat.get("pointsTeam1")
        oaspeti = rezultat.get("pointsTeam2")

        if gazde is None or oaspeti is None:
            continue

        valide.append(rezultat)

    if not valide:
        return None

    valide.sort(
        key=lambda x: x.get("resultTypeID", 0)
    )

    ultimul = valide[-1]

    return (
        int(ultimul["pointsTeam1"]),
        int(ultimul["pointsTeam2"])
    )


def nume_echipe(meci):
    gazde = (
        meci.get("team1", {}).get("teamName")
        or "Gazde"
    )

    oaspeti = (
        meci.get("team2", {}).get("teamName")
        or "Oaspeti"
    )

    return gazde, oaspeti


# ==========================================
# MODEL POISSON
# ==========================================

def poisson(lam, goluri):
    return (
        math.exp(-lam)
        * (lam ** goluri)
        / math.factorial(goluri)
    )


def calculeaza_probabilitati(lam_h, lam_a):
    p1 = 0.0
    px = 0.0
    p2 = 0.0
    gg = 0.0
    over15 = 0.0
    over25 = 0.0
    over35 = 0.0
    scoruri = []

    for h in range(9):
        ph = poisson(lam_h, h)

        for a in range(9):
            p = ph * poisson(lam_a, a)

            if h > a:
                p1 += p
            elif h == a:
                px += p
            else:
                p2 += p

            if h > 0 and a > 0:
                gg += p

            if h + a > 1:
                over15 += p

            if h + a > 2:
                over25 += p

            if h + a > 3:
                over35 += p

            scoruri.append((p, h, a))

    total = p1 + px + p2

    if total > 0:
        p1 /= total
        px /= total
        p2 /= total

    return {
        "1": p1,
        "X": px,
        "2": p2,
        "GG": gg,
        "NG": 1 - gg,
        "Peste 1.5": over15,
        "Sub 1.5": 1 - over15,
        "Peste 2.5": over25,
        "Sub 2.5": 1 - over25,
        "Peste 3.5": over35,
        "Sub 3.5": 1 - over35,
        "scoruri": sorted(
            scoruri,
            reverse=True
        )[:5]
    }


# ==========================================
# FORMA ECHIPELOR
# ==========================================

def forma_echipa(meciuri, echipa, inainte_de):
    rezultate = []

    for meci in meciuri:
        dt = data_meci(meci)

        if dt is None or dt >= inainte_de:
            continue

        scor = scor_final(meci)

        if scor is None:
            continue

        gazde, oaspeti = nume_echipe(meci)

        if gazde == echipa:
            rezultate.append((dt, scor[0], scor[1]))

        elif oaspeti == echipa:
            rezultate.append((dt, scor[1], scor[0]))

    rezultate.sort(
        key=lambda x: x[0],
        reverse=True
    )

    rezultate = rezultate[:8]

    if len(rezultate) < 3:
        return None

    marcate = [x[1] for x in rezultate]
    primite = [x[2] for x in rezultate]

    return (
        sum(marcate) / len(marcate),
        sum(primite) / len(primite),
        len(rezultate)
    )


def analizeaza_meci(meci, toate_meciurile):
    dt = data_meci(meci)

    if dt is None:
        return None

    gazde, oaspeti = nume_echipe(meci)

    forma_h = forma_echipa(
        toate_meciurile,
        gazde,
        dt
    )

    forma_a = forma_echipa(
        toate_meciurile,
        oaspeti,
        dt
    )

    if not forma_h or not forma_a:
        return None

    # Estimare din forma recenta a echipelor.
    lam_h = (
        forma_h[0] + forma_a[1]
    ) / 2

    lam_a = (
        forma_a[0] + forma_h[1]
    ) / 2

    # Avantaj moderat pentru teren propriu.
    lam_h *= 1.06

    lam_h = max(0.15, min(4.0, lam_h))
    lam_a = max(0.15, min(4.0, lam_a))

    probabilitati = calculeaza_probabilitati(
        lam_h,
        lam_a
    )

    return {
        "gazde": gazde,
        "oaspeti": oaspeti,
        "data": dt,
        "lambda_h": lam_h,
        "lambda_a": lam_a,
        "prob": probabilitati,
        "istoric_h": forma_h[2],
        "istoric_a": forma_a[2]
    }


# ==========================================
# API-FOOTBALL - OPTIONAL PENTRU LIVE
# ==========================================

def api_live(api_key):
    headers = {
        "x-apisports-key": api_key
    }

    r = requests.get(
        f"{FOOTBALL_API}/fixtures",
        headers=headers,
        params={"live": "all"},
        timeout=25
    )

    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(
            "API-FOOTBALL a trimis un raspuns invalid."
        )

    if r.status_code != 200:
        raise RuntimeError(
            f"API-FOOTBALL HTTP {r.status_code}: {data}"
        )

    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))

    return data.get("response", [])


# ==========================================
# INTERFATA
# ==========================================

st.title("⚽ FOOTBALL AI PRO")

st.caption(
    "Analiza statistica a meciurilor de fotbal "
    "si estimari de probabilitate."
)

st.info(
    "Meciurile si predictiile normale folosesc "
    "sursa gratuita OpenLigaDB. Nu este necesara "
    "cheia API-FOOTBALL pentru aceasta sectiune."
)


tab1, tab2, tab3 = st.tabs([
    "MECIURI SI PREDICTII",
    "LIVE",
    "ANALIZA MANUALA"
])


# ==========================================
# TAB 1 - MECIURI SI PREDICTII
# ==========================================

with tab1:

    st.header("Campionate si predictii")

    sezon = st.selectbox(
        "Alege sezonul",
        [2026, 2025, 2024, 2023, 2022],
        index=0
    )

    if st.button(
        "INCARCA CAMPIONATELE",
        type="primary"
    ):
        try:
            st.cache_data.clear()

            ligi = incarca_campionate(sezon)

            st.session_state["ligi"] = ligi
            st.session_state["sezon"] = sezon

        except Exception as e:
            st.error(
                f"Nu pot incarca campionatele: {e}"
            )

    ligi = st.session_state.get(
        "ligi",
        pd.DataFrame()
    )

    if not ligi.empty:

        st.success(
            f"Au fost gasite {len(ligi)} campionate."
        )

        liga = st.selectbox(
            "Selecteaza campionatul",
            ligi.to_dict("records"),
            format_func=lambda x: x["Campionat"],
            key="liga_selectata"
        )

        if st.button(
            "INCARCA MECIURILE",
            type="primary"
        ):

            try:
                with st.spinner(
                    "Incarc meciurile campionatului..."
                ):
                    meciuri = incarca_meciuri(
                        liga["Cod"],
                        liga["Sezon"]
                    )

                st.session_state["meciuri_liga"] = meciuri
                st.session_state["cod_liga"] = liga["Cod"]

                st.success(
                    f"Am incarcat {len(meciuri)} meciuri."
                )

            except Exception as e:
                st.error(
                    f"Eroare la incarcarea meciurilor: {e}"
                )

    meciuri = st.session_state.get(
        "meciuri_liga",
        []
    )

    if meciuri:

        acum = datetime.now(BUCHAREST)

        viitoare = []

        for meci in meciuri:
            dt = data_meci(meci)

            if dt is None:
                continue

            if dt > acum and scor_final(meci) is None:
                gazde, oaspeti = nume_echipe(meci)

                viitoare.append({
                    "Meci": f"{gazde} - {oaspeti}",
                    "Data": dt.strftime("%d.%m.%Y %H:%M"),
                    "Obiect": meci
                })

        viitoare.sort(
            key=lambda x: x["Data"]
        )

        st.subheader("Meciuri viitoare")

        if viitoare:

            tabel = pd.DataFrame([
                {
                    "Data": x["Data"],
                    "Meci": x["Meci"]
                }
                for x in viitoare
            ])

            st.dataframe(
                tabel,
                use_container_width=True,
                hide_index=True
            )

            optiuni = {
                f'{x["Data"]} | {x["Meci"]}': x["Obiect"]
                for x in viitoare
            }

            ales = st.selectbox(
                "Alege meciul pentru analiza",
                list(optiuni.keys())
            )

            if st.button(
                "ANALIZEAZA MECIUL",
                type="primary"
            ):

                try:
                    rezultat = analizeaza_meci(
                        optiuni[ales],
                        meciuri
                    )

                    if rezultat is None:
                        st.warning(
                            "Nu exista minimum 3 meciuri "
                            "istorice pentru ambele echipe."
                        )

                    else:
                        p = rezultat["prob"]

                        st.subheader(
                            rezultat["gazde"]
                            + " - "
                            + rezultat["oaspeti"]
                        )

                        st.write(
                            "Goluri estimate: "
                            f'**{rezultat["lambda_h"]:.2f} - '
                            f'{rezultat["lambda_a"]:.2f}**'
                        )

                        c1, c2, c3 = st.columns(3)

                        c1.metric(
                            "1 - Gazde",
                            f'{p["1"] * 100:.1f}%'
                        )

                        c2.metric(
                            "X - Egal",
                            f'{p["X"] * 100:.1f}%'
                        )

                        c3.metric(
                            "2 - Oaspeti",
                            f'{p["2"] * 100:.1f}%'
                        )

                        st.subheader("Piete statistice")

                        piete = [
                            "GG",
                            "NG",
                            "Peste 1.5",
                            "Sub 1.5",
                            "Peste 2.5",
                            "Sub 2.5",
                            "Peste 3.5",
                            "Sub 3.5"
                        ]

                        tabel_piete = pd.DataFrame([
                            {
                                "Piata": piata,
                                "Probabilitate": (
                                    f'{p[piata] * 100:.1f}%'
                                )
                            }
                            for piata in piete
                        ])

                        st.dataframe(
                            tabel_piete,
                            use_container_width=True,
                            hide_index=True
                        )

                        st.subheader("Scoruri estimate")

                        tabel_scoruri = pd.DataFrame([
                            {
                                "Scor": f"{h}-{a}",
                                "Probabilitate": (
                                    f"{prob * 100:.1f}%"
                                )
                            }
                            for prob, h, a in p["scoruri"]
                        ])

                        st.dataframe(
                            tabel_scoruri,
                            use_container_width=True,
                            hide_index=True
                        )

                        st.caption(
                            "Istoric: "
                            f'{rezultat["istoric_h"]} meciuri gazde / '
                            f'{rezultat["istoric_a"]} meciuri oaspeti.'
                        )

                except Exception as e:
                    st.error(
                        f"Eroare la analiza: {e}"
                    )

            # Export lista meciuri viitoare
            st.download_button(
                "DESCARCA MECIURILE CSV",
                data=tabel.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name="football_ai_pro_meciuri.csv",
                mime="text/csv"
            )

        else:
            st.info(
                "Nu sunt meciuri viitoare in acest campionat "
                "pentru sezonul ales."
            )


# ==========================================
# TAB 2 - LIVE
# ==========================================

with tab2:

    st.header("🔴 LIVE PREDICTIONS")

    st.caption(
        "Fluxul LIVE foloseste API-FOOTBALL. "
        "Este separat de sursa gratuita OpenLigaDB."
    )

    api_key = st.text_input(
        "Cheie API-FOOTBALL (optional)",
        type="password",
        key="live_api_key"
    )

    st.caption(
        "Nu introduce cheia in cod si nu o publica pe GitHub."
    )

    if st.button(
        "ACTUALIZEAZA MECIURILE LIVE",
        type="primary"
    ):

        if not api_key:
            st.warning(
                "Pentru scoruri LIVE este necesara o cheie "
                "API-FOOTBALL cu acces si cereri disponibile."
            )

        else:
            try:
                with st.spinner(
                    "Preiau meciurile LIVE..."
                ):
                    live = api_live(api_key)

                st.session_state["live_meciuri"] = live

            except Exception as e:
                st.error(
                    "Nu pot prelua LIVE: " + str(e)
                )

    live = st.session_state.get(
        "live_meciuri",
        []
    )

    if live:

        randuri = []

        for m in live:
            home = m.get("teams", {}).get("home", {})
            away = m.get("teams", {}).get("away", {})
            goals = m.get("goals", {})
            fixture = m.get("fixture", {})
            status = fixture.get("status", {})

            randuri.append({
                "Campionat": m.get("league", {}).get("name", ""),
                "Meci": (
                    f'{home.get("name", "")} - '
                    f'{away.get("name", "")}'
                ),
                "Scor": (
                    f'{goals.get("home", 0)} - '
                    f'{goals.get("away", 0)}'
                ),
                "Minut": (
                    str(status.get("elapsed") or "-") + "'"
                ),
                "Status": status.get("long", "")
            })

        st.success(
            f"Au fost gasite {len(live)} meciuri LIVE."
        )

        st.dataframe(
            pd.DataFrame(randuri),
            use_container_width=True,
            hide_index=True
        )

        st.info(
            "Scorurile LIVE sunt afisate din API. "
            "Nu afisez probabilitati LIVE daca nu exista "
            "date statistice suficiente pentru un calcul corect."
        )

    else:
        st.info(
            "Apasa ACTUALIZEAZA MECIURILE LIVE in timpul "
            "desfasurarii meciurilor."
        )


# ==========================================
# TAB 3 - ANALIZA MANUALA
# ==========================================

with tab3:

    st.header("Analiza manuala")

    c1, c2 = st.columns(2)

    with c1:
        nume_h = st.text_input(
            "Echipa gazda",
            "Gazde"
        )

        goluri_h = st.number_input(
            "Media golurilor marcate de gazde",
            min_value=0.0,
            max_value=5.0,
            value=1.4,
            step=0.1
        )

        primite_h = st.number_input(
            "Media golurilor primite de gazde",
            min_value=0.0,
            max_value=5.0,
            value=1.1,
            step=0.1
        )

    with c2:
        nume_a = st.text_input(
            "Echipa oaspete",
            "Oaspeti"
        )

        goluri_a = st.number_input(
            "Media golurilor marcate de oaspeti",
            min_value=0.0,
            max_value=5.0,
            value=1.2,
            step=0.1
        )

        primite_a = st.number_input(
            "Media golurilor primite de oaspeti",
            min_value=0.0,
            max_value=5.0,
            value=1.3,
            step=0.1
        )

    if st.button(
        "CALCULEAZA ANALIZA MANUALA",
        type="primary"
    ):

        lam_h = max(
            0.15,
            (goluri_h + primite_a) / 2
        )

        lam_a = max(
            0.15,
            (goluri_a + primite_h) / 2
        )

        p = calculeaza_probabilitati(
            lam_h,
            lam_a
        )

        st.subheader(
            nume_h + " - " + nume_a
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "1",
            f'{p["1"] * 100:.1f}%'
        )

        c2.metric(
            "X",
            f'{p["X"] * 100:.1f}%'
        )

        c3.metric(
            "2",
            f'{p["2"] * 100:.1f}%'
        )

        st.write(
            f'GG: **{p["GG"] * 100:.1f}%**'
        )

        st.write(
            f'Peste 2.5: **{p["Peste 2.5"] * 100:.1f}%**'
        )

        st.write(
            f'Goluri estimate: **{lam_h:.2f} - {lam_a:.2f}**'
        )


# ==========================================
# FINAL
# ==========================================

st.divider()

st.caption(
    "FOOTBALL AI PRO | Estimari statistice orientative. "
    "Probabilitatile nu garanteaza rezultatele."
    )
                
