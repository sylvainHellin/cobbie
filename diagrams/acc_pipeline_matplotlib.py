"""Generate a research-paper-quality diagram of the ACC training pipeline."""

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np

# ── Layout constants ──────────────────────────────────────────────────
FIG_W, FIG_H = 10, 13
BOX_W, BOX_H = 2.0, 0.7
DIA_SIZE = 0.65  # diamond half-side

# Colours (grayscale-friendly)
COL_LLM = "#d9d9d9"
COL_PROC = "#f0f0f0"
COL_DEC = "#ffffff"
COL_IO = "#e8e8e8"
COL_STARTEND = "#bfbfbf"
EDGE_COL = "#333333"
FONT = "serif"

# ── Node positions (x, y) ────────────────────────────────────────────
positions = {
    "START":       (5.0, 12.0),
    "CREATE_TOOL": (5.0, 10.5),
    "VALIDATE":    (5.0, 9.0),
    "F1_CHECK":    (5.0, 7.5),
    "ASSESS":      (2.5, 6.0),
    "DECIDE":      (2.5, 4.5),
    "SAVE_TOOL":   (5.0, 3.0),
    "TEST_TOOL":   (5.0, 1.8),
    "END":         (5.0, 0.6),
}


def draw_rounded_box(ax, cx, cy, w, h, label, sublabel=None,
                     fc=COL_PROC, ec=EDGE_COL):
    box = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.08", fc=fc, ec=ec, lw=1.2, zorder=2,
    )
    ax.add_patch(box)
    if sublabel:
        ax.text(cx, cy + 0.08, label, ha="center", va="center",
                fontsize=9, fontfamily=FONT, fontweight="bold", zorder=3)
        ax.text(cx, cy - 0.16, sublabel, ha="center", va="center",
                fontsize=7, fontfamily=FONT, fontstyle="italic",
                color="#555555", zorder=3)
    else:
        ax.text(cx, cy, label, ha="center", va="center",
                fontsize=9, fontfamily=FONT, fontweight="bold", zorder=3)


def draw_stadium(ax, cx, cy, w, h, label, fc=COL_STARTEND, ec=EDGE_COL):
    box = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.15", fc=fc, ec=ec, lw=1.5, zorder=2,
    )
    ax.add_patch(box)
    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=9, fontfamily=FONT, fontweight="bold", zorder=3)


def draw_diamond(ax, cx, cy, s, label, sublabel=None,
                 fc=COL_DEC, ec=EDGE_COL):
    verts = np.array([
        [cx, cy + s], [cx + s * 1.3, cy],
        [cx, cy - s], [cx - s * 1.3, cy], [cx, cy + s],
    ])
    poly = plt.Polygon(verts, closed=True, fc=fc, ec=ec, lw=1.2, zorder=2)
    ax.add_patch(poly)
    if sublabel:
        ax.text(cx, cy + 0.1, label, ha="center", va="center",
                fontsize=8, fontfamily=FONT, fontweight="bold", zorder=3)
        ax.text(cx, cy - 0.15, sublabel, ha="center", va="center",
                fontsize=6.5, fontfamily=FONT, color="#555555", zorder=3)
    else:
        ax.text(cx, cy, label, ha="center", va="center",
                fontsize=8, fontfamily=FONT, fontweight="bold", zorder=3)


def arrow(ax, x1, y1, x2, y2, label=None, label_side="right"):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>", color=EDGE_COL, lw=1.2,
            connectionstyle="arc3,rad=0",
        ),
        zorder=1,
    )
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        offset = 0.15 if label_side == "right" else -0.15
        if abs(x2 - x1) > abs(y2 - y1):
            ax.text(mx, my + 0.15, label, ha="center", va="bottom",
                    fontsize=7, fontfamily=FONT, color="#444444", zorder=3)
        else:
            ax.text(mx + offset, my, label, ha="left" if label_side == "right" else "right",
                    va="center", fontsize=7, fontfamily=FONT,
                    color="#444444", zorder=3)


def arrow_curved(ax, x1, y1, x2, y2, label=None, rad=0.3):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>", color=EDGE_COL, lw=1.2,
            connectionstyle=f"arc3,rad={rad}",
        ),
        zorder=1,
    )
    if label:
        mx = (x1 + x2) / 2 - abs(rad) * 0.8
        my = (y1 + y2) / 2
        ax.text(mx - 0.1, my, label, ha="right", va="center",
                fontsize=7, fontfamily=FONT, color="#444444", zorder=3)


# ── Build figure ──────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.set_aspect("equal")
ax.axis("off")

p = positions

# Nodes
draw_stadium(ax, *p["START"], 1.6, 0.55, "START")
draw_rounded_box(ax, *p["CREATE_TOOL"], BOX_W, BOX_H,
                 "CREATE_TOOL", "create_helper_function", fc=COL_LLM)
draw_rounded_box(ax, *p["VALIDATE"], BOX_W, BOX_H,
                 "VALIDATE_TOOL", "train + val models", fc=COL_PROC)
draw_diamond(ax, *p["F1_CHECK"], DIA_SIZE, "F1 = 1.0?")
draw_rounded_box(ax, *p["ASSESS"], BOX_W, BOX_H,
                 "ASSESS", "assess_acc_tool", fc=COL_LLM)
