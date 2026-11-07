# FOOTBALL AI PRO

Aplicație Streamlit pentru analiză statistică fotbalistică folosind API-FOOTBALL v3.

## Instalare
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Publicare
În Streamlit Community Cloud:
- Repository: `Vitan756/FOOTBALL-AI-PRO`
- Branch: `main`
- Main file: `app.py`

Introdu cheia API-FOOTBALL în câmpul din bara laterală. Nu publica cheia în GitHub.

## Compatibilitate plan Free
Aplicația caută ultimele rezultate prin parametrii `from` și `to` pe endpoint-ul `fixtures`. Nu folosește parametrul `last`, indisponibil pe planul Free.

Modelul Poisson este simplificat și orientativ. Nu garantează rezultate și nu este un model profesional validat pentru pariuri.
