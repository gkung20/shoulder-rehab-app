"""Automated clinical PDF audit report generator for shoulder rehabilitation.

Generates a formatted 1-2 page clinical summary document for physiotherapists
and orthopedic practitioners, including:
1. Patient metadata and prescription parameters.
2. Executive KPI summary (success rate, average ROM, repetition count).
3. Embedded high-resolution Matplotlib graphs (ROM curve & error breakdown).
4. Full repetition audit log with flagged compensations.
5. Legal medical disclaimer and practitioner sign-off block.
"""

from datetime import datetime
import io
from pathlib import Path
from typing import Optional, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.rules_engine import SessionSummary


def _create_clinical_charts(
    session_summary: SessionSummary,
    target_min: float,
    target_max: float,
) -> io.BytesIO:
    """Generate dual clinical diagnostic graphs in an in-memory PNG buffer.

    - Left: Peak abduction angles per repetition vs therapeutic target corridor.
    - Right: Frequency distribution of detected motor compensations.
    """
    fig, (ax_rom, ax_err) = plt.subplots(1, 2, figsize=(7.2, 2.7), dpi=180)

    evals = session_summary.evaluations
    rep_indices = [e.rep_index for e in evals]
    peak_angles = [
        e.metrics.peak_abduction_deg if e.metrics else 0.0 for e in evals
    ]
    correct_mask = [e.is_correct for e in evals]

    # --- 1. Range of Motion Plot ---
    ax_rom.axhspan(target_min, target_max, color="#c8e6c9", alpha=0.65, label="Zone Cible Prescrite")
    ax_rom.axhline(target_min, color="#2e7d32", linestyle="--", linewidth=1.0)
    ax_rom.axhline(target_max, color="#2e7d32", linestyle="--", linewidth=1.0)

    if rep_indices:
        # Plot connecting line
        ax_rom.plot(rep_indices, peak_angles, color="#1976d2", linewidth=1.5, alpha=0.7, zorder=2)

        # Plot individual points colored by status
        for idx, ang, ok in zip(rep_indices, peak_angles, correct_mask):
            pt_color = "#2e7d32" if ok else "#d32f2f"
            pt_marker = "o" if ok else "X"
            ax_rom.scatter(idx, ang, color=pt_color, s=55, marker=pt_marker, zorder=3)

        ax_rom.set_xticks(rep_indices)
        ax_rom.set_xlim(min(rep_indices) - 0.5, max(rep_indices) + 0.5)
    else:
        ax_rom.text(0.5, 0.5, "Aucune répétition enregistrée", ha="center", va="center", transform=ax_rom.transAxes)

    ax_rom.set_title("Amplitude Maximale par Répétition", fontsize=9.5, fontweight="bold", pad=6)
    ax_rom.set_xlabel("Répétition (#)", fontsize=8)
    ax_rom.set_ylabel("Abduction (°)", fontsize=8)
    ax_rom.set_ylim(0, max(130.0, max(peak_angles, default=90.0) + 15.0))
    ax_rom.grid(True, linestyle=":", alpha=0.5)
    ax_rom.tick_params(labelsize=7.5)

    # --- 2. Error Frequency Distribution ---
    errors = session_summary.get_most_frequent_errors(top_n=5)
    if errors:
        cat_names = [e[0] for e in reversed(errors)]
        counts = [e[1] for e in reversed(errors)]
        y_pos = np.arange(len(cat_names))

        bars = ax_err.barh(y_pos, counts, color="#e57373", edgecolor="#c62828", height=0.55)
        ax_err.set_yticks(y_pos)
        ax_err.set_yticklabels(cat_names, fontsize=7.5)
        ax_err.set_xlabel("Occurrences", fontsize=8)
        ax_err.set_title("Compensations Motrices Fréquentes", fontsize=9.5, fontweight="bold", pad=6)
        ax_err.grid(axis="x", linestyle=":", alpha=0.5)
        ax_err.tick_params(labelsize=7.5)

        # Value labels on bars
        for bar in bars:
            w = bar.get_width()
            ax_err.text(w + 0.1, bar.get_y() + bar.get_height() / 2, f"{int(w)}", va="center", fontsize=7.5)
        ax_err.set_xlim(0, max(counts) + 1.2)
    else:
        ax_err.text(0.5, 0.5, "Aucune compensation\n(Séance parfaite)", ha="center", va="center", transform=ax_err.transAxes, color="#2e7d32", fontweight="bold")
        ax_err.set_title("Compensations Motrices", fontsize=9.5, fontweight="bold", pad=6)
        ax_err.axis("off")

    fig.tight_layout()
    img_buffer = io.BytesIO()
    fig.savefig(img_buffer, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    img_buffer.seek(0)
    return img_buffer


def generate_clinical_pdf_report(
    session_summary: SessionSummary,
    arm: str,
    target_min: float = 80.0,
    target_max: float = 100.0,
    patient_id: str = "PATIENT-UNIV-01",
    output_path: Optional[Union[str, Path]] = None,
) -> bytes:
    """Generate a publication-grade clinical PDF session report.

    Args:
        session_summary: Aggregated SessionSummary containing RepetitionEvaluations.
        arm: Active arm ('right' or 'left').
        target_min: Prescribed minimum abduction angle.
        target_max: Prescribed maximum abduction angle.
        patient_id: Anonymized patient / session identifier.
        output_path: Optional filesystem path to save the generated PDF.

    Returns:
        Raw bytes of the compiled PDF document.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=32,
        bottomMargin=32,
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    style_title = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        textColor=colors.HexColor("#0d47a1"),
        alignment=0,
    )
    style_sub = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#546e7a"),
    )
    style_meta_label = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#263238"),
    )
    style_meta_val = ParagraphStyle(
        "MetaVal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#37474f"),
    )
    style_tbl_header = ParagraphStyle(
        "TblH",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1,
    )
    style_tbl_cell = ParagraphStyle(
        "TblC",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        alignment=1,
    )
    style_disclaimer = ParagraphStyle(
        "Discl",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#c62828"),
        alignment=1,
    )

    story = []

    # 1. Header & Title Block
    now_str = datetime.now().strftime("%d/%m/%Y à %H:%M")
    story.append(Paragraph("BILAN DE KINÉSITHÉRAPIE VIRTUELLE ASSISTÉE", style_title))
    story.append(Paragraph("Assistant Numérique d'Abduction Active de l'Épaule — Évaluation Biomécanique", style_sub))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0d47a1"), spaceAfter=10))

    # 2. Metadata Grid Table
    arm_french = "Bras Droit (Ipsilatéral)" if arm.lower() == "right" else "Bras Gauche (Ipsilatéral)"
    meta_data = [
        [
            Paragraph("<b>Identifiant Patient :</b>", style_meta_label),
            Paragraph(patient_id, style_meta_val),
            Paragraph("<b>Date de la Séance :</b>", style_meta_label),
            Paragraph(now_str, style_meta_val),
        ],
        [
            Paragraph("<b>Membre Évalué :</b>", style_meta_label),
            Paragraph(arm_french, style_meta_val),
            Paragraph("<b>Objectif Thérapeutique :</b>", style_meta_label),
            Paragraph(f"Abduction [{target_min:.0f}° - {target_max:.0f}°]", style_meta_val),
        ],
    ]
    tbl_meta = Table(meta_data, colWidths=[115, 140, 115, 150])
    tbl_meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f7fa")),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd8dc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(tbl_meta)
    story.append(Spacer(1, 10))

    # 3. Key Performance Indicators (KPIs)
    total_reps = session_summary.total_repetitions
    correct_reps = session_summary.correct_repetitions
    success_rate = session_summary.success_rate_percent
    evals = session_summary.evaluations

    if evals:
        peak_angles = [e.metrics.peak_abduction_deg for e in evals if e.metrics]
        mean_rom = np.mean(peak_angles) if peak_angles else 0.0
    else:
        mean_rom = 0.0

    kpi_data = [
        [
            Paragraph("<b>Répétitions Totales</b>", style_meta_label),
            Paragraph("<b>Répétitions Conformes</b>", style_meta_label),
            Paragraph("<b>Taux de Réussite</b>", style_meta_label),
            Paragraph("<b>Amplitude Moyenne</b>", style_meta_label),
        ],
        [
            Paragraph(f"<font size=13 color='#0d47a1'><b>{total_reps}</b></font>", style_tbl_cell),
            Paragraph(f"<font size=13 color='#2e7d32'><b>{correct_reps}</b></font>", style_tbl_cell),
            Paragraph(f"<font size=13 color='#0d47a1'><b>{success_rate:.1f} %</b></font>", style_tbl_cell),
            Paragraph(f"<font size=13 color='#0d47a1'><b>{mean_rom:.1f} °</b></font>", style_tbl_cell),
        ]
    ]
    tbl_kpi = Table(kpi_data, colWidths=[130, 130, 130, 130])
    tbl_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f2fd")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#ffffff")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#90caf9")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl_kpi)
    story.append(Spacer(1, 10))

    # 4. Biomechanical Charts Image
    chart_buf = _create_clinical_charts(session_summary, target_min=target_min, target_max=target_max)
    chart_img = Image(chart_buf, width=520, height=195)
    story.append(chart_img)
    story.append(Spacer(1, 10))

    # 5. Repetition Audit Table
    story.append(Paragraph("<b>Détail Chronologique des Répétitions</b>", style_meta_label))
    story.append(Spacer(1, 4))

    table_rows = [
        [
            Paragraph("<b>#</b>", style_tbl_header),
            Paragraph("<b>Statut</b>", style_tbl_header),
            Paragraph("<b>ROM Max</b>", style_tbl_header),
            Paragraph("<b>Montée</b>", style_tbl_header),
            Paragraph("<b>Maintien</b>", style_tbl_header),
            Paragraph("<b>Descente</b>", style_tbl_header),
            Paragraph("<b>Anomalies & Remarques Cliniques</b>", style_tbl_header),
        ]
    ]

    for ev in evals[:10]:  # Up to 10 reps per page
        m = ev.metrics
        status_color = "#2e7d32" if ev.is_correct else "#c62828"
        status_text = f"<font color='{status_color}'><b>{ev.status_label}</b></font>"

        reasons_text = "; ".join(ev.reasons) if ev.reasons else "Conforme aux prescriptions"
        if len(reasons_text) > 60:
            reasons_text = reasons_text[:57] + "..."

        table_rows.append([
            Paragraph(str(ev.rep_index), style_tbl_cell),
            Paragraph(status_text, style_tbl_cell),
            Paragraph(f"{m.peak_abduction_deg:.1f}°" if m else "-", style_tbl_cell),
            Paragraph(f"{m.concentric_duration_sec:.1f}s" if m else "-", style_tbl_cell),
            Paragraph(f"{m.hold_duration_sec:.1f}s" if m else "-", style_tbl_cell),
            Paragraph(f"{m.eccentric_duration_sec:.1f}s" if m else "-", style_tbl_cell),
            Paragraph(reasons_text, style_tbl_cell),
        ])

    tbl_reps = Table(table_rows, colWidths=[24, 66, 52, 45, 45, 48, 240])
    tbl_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d47a1")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd8dc")),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    # Alternating row colors
    for r in range(1, len(table_rows)):
        bg = colors.HexColor("#fbfcfd") if r % 2 == 0 else colors.HexColor("#ffffff")
        tbl_style.append(("BACKGROUND", (0, r), (-1, r), bg))

    tbl_reps.setStyle(TableStyle(tbl_style))
    story.append(tbl_reps)
    story.append(Spacer(1, 12))

    # 6. Practitioner Observations & Signature Block
    sign_data = [
        [
            Paragraph("<b>Observations du Kinésithérapeute :</b><br/><br/><br/>", style_meta_label),
            Paragraph("<b>Visa & Signature du Praticien :</b><br/><br/><br/>", style_meta_label),
        ]
    ]
    tbl_sign = Table(sign_data, colWidths=[330, 190])
    tbl_sign.setStyle(TableStyle([
        ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor("#b0bec5")),
        ("BOX", (1, 0), (1, 0), 0.5, colors.HexColor("#b0bec5")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl_sign)
    story.append(Spacer(1, 10))

    # 7. Medical Disclaimer Footer
    story.append(Paragraph(
        "AVERTISSEMENT : Ce document est issu d'un prototype universitaire expérimental (Santé Numérique). "
        "Il ne se substitue pas à l'examen clinique direct réalisé par un professionnel de santé diplômé d'État.",
        style_disclaimer,
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pdf_bytes)

    return pdf_bytes
