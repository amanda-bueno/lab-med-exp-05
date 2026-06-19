from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_RESULTS = DATA_DIR / "raw_results.csv"
PROCESSED_RESULTS = DATA_DIR / "processed_results.csv"
STATISTICAL_RESULTS = DATA_DIR / "statistical_results.csv"
OUTPUT_DIR = ROOT / "report"
FIGURES_DIR = OUTPUT_DIR / "figures"

METRICS = ["response_time_ms", "response_size_bytes"]
METRIC_LABELS = {
    "response_time_ms": "tempo de resposta",
    "response_size_bytes": "tamanho da resposta",
}
METRIC_SHORT = {
    "response_time_ms": "Tempo",
    "response_size_bytes": "Tamanho",
}
SCENARIO_LABELS = {
    "simple_user": "simple user",
    "user_list": "user list",
    "nested_data": "nested data",
    "post_titles": "post titles",
    "full_profile": "full profile",
}
COLORS = {
    "primary": "#0D9488",
    "primary_dark": "#0F766E",
    "secondary": "#F97316",
    "success": "#10B981",
    "warning": "#F59E0B",
    "text": "#1E293B",
    "muted": "#64748B",
    "border": "#E2E8F0",
    "grid": "#F1F5F9",
    "card": "#FFFFFF",
}


def bundled_python_root() -> Path | None:
    suffix = Path(".cache") / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python"
    candidates = [Path.home(), *ROOT.parents]
    for candidate in candidates:
        path = candidate / suffix
        if path.exists():
            return path
    return None


def bundled_python_packages() -> Path | None:
    root = bundled_python_root()
    if root is None:
        return None
    site_packages = root / "Lib" / "site-packages"
    return site_packages if site_packages.exists() else root


def rerun_with_bundled_python() -> None:
    root = bundled_python_root()
    if root is None:
        return
    executable = root / "python.exe"
    if executable.exists() and Path(sys.executable).resolve() != executable.resolve():
        completed = subprocess.run([str(executable), *sys.argv], check=False)
        raise SystemExit(completed.returncode)


def import_dependencies():
    try:
        import numpy as np
        import pandas as pd
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.pdfgen import canvas
        return np, pd, colors, landscape, letter, canvas
    except (ModuleNotFoundError, ImportError):
        rerun_with_bundled_python()
        bundled = bundled_python_packages()
        if bundled is not None:
            sys.path.insert(0, str(bundled))
            try:
                import numpy as np
                import pandas as pd
                from reportlab.lib import colors
                from reportlab.lib.pagesizes import landscape, letter
                from reportlab.pdfgen import canvas
                return np, pd, colors, landscape, letter, canvas
            except (ModuleNotFoundError, ImportError) as exc:
                raise SystemExit(
                    "Missing report dependencies. Install them with: "
                    "python -m pip install pandas numpy reportlab"
                ) from exc
        raise SystemExit("Missing report dependencies. Install them with: python -m pip install pandas numpy reportlab")


np, pd, rl_colors, landscape, letter, canvas = import_dependencies()


def fmt_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}".replace(",", ".")