draw_diamond(ax, *p["DECIDE"], DIA_SIZE, "DECIDE", "retries left?")
draw_rounded_box(ax, *p["SAVE_TOOL"], BOX_W, BOX_H, "SAVE_TOOL", fc=COL_PROC)
draw_rounded_box(ax, *p["TEST_TOOL"], BOX_W, BOX_H,
                 "TEST_TOOL", "test models", fc=COL_PROC)
draw_stadium(ax, *p["END"], 1.6, 0.55, "END")

# Straight arrows
arrow(ax, 5.0, 11.72, 5.0, 10.85)
arrow(ax, 5.0, 10.15, 5.0, 9.35)
arrow(ax, 5.0, 8.65, 5.0, 8.15)
arrow(ax, 5.0, 3.35, 5.0, 2.15, label="")
arrow(ax, 5.0, 1.45, 5.0, 0.88)

# F1 check → SAVE (Yes, right side)
arrow(ax, 5.0 + DIA_SIZE * 1.3, 7.5, 6.5, 7.5)
ax.annotate(
    "", xy=(6.5, 3.0), xytext=(6.5, 7.5),
    arrowprops=dict(arrowstyle="-|>", color=EDGE_COL, lw=1.2),
    zorder=1,
)
ax.text(6.65, 7.3, "Yes", fontsize=7, fontfamily=FONT, color="#444444")

# F1 check → ASSESS (No, left side)
arrow(ax, 5.0 - DIA_SIZE * 1.3, 7.5, 3.5, 7.5)
ax.annotate(
    "", xy=(2.5, 6.35), xytext=(3.5, 7.5),
    arrowprops=dict(arrowstyle="-|>", color=EDGE_COL, lw=1.2,
                    connectionstyle="arc3,rad=0.15"),
    zorder=1,
)
ax.text(3.1, 7.65, "No", fontsize=7, fontfamily=FONT, color="#444444")

# ASSESS → DECIDE
arrow(ax, 2.5, 5.65, 2.5, 5.15)

# DECIDE → CREATE_TOOL (retry loop – curved left)
arrow_curved(ax, 2.5 - DIA_SIZE * 1.3, 4.5, 5.0 - BOX_W / 2, 10.5,
             label="retry", rad=-0.4)

# DECIDE → SAVE_TOOL (exhausted)
ax.annotate(
    "", xy=(5.0 - BOX_W / 2, 3.0), xytext=(2.5 + DIA_SIZE * 1.3, 4.5),
    arrowprops=dict(arrowstyle="-|>", color=EDGE_COL, lw=1.2,
                    connectionstyle="arc3,rad=-0.15"),
    zorder=1,
)
ax.text(4.1, 3.95, "exhausted", fontsize=7, fontfamily=FONT, color="#444444")

# ── I/O annotations ──────────────────────────────────────────────────
io_x = 8.2
for i, txt in enumerate(["Rule context", "IFC models (splits)", "Ground truth GUIDs"]):
    y = 12.0 - i * 0.4
    ax.text(io_x, y, txt, fontsize=7, fontfamily=FONT, color="#666666",
            bbox=dict(boxstyle="round,pad=0.2", fc=COL_IO, ec="#aaaaaa", lw=0.8))
    ax.annotate(
        "", xy=(5.8, 12.0), xytext=(io_x - 0.1, y),
        arrowprops=dict(arrowstyle="-|>", color="#aaaaaa", lw=0.8,
                        connectionstyle="arc3,rad=0.1"),
        zorder=0,
    )

for txt, src_y in [("Saved Python tool", 3.0), ("MLflow metrics", 1.8)]:
    ax.text(io_x, src_y, txt, fontsize=7, fontfamily=FONT, color="#666666",
            bbox=dict(boxstyle="round,pad=0.2", fc=COL_IO, ec="#aaaaaa", lw=0.8))
    ax.annotate(
        "", xy=(io_x - 0.1, src_y), xytext=(6.0, src_y),
        arrowprops=dict(arrowstyle="-|>", color="#aaaaaa", lw=0.8),
        zorder=0,
    )

# ── Legend ─────────────────────────────────────────────────────────────
legend_items = [
    (COL_LLM, "LLM agent call"),
    (COL_PROC, "Deterministic step"),
    (COL_DEC, "Decision"),
]
for i, (col, lbl) in enumerate(legend_items):
    y = 0.5 - i * 0.35
    ax.add_patch(FancyBboxPatch(
        (0.3, y - 0.12), 0.35, 0.24,
        boxstyle="round,pad=0.04", fc=col, ec=EDGE_COL, lw=0.8))
    ax.text(0.85, y, lbl, fontsize=7, fontfamily=FONT, va="center")

# ── Title ─────────────────────────────────────────────────────────────
ax.text(5.0, 12.8, "ACC Training Pipeline", ha="center", va="center",
        fontsize=13, fontfamily=FONT, fontweight="bold")

fig.tight_layout(pad=0.5)
fig.savefig("diagrams/acc_pipeline_matplotlib.pdf", bbox_inches="tight", dpi=300)
fig.savefig("diagrams/acc_pipeline_matplotlib.png", bbox_inches="tight", dpi=300)
print("Saved diagrams/acc_pipeline_matplotlib.pdf and .png")
