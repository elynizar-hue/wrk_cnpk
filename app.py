"""
Dashboard Canpack - Surveillance de l'isolement electrique
3 armoires : Body Maker, Zone Laveuse, LSM (Vernissage)

Lancement :  streamlit run app.py
Necessite un broker MQTT accessible (le meme que celui utilise par Node-RED).
"""
import os
import tempfile
import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from db import get_connection, init_db
from mqtt_listener import demarrer_listener, ARMOIRES
from report import generer_rapport_pdf

st.set_page_config(
    page_title="Canpack - Surveillance Isolement",
    page_icon="⚡",
    layout="wide",
)

COULEURS_STATUT = {"normal": "#2ECC71", "PRECOCE": "#F39C12", "CRITIQUE": "#E74C3C"}


# ---- Demarrage du listener MQTT en arriere-plan (une seule fois par process) ----
@st.cache_resource
def _listener_singleton():
    init_db()
    return demarrer_listener()


_listener_singleton()


# ---- Fonctions de lecture des donnees ----
def charger_dernieres_mesures():
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT armoire, courant_mA, moyenne, statut, horodatage
        FROM mesures
        WHERE id IN (SELECT MAX(id) FROM mesures GROUP BY armoire)
        """,
        conn,
    )
    conn.close()
    return df


def charger_historique(armoire, depuis, jusqu_a):
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT horodatage, courant_mA, moyenne, statut
        FROM mesures
        WHERE armoire = ? AND horodatage BETWEEN ? AND ?
        ORDER BY horodatage ASC
        """,
        conn,
        params=(armoire, depuis, jusqu_a),
    )
    conn.close()
    if not df.empty:
        df["horodatage"] = pd.to_datetime(df["horodatage"])
    return df


def charger_alertes(limite=100):
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT horodatage, armoire, niveau, valeur_mA FROM alertes ORDER BY id DESC LIMIT ?",
        conn,
        params=(limite,),
    )
    conn.close()
    return df


def calculer_prediction(df, seuil_critique):
    """Regression lineaire simple sur les derniers points -> tendance + temps estime."""
    if len(df) < 4:
        return "Donnees insuffisantes pour une prediction", "#888888"

    recent = df.tail(12).copy()
    recent["minutes"] = (recent["horodatage"] - recent["horodatage"].iloc[0]).dt.total_seconds() / 60
    x = recent["minutes"].values
    y = recent["moyenne"].values
    n = len(x)
    pente = (n * (x * y).sum() - x.sum() * y.sum()) / (n * (x * x).sum() - x.sum() ** 2 + 1e-9)

    derniere_valeur = y[-1]
    if pente > 0.5:
        restant = seuil_critique - derniere_valeur
        minutes_restantes = restant / pente if pente > 0 else None
        if minutes_restantes and 0 < minutes_restantes < 1440:
            return f"Hausse (+{pente:.2f} mA/min) - seuil critique estime dans ~{minutes_restantes:.0f} min", "#F39C12"
        return f"Hausse legere (+{pente:.2f} mA/min), pas d'echeance critique estimee", "#F39C12"
    elif pente < -0.5:
        return f"Tendance a la baisse ({pente:.2f} mA/min)", "#2ECC71"
    return "Stable", "#2ECC71"


# ---- Sidebar ----
st.sidebar.title("⚡ Canpack - Isolement")
st.sidebar.markdown("Surveillance continue du courant de fuite")

plage = st.sidebar.selectbox(
    "Periode de l'historique",
    ["Dernière heure", "Dernières 24h", "Derniers 7 jours", "Tout"],
    index=1,
)
plage_deltas = {
    "Dernière heure": timedelta(hours=1),
    "Dernières 24h": timedelta(hours=24),
    "Derniers 7 jours": timedelta(days=7),
    "Tout": timedelta(days=3650),
}
depuis = (datetime.utcnow() - plage_deltas[plage]).isoformat()
jusqu_a = datetime.utcnow().isoformat()

rafraichissement = st.sidebar.slider("Rafraîchissement (secondes)", 3, 30, 5)
auto_refresh = st.sidebar.checkbox("Rafraîchissement automatique", value=True)

st.sidebar.divider()
st.sidebar.caption("Statuts")
for nom, couleur in COULEURS_STATUT.items():
    st.sidebar.markdown(
        f"<span style='color:{couleur}'>●</span> {nom}", unsafe_allow_html=True
    )

# ---- En-tete / Vue d'ensemble ----
st.title("Surveillance de l'isolement électrique")
st.caption("Body Maker · Zone Laveuse · LSM (Vernissage) — mesure du courant de fuite")