def fmt_float(value: float | int, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "--"
    return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(part: float, total: float) -> float:
    return 100 * part / total if total else 0.0


def label_scenario(value: str) -> str:
    return SCENARIO_LABELS.get(value, value.replace("_", " "))


def metric_label(value: str) -> str:
    return METRIC_LABELS.get(value, value)


def metric_short(value: str) -> str:
    return METRIC_SHORT.get(value, value)


def hex_color(value: str):
    return rl_colors.HexColor(value)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    missing = [path for path in [RAW_RESULTS, PROCESSED_RESULTS, STATISTICAL_RESULTS] if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise SystemExit(f"Missing required analysis files: {missing_text}. Run python -m analysis.statistical_analysis first.")

    raw = pd.read_csv(RAW_RESULTS)
    processed = pd.read_csv(PROCESSED_RESULTS)
    statistical = pd.read_csv(STATISTICAL_RESULTS)

    raw = raw[raw["success"].astype(str).str.lower() == "true"].copy()
    for column in ["response_time_ms", "response_size_bytes", "repetition"]:
        raw[column] = pd.to_numeric(raw[column])
    for column in ["mean", "median", "std", "q1", "q3", "iqr", "p95"]:
        processed[column] = pd.to_numeric(processed[column])
    for column in [
        "observations",
        "rest_median",
        "graphql_median",
        "percent_difference_rest_minus_graphql",
        "holm_p_value",
        "effect_size",
    ]:
        statistical[column] = pd.to_numeric(statistical[column])
    statistical["significant"] = statistical["significant"].astype(str).str.lower() == "true"
    return raw, processed, statistical


def paired_diff_summary(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario in sorted(raw["scenario"].unique()):
        scenario_df = raw[raw["scenario"] == scenario]
        for metric in METRICS:
            pivot = scenario_df.pivot_table(index="repetition", columns="treatment", values=metric, aggfunc="first").dropna()
            diff = pivot["REST"] - pivot["GRAPHQL"]
            sd = float(diff.std(ddof=1)) if len(diff) > 1 else 0.0
            se = sd / math.sqrt(len(diff)) if len(diff) else 0.0
            rows.append(
                {
                    "scenario": scenario,
                    "metric": metric,
                    "mean_diff": float(diff.mean()) if len(diff) else 0.0,
                    "sd_diff": sd,
                    "se_diff": se,
                    "ci95_low": float(diff.mean() - 1.96 * se) if len(diff) else 0.0,
                    "ci95_high": float(diff.mean() + 1.96 * se) if len(diff) else 0.0,
                }
            )
    return pd.DataFrame(rows)


def build_stats(raw: pd.DataFrame, processed: pd.DataFrame, statistical: pd.DataFrame) -> dict:
    repetitions = int(raw.groupby(["scenario", "treatment"])["repetition"].nunique().min())
    scenarios = sorted(raw["scenario"].unique())
    valid_rows = len(raw)
    expected_rows = len(scenarios) * 2 * repetitions
    significant = statistical[statistical["significant"]]
    time_rows = statistical[statistical["metric"] == "response_time_ms"].copy()
    size_rows = statistical[statistical["metric"] == "response_size_bytes"].copy()
    best_time = time_rows.loc[time_rows["percent_difference_rest_minus_graphql"].idxmax()]
    best_size = size_rows.loc[size_rows["percent_difference_rest_minus_graphql"].idxmax()]
    simple_time = time_rows[time_rows["scenario"].isin(["simple_user", "user_list", "post_titles"])]
    nested_time = time_rows[time_rows["scenario"].isin(["nested_data", "full_profile"])]
    size_better = int((size_rows["percent_difference_rest_minus_graphql"] > 0).sum())
    time_better = int((time_rows["percent_difference_rest_minus_graphql"] > 0).sum())
    no_sig_time = int((~time_rows["significant"]).sum())

    diff_summary = paired_diff_summary(raw)
    noisy_time = diff_summary[diff_summary["metric"] == "response_time_ms"].sort_values("se_diff", ascending=False).iloc[0]

    recommended_repetitions = max(500, repetitions)
    return {
        "valid_rows": valid_rows,
        "expected_rows": expected_rows,
        "scenario_count": len(scenarios),
        "scenario_labels": ", ".join(label_scenario(scenario) for scenario in scenarios),
        "repetitions": repetitions,
        "paired_tests": len(statistical),
        "significant_tests": len(significant),
        "time_significant": int(time_rows["significant"].sum()),
        "size_significant": int(size_rows["significant"].sum()),
        "time_better": time_better,
        "size_better": size_better,
        "no_sig_time": no_sig_time,
        "best_time_scenario": label_scenario(best_time["scenario"]),
        "best_time_gain": float(best_time["percent_difference_rest_minus_graphql"]),
        "best_size_scenario": label_scenario(best_size["scenario"]),
        "best_size_gain": float(best_size["percent_difference_rest_minus_graphql"]),
        "nested_time_min_gain": float(nested_time["percent_difference_rest_minus_graphql"].min()),
        "nested_time_max_gain": float(nested_time["percent_difference_rest_minus_graphql"].max()),
        "simple_time_min_gain": float(simple_time["percent_difference_rest_minus_graphql"].min()),
        "simple_time_max_gain": float(simple_time["percent_difference_rest_minus_graphql"].max()),
        "size_min_gain": float(size_rows["percent_difference_rest_minus_graphql"].min()),
        "size_max_gain": float(size_rows["percent_difference_rest_minus_graphql"].max()),
        "noisy_scenario": label_scenario(noisy_time["scenario"]),
        "noisy_se": float(noisy_time["se_diff"]),
        "recommended_repetitions": recommended_repetitions,
        "recommended_rows": len(scenarios) * 2 * recommended_repetitions,
    }


def chart_canvas(path: Path, title: str, subtitle: str | None = None):
    width, height = 270, 205
    c = canvas.Canvas(str(path), pagesize=(width, height))
    c.setFillColor(hex_color(COLORS["card"]))
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.setFillColor(hex_color(COLORS["text"]))
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(8, height - 13, title)
    if subtitle:
        c.setFillColor(hex_color(COLORS["muted"]))
        c.setFont("Helvetica", 5.2)
        c.drawString(8, height - 21, subtitle[:96])
    return c, width, height


def draw_footer(c, width: float):
    return


def draw_axis_label(c, text: str, x: float, y: float):
    c.setFillColor(hex_color(COLORS["muted"]))
    c.setFont("Helvetica", 6.2)
    c.drawCentredString(x, y, text)


def make_bar_chart(statistical: pd.DataFrame, metric: str, output: Path) -> None:
    rows = statistical[statistical["metric"] == metric].copy()
    rows = rows.sort_values("percent_difference_rest_minus_graphql")
    title = f"Ganho percentual de GraphQL por cenario - {metric_short(metric)}"
    subtitle = "Valores positivos indicam menor mediana em GraphQL; valores negativos favorecem REST."
    c, width, height = chart_canvas(output, title, subtitle)

    left, right, top, bottom = 70, 24, height - 38, 28
    plot_w = width - left - right
    plot_h = top - bottom
    values = rows["percent_difference_rest_minus_graphql"].tolist()
    min_v = min(math.floor(min(values) / 10) * 10, -20)
    max_v = max(math.ceil(max(values) / 10) * 10, 100)
    span = max_v - min_v

    def x_scale(value: float) -> float:
        return left + (value - min_v) / span * plot_w

    zero_x = x_scale(0)
    c.setStrokeColor(hex_color(COLORS["border"]))
    c.setLineWidth(1)
    tick_start = int(math.ceil(min_v / 20) * 20)
    tick_end = int(math.floor(max_v / 20) * 20)
    for tick in range(tick_start, tick_end + 1, 20):
        x = x_scale(float(tick))
        c.setStrokeColor(hex_color(COLORS["grid"]))
        c.line(x, bottom, x, top)
        c.setFillColor(hex_color(COLORS["muted"]))
        c.setFont("Helvetica", 5.8)
        c.drawCentredString(x, bottom - 10, f"{tick:.0f}%")
    c.setStrokeColor(hex_color(COLORS["text"]))
    c.line(zero_x, bottom, zero_x, top)

    row_h = plot_h / len(rows)
    bar_h = min(13, row_h * 0.54)
    for index, (_, row) in enumerate(rows.iterrows()):
        y = top - row_h * (index + 0.5)
        value = float(row["percent_difference_rest_minus_graphql"])
        color = COLORS["primary"] if value >= 0 else COLORS["secondary"]
        c.setFillColor(hex_color(COLORS["text"]))
        c.setFont("Helvetica", 6.3)
        c.drawRightString(left - 5, y - 2, label_scenario(row["scenario"]))
        c.setFillColor(hex_color(color))
        x0 = min(zero_x, x_scale(value))
        w = abs(x_scale(value) - zero_x)
        c.roundRect(x0, y - bar_h / 2, max(w, 2), bar_h, 4, fill=1, stroke=0)
        c.setFillColor(hex_color(COLORS["text"]))
        c.setFont("Helvetica-Bold", 6.2)
        if value >= 0:
            label_x = min(x_scale(value) + 3, width - 4)
            align = c.drawString if label_x < width - 8 else c.drawRightString
        else:
            label_x = zero_x + 3
            align = c.drawString
        align(label_x, y - 2, f"{fmt_float(value, 1)}%")
        if row["significant"]:
            c.setFillColor(hex_color(COLORS["success"]))
            c.circle(x_scale(value), y + bar_h / 2 + 3, 1.7, fill=1, stroke=0)

    draw_axis_label(c, "Diferenca percentual REST - GraphQL", left + plot_w / 2, 8)
    draw_footer(c, width)
    c.save()


def make_quadrant_chart(statistical: pd.DataFrame, output: Path) -> None:
    time = statistical[statistical["metric"] == "response_time_ms"].set_index("scenario")
    size = statistical[statistical["metric"] == "response_size_bytes"].set_index("scenario")
    scenarios = [scenario for scenario in time.index if scenario in size.index]
    c, width, height = chart_canvas(
        output,
        "Perfil multivariado: ganho em tempo vs tamanho",
        "Quadrante superior direito: GraphQL reduz tempo e payload no mesmo cenario.",
    )

    left, right, top, bottom = 35, 15, height - 38, 30
    plot_w = width - left - right
    plot_h = top - bottom
    x_values = [float(size.loc[s, "percent_difference_rest_minus_graphql"]) for s in scenarios]
    y_values = [float(time.loc[s, "percent_difference_rest_minus_graphql"]) for s in scenarios]
    min_x, max_x = min(-5, min(x_values)), max(100, max(x_values))
    min_y, max_y = min(-20, min(y_values)), max(100, max(y_values))

    def x_scale(value: float) -> float:
        return left + (value - min_x) / (max_x - min_x) * plot_w

    def y_scale(value: float) -> float:
        return bottom + (value - min_y) / (max_y - min_y) * plot_h

    c.setStrokeColor(hex_color(COLORS["grid"]))
    for tick in range(0, 101, 20):
        c.line(x_scale(tick), bottom, x_scale(tick), top)
        c.line(left, y_scale(tick), left + plot_w, y_scale(tick))
        c.setFillColor(hex_color(COLORS["muted"]))
        c.setFont("Helvetica", 5.6)
        tick_x = x_scale(tick)
        if tick == 100:
            c.drawRightString(tick_x, bottom - 9, f"{tick}%")
        else:
            c.drawCentredString(tick_x, bottom - 9, f"{tick}%")
        c.drawRightString(left - 4, y_scale(tick) - 2, f"{tick}%")
    c.setStrokeColor(hex_color(COLORS["border"]))
    c.rect(left, bottom, plot_w, plot_h, fill=0, stroke=1)
    c.setStrokeColor(hex_color(COLORS["text"]))
    c.line(x_scale(0), bottom, x_scale(0), top)
    c.line(left, y_scale(0), left + plot_w, y_scale(0))

    for scenario in scenarios:
        x = float(size.loc[scenario, "percent_difference_rest_minus_graphql"])
        y = float(time.loc[scenario, "percent_difference_rest_minus_graphql"])
        significant = bool(size.loc[scenario, "significant"] or time.loc[scenario, "significant"])
        color = COLORS["primary"] if x >= 0 and y >= 0 else COLORS["secondary"]
        c.setFillColor(hex_color(color))
        c.circle(x_scale(x), y_scale(y), 4.2 if significant else 3.2, fill=1, stroke=0)
        c.setFillColor(hex_color(COLORS["text"]))
        c.setFont("Helvetica-Bold", 5.6)
        c.drawString(x_scale(x) + 5, y_scale(y) + 1, label_scenario(scenario))

    draw_axis_label(c, "Ganho em tamanho (%)", left + plot_w / 2, 8)
    c.saveState()
    c.translate(10, bottom + plot_h / 2)
    c.rotate(90)
    draw_axis_label(c, "Ganho em tempo (%)", 0, 0)
    c.restoreState()
    draw_footer(c, width)
    c.save()


def make_decision_chart(statistical: pd.DataFrame, output: Path) -> None:
    rows = statistical.copy()
    scenarios = [label_scenario(s) for s in sorted(rows["scenario"].unique())]
    c, width, height = chart_canvas(
        output,
        "Decisao estatistica por cenario e metrica",
        "Marcadores opacos sao significativos apos Holm; marcadores claros indicam resultado inconclusivo.",
    )
    left, right, top, bottom = 58, 14, height - 38, 30
    plot_w = width - left - right
    plot_h = top - bottom
    values = rows["percent_difference_rest_minus_graphql"].tolist()
    min_v = min(-20, min(values))
    max_v = max(100, max(values))

    def x_scale(value: float) -> float:
        return left + (value - min_v) / (max_v - min_v) * plot_w

    row_h = plot_h / len(scenarios)
    for tick in range(-20, 101, 20):
        x = x_scale(tick)
        c.setStrokeColor(hex_color(COLORS["grid"]))
        c.line(x, bottom, x, top)
        c.setFillColor(hex_color(COLORS["muted"]))
        c.setFont("Helvetica", 5.6)
        c.drawCentredString(x, bottom - 9, f"{tick}%")
    c.setStrokeColor(hex_color(COLORS["text"]))
    c.line(x_scale(0), bottom, x_scale(0), top)

    offsets = {"response_time_ms": 4.5, "response_size_bytes": -4.5}
    colors = {"response_time_ms": COLORS["primary"], "response_size_bytes": COLORS["secondary"]}
    for index, scenario_label in enumerate(scenarios):
        y = top - row_h * (index + 0.5)
        c.setFillColor(hex_color(COLORS["text"]))
        c.setFont("Helvetica", 6.3)
        c.drawRightString(left - 5, y - 2, scenario_label)
        scenario_key = next(key for key, label in SCENARIO_LABELS.items() if label == scenario_label)
        for metric in METRICS:
            row = rows[(rows["scenario"] == scenario_key) & (rows["metric"] == metric)].iloc[0]
            x = x_scale(float(row["percent_difference_rest_minus_graphql"]))
            c.setFillColor(hex_color(colors[metric]))
            if not row["significant"]:
                c.setFillAlpha(0.28)
            c.circle(x, y + offsets[metric], 3.2, fill=1, stroke=0)
            c.setFillAlpha(1)

    legend_x = width - 88
    legend_y = height - 13
    for i, metric in enumerate(METRICS):
        c.setFillColor(hex_color(colors[metric]))
        c.circle(legend_x + i * 43, legend_y, 2.5, fill=1, stroke=0)
        c.setFillColor(hex_color(COLORS["text"]))
        c.setFont("Helvetica", 5.8)
        c.drawString(legend_x + 5 + i * 43, legend_y - 2, metric_short(metric))

    draw_axis_label(c, "Diferenca percentual REST - GraphQL", left + plot_w / 2, 8)
    draw_footer(c, width)
    c.save()


def make_interval_chart(processed: pd.DataFrame, output: Path) -> None:
    rows = processed[processed["metric"] == "response_time_ms"].copy()
    scenarios = sorted(rows["scenario"].unique())
    c, width, height = chart_canvas(
        output,
        "Distribuicao temporal por tratamento",
        "Pontos representam medianas; linhas mostram o intervalo interquartil de cada cenario.",
    )
    left, right, top, bottom = 58, 16, height - 38, 30
    plot_w = width - left - right
    plot_h = top - bottom
    max_v = max(rows["q3"].max(), rows["median"].max()) * 1.1

    def x_scale(value: float) -> float:
        return left + value / max_v * plot_w

    row_h = plot_h / len(scenarios)
    for tick in np.linspace(0, max_v, 6):
        x = x_scale(float(tick))
        c.setStrokeColor(hex_color(COLORS["grid"]))
        c.line(x, bottom, x, top)
        c.setFillColor(hex_color(COLORS["muted"]))
        c.setFont("Helvetica", 5.6)
        c.drawCentredString(x, bottom - 9, f"{tick:.0f}")

    for index, scenario in enumerate(scenarios):
        center_y = top - row_h * (index + 0.5)
        c.setFillColor(hex_color(COLORS["text"]))
        c.setFont("Helvetica", 6.3)
        c.drawRightString(left - 5, center_y - 2, label_scenario(scenario))
        for treatment, offset, color in [("REST", 8, COLORS["primary"]), ("GRAPHQL", -8, COLORS["secondary"])]:
            row = rows[(rows["scenario"] == scenario) & (rows["treatment"] == treatment)].iloc[0]
            y = center_y + offset
            c.setStrokeColor(hex_color(color))
            c.setLineWidth(1.8)
            c.line(x_scale(float(row["q1"])), y, x_scale(float(row["q3"])), y)
            c.setFillColor(hex_color(color))
            c.circle(x_scale(float(row["median"])), y, 2.7, fill=1, stroke=0)

    legend_x = width - 82
    legend_y = height - 13
    for i, (label, color) in enumerate([("REST", COLORS["primary"]), ("GraphQL", COLORS["secondary"])]):
        c.setFillColor(hex_color(color))
        c.circle(legend_x + i * 42, legend_y, 2.5, fill=1, stroke=0)
        c.setFillColor(hex_color(COLORS["text"]))
        c.setFont("Helvetica", 5.8)
        c.drawString(legend_x + 5 + i * 42, legend_y - 2, label)

    draw_axis_label(c, "Tempo de resposta (ms)", left + plot_w / 2, 8)
    draw_footer(c, width)
    c.save()


def generate_figures(processed: pd.DataFrame, statistical: pd.DataFrame) -> list[str]:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    figures = [
        ("time_gain.pdf", lambda path: make_bar_chart(statistical, "response_time_ms", path)),
        ("size_gain.pdf", lambda path: make_bar_chart(statistical, "response_size_bytes", path)),
        ("quadrant_profile.pdf", lambda path: make_quadrant_chart(statistical, path)),
        ("statistical_decision.pdf", lambda path: make_decision_chart(statistical, path)),
        ("time_intervals.pdf", lambda path: make_interval_chart(processed, path)),
    ]
    written = []
    for filename, builder in figures:
        path = FIGURES_DIR / filename
        builder(path)
        written.append(str(path))
    return written


def result_rows(statistical: pd.DataFrame) -> str:
    rows = []
    for _, row in statistical.sort_values(["scenario", "metric"]).iterrows():
        rows.append(
            "        "
            + f"{label_scenario(row['scenario'])} & {metric_short(row['metric'])} & "
            + f"{fmt_float(row['rest_median'], 2)} & {fmt_float(row['graphql_median'], 2)} & "
            + f"{fmt_float(row['percent_difference_rest_minus_graphql'], 1)}\\% & "
            + f"{fmt_float(row['holm_p_value'], 4)} & {'Sim' if row['significant'] else 'Nao'} \\\\"
        )
    return "\n".join(rows)


def generate_latex(raw: pd.DataFrame, processed: pd.DataFrame, statistical: pd.DataFrame, stats: dict) -> str:
    table_rows = result_rows(statistical)
    return fr"""\documentclass[journal]{{IEEEtran}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[portuguese]{{babel}}
\usepackage{{graphicx}}
\usepackage{{cite}}
\usepackage{{hyperref}}
\usepackage{{amsmath}}
\usepackage{{amssymb}}
\usepackage{{booktabs}}
\usepackage{{array}}
\usepackage{{microtype}}
\graphicspath{{{{figures/}}}}
\hypersetup{{colorlinks=true,linkcolor=black,citecolor=black,urlcolor=black}}

\title{{GraphQL vs REST em um Experimento Controlado:\\
Tempo de Resposta, Tamanho de Payload e Significância Estatística}}

\author{{Amanda Bueno Campos Peixoto\\
Guilherme Gomes de Brites\\
Lucas Cerqueira Azevedo\\[0.35em]
\small Laboratório de Experimentação de Software -- Lab 05}}

\date{{\today}}

\begin{{document}}

\maketitle

\begin{{abstract}}
Este artigo relata um experimento controlado que compara REST e GraphQL sobre a mesma base SQLite, a mesma camada de serviços e cinco cenários de consulta. A coleta atualmente disponível contém {fmt_int(stats["valid_rows"])} medições válidas, organizadas em {fmt_int(stats["repetitions"])} repetições pareadas por cenário e tecnologia. A análise avalia tempo de resposta e tamanho do payload por meio de estatísticas descritivas, testes pareados, correção de Holm e tamanho de efeito. Os resultados indicam vantagem clara de GraphQL em cenários com dados aninhados e redução consistente de payload em quatro dos cinco cenários, enquanto consultas simples apresentam diferenças temporais pequenas e não significativas.
\end{{abstract}}

\section{{Introdução}}
\label{{sec:intro}}

APIs REST continuam sendo uma escolha dominante para sistemas Web por sua simplicidade operacional e compatibilidade com HTTP. GraphQL propõe uma alternativa orientada a consulta, na qual o cliente especifica exatamente os campos desejados e pode recuperar estruturas aninhadas em uma única chamada. Essa flexibilidade promete reduzir over-fetching, under-fetching e múltiplas idas à rede, mas também pode introduzir custo de parsing e resolução no servidor.

O objetivo deste trabalho é comparar empiricamente REST e GraphQL em um ambiente controlado. O estudo mede duas dimensões observáveis pelo cliente: tempo total de resposta e tamanho do corpo retornado. A pergunta central é se GraphQL apresenta vantagem mensurável em relação a REST quando ambas as abordagens executam tarefas equivalentes sobre os mesmos dados.

\section{{Metodologia}}
\label{{sec:methodology}}

\subsection{{Ambiente Experimental}}

O experimento usa uma API Python local com endpoints REST e um endpoint GraphQL. As duas tecnologias compartilham o mesmo banco SQLite e a mesma camada de serviços, reduzindo diferenças de implementação que poderiam favorecer artificialmente uma abordagem. A base sintética padrão contém 1.000 usuários, 10.000 postagens e 50.000 comentários, gerados de forma determinística.

Os cenários avaliados foram: {stats["scenario_labels"]}. Cada cenário foi executado nas versões REST e GraphQL. Nos cenários REST que exigem múltiplas chamadas, o tempo e o tamanho foram acumulados até completar a tarefa experimental, preservando equivalência funcional com a consulta GraphQL.

\subsection{{Coleta}}

A configuração usada nos dados atuais executou 10 chamadas de aquecimento por cenário e tecnologia, seguidas por {fmt_int(stats["repetitions"])} repetições válidas pareadas. Em cada repetição, a ordem entre REST e GraphQL foi randomizada para reduzir viés de aquecimento, cache e flutuação temporal. O dataset resultante possui {fmt_int(stats["valid_rows"])} linhas válidas, exatamente {fmt_int(stats["scenario_count"])} cenários $\times$ 2 tecnologias $\times$ {fmt_int(stats["repetitions"])} repetições.

A configuração padrão do coletor foi definida em {fmt_int(stats["recommended_repetitions"])} repetições por cenário, o que gera {fmt_int(stats["recommended_rows"])} medições válidas em uma nova execução completa. A razão é prática: {fmt_int(stats["valid_rows"])} medições são suficientes para revelar grandes efeitos, mas os cenários simples apresentam diferenças temporais próximas do ruído de medição local. Manter esse volume de repetições melhora a precisão desses casos marginais sem alterar o desenho experimental.

\subsection{{Análise Estatística}}

Para cada cenário e métrica, as medições foram pareadas por repetição. A diferença foi definida como REST menos GraphQL; portanto, valores positivos indicam menor tempo ou payload em GraphQL. A normalidade das diferenças foi avaliada por Shapiro-Wilk. Quando a distribuição foi compatível com normalidade, aplicou-se teste t pareado; caso contrário, aplicou-se Wilcoxon pareado. Os p-valores foram corrigidos por Holm separadamente por métrica, com $\alpha = 0{{,}}05$.

\section{{Resultados}}
\label{{sec:results}}

\subsection{{Visão Geral dos Efeitos}}

\begin{{figure}}[!t]
\centering
\includegraphics[width=\columnwidth]{{time_gain.pdf}}
\caption{{Ganho percentual de GraphQL em tempo de resposta. Valores positivos indicam menor mediana em GraphQL.}}
\label{{fig:time_gain}}
\end{{figure}}

A Figura \ref{{fig:time_gain}} mostra que GraphQL reduziu fortemente o tempo nos cenários \textit{{nested data}} e \textit{{full profile}}, com ganhos entre {fmt_float(stats["nested_time_min_gain"], 1)}\% e {fmt_float(stats["nested_time_max_gain"], 1)}\%. Esses cenários exigem múltiplas chamadas REST para recompor dados aninhados, enquanto GraphQL resolve a tarefa em uma consulta. Em contraste, consultas simples ficaram próximas da paridade, com diferenças entre {fmt_float(stats["simple_time_min_gain"], 1)}\% e {fmt_float(stats["simple_time_max_gain"], 1)}\%, e sem significância em {fmt_int(stats["no_sig_time"])} dos cinco testes temporais.

\begin{{figure}}[!t]
\centering
\includegraphics[width=\columnwidth]{{size_gain.pdf}}
\caption{{Ganho percentual de GraphQL no tamanho da resposta. Valores positivos indicam menor payload em GraphQL.}}
\label{{fig:size_gain}}
\end{{figure}}

A Figura \ref{{fig:size_gain}} evidencia uma vantagem mais consistente em tamanho de resposta. GraphQL reduziu o payload em {fmt_int(stats["size_better"])} dos cinco cenários, com ganhos entre {fmt_float(stats["size_min_gain"], 1)}\% e {fmt_float(stats["size_max_gain"], 1)}\%. O único caso negativo foi \textit{{full profile}}, no qual a consulta GraphQL retornou uma representação praticamente equivalente à REST e ficou {fmt_float(abs(stats["size_min_gain"]), 1)}\% maior.

\subsection{{Perfil Multivariado}}

\begin{{figure}}[!t]
\centering
\includegraphics[width=\columnwidth]{{quadrant_profile.pdf}}
\caption{{Perfil multivariado dos cenários: ganho em tamanho versus ganho em tempo.}}
\label{{fig:quadrant}}
\end{{figure}}

A Figura \ref{{fig:quadrant}} combina as duas métricas. Os cenários aninhados aparecem no quadrante favorável a GraphQL em tempo e, em geral, também em tamanho. O cenário \textit{{post titles}} demonstra o caso clássico de redução de over-fetching: o tempo fica próximo da paridade, mas o payload cai substancialmente porque a consulta GraphQL solicita apenas títulos.

\subsection{{Distribuição Temporal}}

\begin{{figure}}[!t]
\centering
\includegraphics[width=\columnwidth]{{time_intervals.pdf}}
\caption{{Medianas e intervalos interquartis do tempo de resposta por tratamento.}}
\label{{fig:time_intervals}}
\end{{figure}}

A Figura \ref{{fig:time_intervals}} mostra que as distribuições de tempo dos cenários simples se sobrepõem mais do que as dos cenários aninhados. Isso explica a decisão estatística: quando a diferença é pequena diante da variabilidade local, a conclusão apropriada é paridade ou inconclusão, não vitória prática de uma tecnologia.

\subsection{{Decisão Estatística}}

\begin{{figure}}[!t]
\centering
\includegraphics[width=\columnwidth]{{statistical_decision.pdf}}
\caption{{Decisão estatística por cenário e métrica. Marcadores opacos indicam significância após correção de Holm.}}
\label{{fig:decision}}
\end{{figure}}

A Figura \ref{{fig:decision}} resume os {fmt_int(stats["paired_tests"])} testes pareados. Ao todo, {fmt_int(stats["significant_tests"])} foram significativos. Para tempo de resposta, {fmt_int(stats["time_significant"])} de cinco cenários apresentaram diferença significativa. Para tamanho do payload, {fmt_int(stats["size_significant"])} de cinco cenários foram significativos, o que era esperado porque os tamanhos são determinísticos para uma mesma consulta e base de dados.

\begin{{table*}}[!t]
\centering
\caption{{Resumo dos testes pareados. Dif. é REST menos GraphQL; valores positivos favorecem GraphQL.}}
\label{{tab:tests}}
\footnotesize
\setlength{{\tabcolsep}}{{6pt}}
\renewcommand{{\arraystretch}}{{1.12}}
\begin{{tabular}}{{llrrrrr}}
\toprule
Cenário & Métrica & REST & GraphQL & Dif. & p Holm & Sig. \\
\midrule
{table_rows}
\bottomrule
\end{{tabular}}
\end{{table*}}

\section{{Discussão}}
\label{{sec:discussion}}

Os resultados sugerem que a vantagem de GraphQL depende do formato da tarefa. Quando a consulta exige dados aninhados ou seleção fina de campos, GraphQL reduz chamadas ou payload e tende a apresentar ganhos relevantes. Quando a tarefa já é simples em REST, como buscar um usuário ou listar usuários com poucos campos, o custo e o benefício ficam próximos da paridade.

O tamanho da resposta apresentou comportamento mais estável que o tempo, pois é determinado pelo formato do payload. O tempo de resposta, por outro lado, sofre influência de ruído local, escalonamento do sistema operacional e pequenas variações do servidor. A maior incerteza foi observada em {stats["noisy_scenario"]}, com erro padrão da diferença temporal de aproximadamente {fmt_float(stats["noisy_se"], 2)} ms. Por isso, o projeto recomenda manter pelo menos {fmt_int(stats["recommended_repetitions"])} repetições por cenário em novas coletas.

\section{{Ameaças à Validade}}
\label{{sec:threats}}

O estudo usa uma API local e uma base sintética; portanto, os resultados não devem ser generalizados diretamente para sistemas distribuídos, redes reais ou bancos sob carga concorrente. A implementação GraphQL e REST foi construída para equivalência funcional, mas bibliotecas e otimizações específicas poderiam alterar os resultados. Além disso, o tamanho de resposta mede apenas o corpo retornado, não cabeçalhos HTTP ou compressão. Finalmente, o experimento atual mede um único perfil de dados e parâmetros fixos de página, usuário e limite.

\section{{Conclusão}}
\label{{sec:conclusion}}

Neste experimento controlado, GraphQL apresentou ganhos expressivos nos cenários em que REST precisou realizar múltiplas chamadas ou retornou campos desnecessários. A vantagem mais clara ocorreu em \textit{{{stats["best_time_scenario"]}}}, com {fmt_float(stats["best_time_gain"], 1)}\% de redução na mediana de tempo, e em \textit{{{stats["best_size_scenario"]}}}, com {fmt_float(stats["best_size_gain"], 1)}\% de redução no tamanho da resposta. Para consultas simples, a evidência não sustenta uma superioridade temporal robusta. Assim, a conclusão principal é contextual: GraphQL se destaca quando a consulta precisa compor dados ou controlar seletivamente campos, enquanto REST permanece competitivo em endpoints simples e bem ajustados.

\begin{{thebibliography}}{{99}}

\bibitem{{graphql}} GraphQL Foundation, ``GraphQL Specification'', \url{{https://spec.graphql.org/}}.

\bibitem{{fielding}} R. T. Fielding, ``Architectural Styles and the Design of Network-based Software Architectures'', Doctoral dissertation, University of California, Irvine, 2000.

\bibitem{{holm}} S. Holm, ``A Simple Sequentially Rejective Multiple Test Procedure'', Scandinavian Journal of Statistics, 1979.

\bibitem{{wilcoxon}} F. Wilcoxon, ``Individual Comparisons by Ranking Methods'', Biometrics Bulletin, 1945.

\end{{thebibliography}}

\end{{document}}
"""


def generate_latex_paper(output_dir: Path = OUTPUT_DIR) -> Path:
    raw, processed, statistical = load_data()
    stats = build_stats(raw, processed, statistical)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures = generate_figures(processed, statistical)
    latex = generate_latex(raw, processed, statistical, stats)
    output_file = output_dir / "paper.tex"
    output_file.write_text(latex, encoding="utf-8")

    print(f"Documento LaTeX gerado: {output_file}")
    print("Figuras geradas:")
    for figure in figures:
        print(f"  {figure}")
    print("\nObservacao sobre tamanho amostral:")
    print(
        f"  A coleta atual possui {fmt_int(stats['valid_rows'])} medicoes; "
        f"o default do coletor esta definido para {fmt_int(stats['recommended_rows'])} "
        "medicoes em uma nova execucao completa."
    )
    return output_file


if __name__ == "__main__":
    generate_latex_paper()
