"""
Generation d'un rapport PDF (graphes + tableau d'alertes) a partir de
l'historique SQLite - utile pour la soutenance ou un point d'avancement.

Usage direct :  python report.py
Ou via le bouton "Generer le rapport PDF" dans app.py
"""
import io
import os
import tempfile
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak,
)

from db import get_connection
from mqtt_listener import ARMOIRES

COULEUR_NORMAL = colors.HexColor("#2ECC71")
COULEUR_PRECOCE = colors.HexColor("#F39C12")
COULEUR_CRITIQUE = colors.HexColor("#E74C3C")


def _charger_historique(armoire, depuis_heures=24):
    conn = get_connection()
    depuis = (datetime.utcnow() - timedelta(hours=depuis_heures)).isoformat()
    df = pd.read_sql_query(
        """
        SELECT horodatage, courant_mA, moyenne, statut
        FROM mesures
        WHERE armoire = ? AND horodatage >= ?
        ORDER BY horodatage ASC
        """,
        conn, params=(armoire, depuis),
    )
    conn.close()
    if not df.empty:
        df["horodatage"] = pd.to_datetime(df["horodatage"])
    return df


def _charger_alertes(depuis_heures=24):
    conn = get_connection()
    depuis = (datetime.utcnow() - timedelta(hours=depuis_heures)).isoformat()
    df = pd.read_sql_query(
        """
        SELECT horodatage, armoire, niveau, valeur_mA
        FROM alertes
        WHERE horodatage >= ?
        ORDER BY horodatage DESC
        """,
        conn, params=(depuis,),
    )
    conn.close()
    return df


def _tracer_graphe(df, nom, seuil_precoce, seuil_critique):
    """Retourne un buffer PNG pret a etre embarque dans le PDF."""
    fig, ax = plt.subplots(figsize=(16, 6))
    if not df.empty:
        ax.plot(df["horodatage"], df["courant_mA"], color="#AAAAAA", linewidth=0.8, label="Valeur instantanée")
        ax.plot(df["horodatage"], df["moyenne"], color="#1F77B4", linewidth=1.8, label="Moyenne glissante")
    ax.axhline(seuil_precoce, color="#F39C12", linestyle="--", linewidth=1, label="Seuil précoce")
    ax.axhline(seuil_critique, color="#E74C3C", linestyle="--", linewidth=1, label="Seuil critique")
    ax.set_title(f"{nom} - Courant de fuite (mA)")
    ax.set_ylabel("mA")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


def generer_rapport_pdf(chemin_sortie, depuis_heures=24):
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle("TitreRapport", parent=styles["Title"], fontSize=20)
    style_section = ParagraphStyle("Section", parent=styles["Heading2"], spaceBefore=14, spaceAfter=8)
    style_normal = styles["Normal"]

    doc = SimpleDocTemplate(
        chemin_sortie, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
    )
    story = []

    # --- Page de garde ---
    story.append(Paragraph("Rapport de surveillance de l'isolement électrique", style_titre))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Canpack — Body Maker / Zone Laveuse / LSM (Vernissage)", styles["Heading3"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — "
        f"période couverte : dernières {depuis_heures} heures",
        style_normal,
    ))
    story.append(Spacer(1, 20))

    # --- Résumé par armoire ---
    story.append(Paragraph("Résumé", style_section))
    lignes_resume = [["Armoire", "Dernière valeur (mA)", "Statut", "Nb alertes (période)"]]
    alertes_globales = _charger_alertes(depuis_heures)

    for nom, (topic, seuil_precoce, seuil_critique) in ARMOIRES.items():
        df = _charger_historique(nom, depuis_heures)
        derniere = f"{df['moyenne'].iloc[-1]:.1f}" if not df.empty else "—"
        statut = df["statut"].iloc[-1] if not df.empty else "—"
        nb_alertes = len(alertes_globales[alertes_globales["armoire"] == nom]) if not alertes_globales.empty else 0
        lignes_resume.append([nom, derniere, statut, str(nb_alertes)])

    table_resume = Table(lignes_resume, colWidths=[5.5 * cm, 4 * cm, 3 * cm, 4 * cm])
    table_resume.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
    ]))
    story.append(table_resume)
    story.append(PageBreak())

    # --- Une section par armoire avec graphe ---
    for nom, (topic, seuil_precoce, seuil_critique) in ARMOIRES.items():
        story.append(Paragraph(nom, style_section))
        df = _charger_historique(nom, depuis_heures)

        if df.empty:
            story.append(Paragraph("Aucune donnée disponible sur cette période.", style_normal))
        else:
            buf = _tracer_graphe(df, nom, seuil_precoce, seuil_critique)
            story.append(Image(buf, width=16 * cm, height=6 * cm))
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"Seuils configurés — précoce : {seuil_precoce} mA, critique : {seuil_critique} mA. "
                f"Valeur moyenne sur la période : {df['moyenne'].mean():.1f} mA, "
                f"maximum observé : {df['moyenne'].max():.1f} mA.",
                style_normal,
            ))
        story.append(Spacer(1, 16))

    story.append(PageBreak())

    # --- Journal des alertes ---
    story.append(Paragraph("Journal des alertes (période sélectionnée)", style_section))
    if alertes_globales.empty:
        story.append(Paragraph("Aucune alerte enregistrée sur cette période.", style_normal))
    else:
        lignes_alertes = [["Horodatage", "Armoire", "Niveau", "Valeur (mA)"]]
        for _, r in alertes_globales.iterrows():
            lignes_alertes.append([
                r["horodatage"].replace("T", " ")[:19], r["armoire"], r["niveau"], f"{r['valeur_mA']:.1f}"
            ])

        table_alertes = Table(lignes_alertes, colWidths=[5 * cm, 5 * cm, 3 * cm, 3.5 * cm], repeatRows=1)
        style_table = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]
        for i, r in enumerate(alertes_globales.itertuples(), start=1):
            couleur = COULEUR_CRITIQUE if r.niveau == "CRITIQUE" else COULEUR_PRECOCE
            style_table.append(("TEXTCOLOR", (2, i), (2, i), couleur))
        table_alertes.setStyle(TableStyle(style_table))
        story.append(table_alertes)

    doc.build(story)
    return chemin_sortie


if __name__ == "__main__":
    chemin = os.path.join(tempfile.gettempdir(), "rapport_canpack_isolement.pdf")
    generer_rapport_pdf(chemin)
    print(f"Rapport genere : {chemin}")
