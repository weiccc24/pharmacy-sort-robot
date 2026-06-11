"""
analyze_results.py
TECHIN 517 Final Project — Quantitative Results Analysis

Reads the trial CSV logged by pharmacy_sort.py and produces:
  - Success rate per state (bar chart)
  - Mean and standard deviation of completion times (successful trials only)
  - Failure mode breakdown per state
  - Summary table printed to terminal

Usage:
    python3 final_project/analyze_results.py
    python3 final_project/analyze_results.py --csv ~/techin517_trials.csv
    python3 final_project/analyze_results.py --csv ~/techin517_trials.csv --out final_project/results/
"""

import argparse
import os
import sys

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

DEFAULT_CSV = os.path.expanduser("~/techin517_trials.csv")
STATE_ORDER  = ["baseline", "ambient_variance", "geometry_shift"]
STATE_LABELS = {
    "baseline":         "State 1\nBaseline",
    "ambient_variance": "State 2\nAmbient Variance",
    "geometry_shift":   "State 3\nGeometry Shift",
}
COLORS = {
    "baseline":         "#2196F3",
    "ambient_variance": "#FF9800",
    "geometry_shift":   "#4CAF50",
}


def load(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        print(f"[Error] CSV not found: {csv_path}")
        print("Run pharmacy_sort.py to generate trial data first.")
        sys.exit(1)
    df = pd.read_csv(csv_path)
    df["success"] = df["success"].astype(int)
    df["completion_time_s"] = pd.to_numeric(df["completion_time_s"], errors="coerce")
    return df


def print_summary(df: pd.DataFrame):
    print("\n" + "="*60)
    print("PHARMACY SORTING — QUANTITATIVE RESULTS SUMMARY")
    print("="*60)
    print(f"Total trials: {len(df)}")
    print(f"Overall success rate: {df['success'].mean()*100:.1f}%\n")

    for state in STATE_ORDER:
        sdf = df[df["state_label"] == state]
        if sdf.empty:
            continue
        n       = len(sdf)
        n_ok    = sdf["success"].sum()
        rate    = n_ok / n * 100
        ok_times = sdf[sdf["success"] == 1]["completion_time_s"].dropna()
        t_mean  = ok_times.mean() if len(ok_times) else float("nan")
        t_std   = ok_times.std()  if len(ok_times) else float("nan")

        print(f"  {STATE_LABELS.get(state, state).replace(chr(10), ' ')}")
        print(f"    Trials:       {n}")
        print(f"    Success rate: {rate:.0f}%  ({n_ok}/{n})")
        if not pd.isna(t_mean):
            print(f"    Time (mean):  {t_mean:.1f}s  ± {t_std:.1f}s")
        # Failure modes
        fails = sdf[sdf["success"] == 0]["failure_mode"].value_counts()
        if not fails.empty:
            print(f"    Failures:")
            for mode, count in fails.items():
                print(f"      {mode}: {count}")
        print()
    print("="*60 + "\n")


def plot_success_rate(df: pd.DataFrame, out_dir: str):
    states  = [s for s in STATE_ORDER if s in df["state_label"].values]
    rates   = [df[df["state_label"] == s]["success"].mean() * 100 for s in states]
    labels  = [STATE_LABELS.get(s, s) for s in states]
    colors  = [COLORS.get(s, "#888888") for s in states]

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(labels, rates, color=colors, width=0.5, edgecolor="white", linewidth=1.2)

    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                f"{rate:.0f}%", ha="center", va="bottom", fontsize=12, fontweight="bold")

    ax.set_ylim(0, 115)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.set_ylabel("Success Rate", fontsize=12)
    ax.set_title("Pharmacy Sorting — Success Rate by Test State", fontsize=13, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    path = os.path.join(out_dir, "success_rate.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"Saved: {path}")
    plt.close(fig)


def plot_completion_times(df: pd.DataFrame, out_dir: str):
    states = [s for s in STATE_ORDER if s in df["state_label"].values]
    ok_df  = df[df["success"] == 1]
    if ok_df.empty:
        print("No successful trials to plot timing for yet.")
        return

    means  = []
    stds   = []
    labels = []
    colors = []
    for s in states:
        t = ok_df[ok_df["state_label"] == s]["completion_time_s"].dropna()
        if t.empty:
            continue
        means.append(t.mean())
        stds.append(t.std() if len(t) > 1 else 0)
        labels.append(STATE_LABELS.get(s, s))
        colors.append(COLORS.get(s, "#888888"))

    if not means:
        return

    fig, ax = plt.subplots(figsize=(7, 5))
    x = range(len(labels))
    ax.bar(x, means, yerr=stds, color=colors, width=0.5,
           capsize=6, edgecolor="white", linewidth=1.2)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Completion Time (s)", fontsize=12)
    ax.set_title("Pharmacy Sorting — Completion Time (Successful Trials)", fontsize=13, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    path = os.path.join(out_dir, "completion_times.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"Saved: {path}")
    plt.close(fig)


def plot_failure_modes(df: pd.DataFrame, out_dir: str):
    fail_df = df[df["success"] == 0]
    if fail_df.empty:
        print("No failures to plot yet.")
        return

    modes = fail_df["failure_mode"].value_counts()
    fig, ax = plt.subplots(figsize=(7, 4))
    modes.plot(kind="barh", ax=ax, color="#EF5350", edgecolor="white")
    ax.set_xlabel("Count", fontsize=12)
    ax.set_title("Failure Mode Breakdown", fontsize=13, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.4)

    path = os.path.join(out_dir, "failure_modes.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"Saved: {path}")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Pharmacy sorting quantitative results analysis")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Path to trial CSV")
    parser.add_argument("--out", default="final_project/results/", help="Output directory for charts")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    df = load(args.csv)
    print_summary(df)
    plot_success_rate(df, args.out)
    plot_completion_times(df, args.out)
    plot_failure_modes(df, args.out)

    # Save a cleaned copy of the raw data next to the charts
    clean_path = os.path.join(args.out, "trials_raw.csv")
    df.to_csv(clean_path, index=False)
    print(f"Saved: {clean_path}")
    print("\nDone. Add the charts and trials_raw.csv to your GitHub repo.")


if __name__ == "__main__":
    main()
