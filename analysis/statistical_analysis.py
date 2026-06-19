from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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

try:
    import numpy as np
    import pandas as pd
except (ModuleNotFoundError, ImportError):
    rerun_with_bundled_python()
    bundled_packages = bundled_python_packages()
    if bundled_packages is not None:
        sys.path.insert(0, str(bundled_packages))
        try:
            import numpy as np
            import pandas as pd
        except (ModuleNotFoundError, ImportError) as exc:
            raise SystemExit(
                "Missing Python dependency. Install it with: python -m pip install pandas numpy"
            ) from exc
    else:
        raise SystemExit("Missing Python dependency. Install it with: python -m pip install pandas numpy")

try:
    from scipy import stats
except ModuleNotFoundError:
    stats = None


DATA_DIR = ROOT / "data"
RAW_RESULTS = DATA_DIR / "raw_results.csv"
PROCESSED_RESULTS = DATA_DIR / "processed_results.csv"
STATISTICAL_RESULTS = DATA_DIR / "statistical_results.csv"
ALPHA = 0.05


def percentile_95(values: pd.Series) -> float:
    return float(np.percentile(values, 95))


def iqr(values: pd.Series) -> float:
    return float(np.percentile(values, 75) - np.percentile(values, 25))


def descriptive_statistics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric in ["response_time_ms", "response_size_bytes"]:
        grouped = df.groupby(["scenario", "treatment"])[metric]
        desc = grouped.agg(
            observations="count",
            mean="mean",
            median="median",
            std="std",
            min="min",
            max="max",
            q1=lambda x: float(np.percentile(x, 25)),
            q3=lambda x: float(np.percentile(x, 75)),
            iqr=iqr,
            p95=percentile_95,
        ).reset_index()
        desc.insert(2, "metric", metric)
        rows.append(desc)
    return pd.concat(rows, ignore_index=True)


def holm_adjust(p_values: list[float]) -> list[float]:
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [math.nan] * len(p_values)
    running_max = 0.0
    m = len(p_values)
    for rank, (index, p_value) in enumerate(indexed, start=1):
        adjusted_value = min((m - rank + 1) * p_value, 1.0)
        running_max = max(running_max, adjusted_value)
        adjusted[index] = running_max
    return adjusted


def rankdata(values: pd.Series | np.ndarray) -> np.ndarray:
    indexed = sorted(enumerate(np.asarray(values, dtype=float)), key=lambda item: item[1])
    ranks = np.zeros(len(indexed), dtype=float)
    position = 0
    while position < len(indexed):
        end = position
        while end + 1 < len(indexed) and indexed[end + 1][1] == indexed[position][1]:
            end += 1
        average_rank = (position + 1 + end + 1) / 2.0
        for idx in range(position, end + 1):
            ranks[indexed[idx][0]] = average_rank
        position = end + 1
    return ranks


def rank_biserial(diff: pd.Series) -> float:
    non_zero = diff[diff != 0]
    if non_zero.empty:
        return 0.0
    ranks = rankdata(abs(non_zero))
    positive = float(ranks[non_zero > 0].sum())
    negative = float(ranks[non_zero < 0].sum())
    total = positive + negative
    return (positive - negative) / total if total else 0.0


def normal_two_sided_p(z_value: float) -> float:
    return math.erfc(abs(z_value) / math.sqrt(2.0))


def wilcoxon_normal_approximation(rest: pd.Series, graphql: pd.Series) -> float:
    diff = rest - graphql
    non_zero = diff[diff != 0]
    n = len(non_zero)
    if n == 0:
        return 1.0
    ranks = rankdata(abs(non_zero))
    w_positive = float(ranks[non_zero > 0].sum())
    mean = n * (n + 1) / 4.0
    variance = n * (n + 1) * (2 * n + 1) / 24.0
    if variance == 0:
        return 1.0
    z_value = (w_positive - mean) / math.sqrt(variance)
    return normal_two_sided_p(z_value)


def paired_tests(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario in sorted(df["scenario"].unique()):
        scenario_df = df[df["scenario"] == scenario]
        for metric in ["response_time_ms", "response_size_bytes"]:
            pivot = scenario_df.pivot_table(index="repetition", columns="treatment", values=metric, aggfunc="first").dropna()
            rest = pivot["REST"]
            graphql = pivot["GRAPHQL"]
            diff = rest - graphql

            shapiro_p = float(stats.shapiro(diff).pvalue) if stats is not None and len(diff) >= 3 else math.nan
            normal = bool(not math.isnan(shapiro_p) and shapiro_p >= ALPHA)

            if normal:
                test_name = "paired_t_test"
                if stats is not None:
                    result = stats.ttest_rel(rest, graphql)
                    p_value = float(result.pvalue)
                else:
                    p_value = math.nan
                effect_name = "cohens_d"
                effect_size = float(diff.mean() / diff.std(ddof=1)) if diff.std(ddof=1) else 0.0
            else:
                test_name = "wilcoxon" if stats is not None else "wilcoxon_normal_approximation"
                if stats is not None:
                    try:
                        result = stats.wilcoxon(rest, graphql, zero_method="wilcox")
                        p_value = float(result.pvalue)
                    except ValueError:
                        p_value = 1.0
                else:
                    p_value = wilcoxon_normal_approximation(rest, graphql)
                effect_name = "rank_biserial"
                effect_size = rank_biserial(diff)

            rest_median = float(rest.median())
            graphql_median = float(graphql.median())
            percent_difference = ((rest_median - graphql_median) / rest_median * 100.0) if rest_median else 0.0
            rows.append(
                {
                    "scenario": scenario,
                    "metric": metric,
                    "observations": len(diff),
                    "rest_median": rest_median,
                    "graphql_median": graphql_median,
                    "median_difference_rest_minus_graphql": rest_median - graphql_median,
                    "percent_difference_rest_minus_graphql": percent_difference,
                    "shapiro_p_value": shapiro_p,
                    "normal_difference": normal,
                    "test": test_name,
                    "p_value": p_value,
                    "effect_name": effect_name,
                    "effect_size": effect_size,
                }
            )

    results = pd.DataFrame(rows)
    for metric in ["response_time_ms", "response_size_bytes"]:
        mask = results["metric"] == metric
        results.loc[mask, "holm_p_value"] = holm_adjust(results.loc[mask, "p_value"].tolist())
    results["significant"] = results["holm_p_value"] < ALPHA
    return results


def main() -> None:
    if not RAW_RESULTS.exists():
        raise SystemExit(f"Missing {RAW_RESULTS}. Run python -m experiment.run_experiment first.")

    df = pd.read_csv(RAW_RESULTS)
    df = df[df["success"].astype(str).str.lower() == "true"].copy()
    df["response_time_ms"] = pd.to_numeric(df["response_time_ms"])
    df["response_size_bytes"] = pd.to_numeric(df["response_size_bytes"])
    df["repetition"] = pd.to_numeric(df["repetition"])

    descriptive = descriptive_statistics(df)
    statistical = paired_tests(df)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    descriptive.to_csv(PROCESSED_RESULTS, index=False)
    statistical.to_csv(STATISTICAL_RESULTS, index=False)
    print(f"Processed results written to {PROCESSED_RESULTS}")
    print(f"Statistical results written to {STATISTICAL_RESULTS}")


if __name__ == "__main__":
    main()