dernieres = charger_dernieres_mesures()
cols = st.columns(3)
for i, nom in enumerate(ARMOIRES.keys()):
    with cols[i]:
        ligne = dernieres[dernieres["armoire"] == nom]
        if ligne.empty:
            st.metric(nom, "—", help="En attente de données")
        else:
            row = ligne.iloc[0]
            couleur = COULEURS_STATUT.get(row["statut"], "#888888")
            st.markdown(
                f"""
                <div style="border:1px solid #333; border-radius:10px; padding:16px; text-align:center;">
                    <div style="font-size:14px; color:#999;">{nom}</div>
                    <div style="font-size:32px; font-weight:bold;">{row['moyenne']:.1f} mA</div>
                    <div style="color:{couleur}; font-weight:bold;">{row['statut']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.divider()

# ---- Onglets par armoire ----
onglets = st.tabs(list(ARMOIRES.keys()) + ["Alertes & Journal", "Rapport PDF"])

for i, nom in enumerate(ARMOIRES.keys()):
    with onglets[i]:
        _, seuil_precoce, seuil_critique = ARMOIRES[nom]
        df = charger_historique(nom, depuis, jusqu_a)

        if df.empty:
            st.info("Aucune donnée sur cette période pour le moment.")
        else:
            texte_pred, couleur_pred = calculer_prediction(df, seuil_critique)
            st.markdown(
                f"<div style='padding:8px; border-left:4px solid {couleur_pred};'>"
                f"<b>Prédiction :</b> {texte_pred}</div>",
                unsafe_allow_html=True,
            )
            st.write("")

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["horodatage"], y=df["courant_mA"],
                mode="lines", name="Valeur instantanée",
                line=dict(color="#888888", width=1),
            ))
            fig.add_trace(go.Scatter(
                x=df["horodatage"], y=df["moyenne"],
                mode="lines", name="Moyenne glissante",
                line=dict(color="#1F77B4", width=2),
            ))
            fig.add_hline(y=seuil_precoce, line_dash="dot", line_color="#F39C12",
                          annotation_text="Seuil précoce")
            fig.add_hline(y=seuil_critique, line_dash="dot", line_color="#E74C3C",
                          annotation_text="Seuil critique")
            fig.update_layout(
                height=420,
                margin=dict(l=20, r=20, t=30, b=20),
                xaxis_title="", yaxis_title="Courant de fuite (mA)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("Voir les données brutes"):
                st.dataframe(df.sort_values("horodatage", ascending=False), use_container_width=True)
                st.download_button(
                    "Télécharger en CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    file_name=f"historique_{nom.replace(' ', '_')}.csv",
                    mime="text/csv",
                )

with onglets[-2]:
    st.subheader("Journal des alertes")
    alertes = charger_alertes()
    if alertes.empty:
        st.info("Aucune alerte enregistrée pour le moment.")
    else:
        def _colorer(row):
            couleur = "#E74C3C" if row["niveau"] == "CRITIQUE" else "#F39C12"
            return [f"color: {couleur}"] * len(row)

        st.dataframe(alertes.style.apply(_colorer, axis=1), use_container_width=True)
        st.download_button(
            "Télécharger le journal en CSV",
            alertes.to_csv(index=False).encode("utf-8"),
            file_name="journal_alertes.csv",
            mime="text/csv",
        )

        fig_repartition = px.pie(alertes, names="armoire", title="Répartition des alertes par armoire")
        st.plotly_chart(fig_repartition, use_container_width=True)

with onglets[-1]:
    st.subheader("Générer un rapport PDF")
    st.write(
        "Le rapport reprend le résumé des 3 armoires, un graphe par armoire "
        "avec les seuils, et le journal des alertes — utile pour un point "
        "d'avancement ou en annexe de la soutenance."
    )
    periode_rapport = st.selectbox(
        "Période à couvrir dans le rapport",
        ["Dernières 24h", "Derniers 7 jours", "Dernières 30 jours"],
        index=0,
    )
    heures_rapport = {"Dernières 24h": 24, "Derniers 7 jours": 24 * 7, "Dernières 30 jours": 24 * 30}[periode_rapport]

    if st.button("Générer le rapport"):
        with st.spinner("Génération du rapport en cours..."):
            chemin_pdf = os.path.join(tempfile.gettempdir(), "rapport_canpack_isolement.pdf")
            generer_rapport_pdf(chemin_pdf, depuis_heures=heures_rapport)
            with open(chemin_pdf, "rb") as f:
                donnees_pdf = f.read()
        st.success("Rapport généré.")
        st.download_button(
            "Télécharger le rapport PDF",
            donnees_pdf,
            file_name=f"rapport_canpack_isolement_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf",
        )

# ---- Rafraîchissement automatique ----
if auto_refresh:
    time.sleep(rafraichissement)
    st.rerun()
