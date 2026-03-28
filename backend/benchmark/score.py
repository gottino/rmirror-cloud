#!/usr/bin/env python3
"""OCR benchmark scorer — compares outputs against ground truth."""

import argparse
import re
import sys
from pathlib import Path

import yaml
from Levenshtein import distance as levenshtein_distance

# Scoring weights — tune these to prioritize different error types
WEIGHT_CER = 0.4
WEIGHT_LINE = 0.3
WEIGHT_STRUCTURE = 0.3


def compute_cer(output: str, ground_truth: str) -> float:
    """Character Error Rate: edit distance / reference length. Lower is better. Range [0, 1]."""
    if not ground_truth:
        return 0.0
    dist = levenshtein_distance(output, ground_truth)
    return min(dist / len(ground_truth), 1.0)


def compute_line_accuracy(output: str, ground_truth: str) -> float:
    """Fraction of ground truth lines that have a fuzzy match in output. Higher is better. Range [0, 1]."""
    gt_lines = [line.strip() for line in ground_truth.splitlines() if line.strip()]
    out_lines = [line.strip() for line in output.splitlines() if line.strip()]

    if not gt_lines:
        return 1.0

    matched = 0
    for gt_line in gt_lines:
        for out_line in out_lines:
            similarity = _line_similarity(gt_line, out_line)
            if similarity >= 0.8:
                matched += 1
                break

    return matched / len(gt_lines)


def _line_similarity(a: str, b: str) -> float:
    """Similarity between two strings. 1.0 = identical, 0.0 = completely different."""
    if not a and not b:
        return 1.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    dist = levenshtein_distance(a, b)
    return 1.0 - (dist / max_len)


def compute_structure_score(output: str, ground_truth: str) -> float:
    """Score structural preservation: checkboxes, bullets, indentation, dates. Higher is better. Range [0, 1]."""
    sub_scores = []

    # Checkbox count
    gt_checks = len(re.findall(r"- \[[ x]\]", ground_truth))
    out_checks = len(re.findall(r"- \[[ x]\]", output))
    if gt_checks > 0:
        sub_scores.append(max(0.0, 1.0 - abs(out_checks - gt_checks) / gt_checks))
    else:
        sub_scores.append(1.0 if out_checks == 0 else 0.5)

    # Bullet count (lines starting with "- " but not checkboxes)
    gt_bullets = len([l for l in ground_truth.splitlines() if re.match(r"\s*- (?!\[)", l)])
    out_bullets = len([l for l in output.splitlines() if re.match(r"\s*- (?!\[)", l)])
    if gt_bullets > 0:
        sub_scores.append(max(0.0, 1.0 - abs(out_bullets - gt_bullets) / gt_bullets))
    else:
        sub_scores.append(1.0 if out_bullets == 0 else 0.5)

    # Indentation levels: count lines with 2+, 4+, 6+ leading spaces
    for indent in [2, 4, 6]:
        gt_indented = len([l for l in ground_truth.splitlines() if len(l) - len(l.lstrip()) >= indent])
        out_indented = len([l for l in output.splitlines() if len(l) - len(l.lstrip()) >= indent])
        if gt_indented > 0:
            sub_scores.append(max(0.0, 1.0 - abs(out_indented - gt_indented) / gt_indented))

    # Date extraction
    gt_dates = re.findall(r"\*\*Date:\s*(\d{1,2}-\d{1,2}-\d{4})\*\*", ground_truth)
    out_dates = re.findall(r"\*\*Date:\s*(\d{1,2}-\d{1,2}-\d{4})\*\*", output)
    if gt_dates:
        if gt_dates == out_dates:
            sub_scores.append(1.0)
        elif out_dates:
            sub_scores.append(0.3)
        else:
            sub_scores.append(0.0)

    if not sub_scores:
        return 1.0

    return sum(sub_scores) / len(sub_scores)


def compute_composite(cer: float, line_accuracy: float, structure: float) -> float:
    """Weighted composite score. Higher is better."""
    return WEIGHT_CER * (1.0 - cer) + WEIGHT_LINE * line_accuracy + WEIGHT_STRUCTURE * structure


def find_latest_run(results_dir: Path) -> Path | None:
    """Find the most recent results directory."""
    runs = sorted([d for d in results_dir.iterdir() if d.is_dir()], reverse=True)
    return runs[0] if runs else None


def score_run(run_dir: Path, ground_truth_dir: Path, verbose: bool):
    """Score all outputs in a benchmark run against ground truth."""
    meta_path = run_dir / "meta.yaml"
    if not meta_path.exists():
        print(f"ERROR: No meta.yaml found in {run_dir}")
        sys.exit(1)

    with open(meta_path) as f:
        meta = yaml.safe_load(f)

    model_dirs = sorted([d for d in run_dir.iterdir() if d.is_dir()])
    if not model_dirs:
        print(f"ERROR: No model result directories in {run_dir}")
        sys.exit(1)

    gt_files = {p.stem: p.read_text(encoding="utf-8") for p in ground_truth_dir.glob("*.md")}
    if not gt_files:
        print(f"ERROR: No .md files found in {ground_truth_dir}/")
        print("Add ground truth transcriptions to benchmark/ground_truth/ and try again.")
        sys.exit(1)

    all_scores = {}
    for model_dir in model_dirs:
        model_name = model_dir.name
        all_scores[model_name] = {}

        for output_file in sorted(model_dir.glob("*.md")):
            fname = output_file.stem
            parts = fname.rsplit("_run", 1)
            if len(parts) != 2:
                continue
            page_stem = parts[0]

            if page_stem not in gt_files:
                if page_stem not in all_scores[model_name]:
                    print(f"WARNING: No ground truth for '{page_stem}', skipping")
                continue

            output_text = output_file.read_text(encoding="utf-8")

            if output_text.startswith("ERROR:"):
                continue

            gt_text = gt_files[page_stem]
            cer = compute_cer(output_text, gt_text)
            line_acc = compute_line_accuracy(output_text, gt_text)
            structure = compute_structure_score(output_text, gt_text)
            composite = compute_composite(cer, line_acc, structure)

            if page_stem not in all_scores[model_name]:
                all_scores[model_name][page_stem] = []

            all_scores[model_name][page_stem].append({
                "cer": round(cer, 4),
                "line_accuracy": round(line_acc, 4),
                "structure": round(structure, 4),
                "composite": round(composite, 4),
            })

    summary = {}
    for model_name, pages in all_scores.items():
        all_composites = []
        all_cers = []
        all_lines = []
        all_structs = []

        for page_runs in pages.values():
            for run in page_runs:
                all_cers.append(run["cer"])
                all_lines.append(run["line_accuracy"])
                all_structs.append(run["structure"])
                all_composites.append(run["composite"])

        if all_composites:
            summary[model_name] = {
                "cer": {"mean": _mean(all_cers), "stddev": _stddev(all_cers)},
                "line_accuracy": {"mean": _mean(all_lines), "stddev": _stddev(all_lines)},
                "structure": {"mean": _mean(all_structs), "stddev": _stddev(all_structs)},
                "composite": {"mean": _mean(all_composites), "stddev": _stddev(all_composites)},
            }

    timestamp = run_dir.name
    total_pages = len(gt_files)
    total_models = len(summary)
    runs_per_page = meta.get("runs_per_page", "?")

    print(f"\nOCR Benchmark Results \u2014 {timestamp}")
    print("=" * 70)
    print(f"{total_models} models x {total_pages} pages x {runs_per_page} runs\n")
    print(f"{'Model':<20} {'CER\u2193':>6} {'Lines\u2191':>7} {'Struct\u2191':>8} {'Score\u2191':>7} {'StdDev':>7}")
    print("\u2500" * 70)

    for model_name, stats in sorted(summary.items(), key=lambda x: x[1]["composite"]["mean"], reverse=True):
        print(
            f"{model_name:<20} "
            f"{stats['cer']['mean']:>6.2f} "
            f"{stats['line_accuracy']['mean']:>7.2f} "
            f"{stats['structure']['mean']:>8.2f} "
            f"{stats['composite']['mean']:>7.2f} "
            f"{stats['composite']['stddev']:>7.3f}"
        )

        if stats["composite"]["stddev"] > 0.1:
            print(f"  \u26a0 HIGH VARIANCE (stddev {stats['composite']['stddev']:.3f})")

    if verbose:
        print(f"\nPer-page breakdown:")
        print("-" * 70)
        for model_name, pages in sorted(all_scores.items()):
            for page_stem, runs in sorted(pages.items()):
                page_mean = _mean([r["composite"] for r in runs])
                print(f"  {model_name} / {page_stem}: composite={page_mean:.3f} ({len(runs)} runs)")
                for i, run in enumerate(runs, 1):
                    print(f"    run {i}: CER={run['cer']:.3f} lines={run['line_accuracy']:.3f} struct={run['structure']:.3f}")

    scores_output = {"summary": summary, "pages": {}}
    for model_name, pages in all_scores.items():
        for page_stem, runs in pages.items():
            if page_stem not in scores_output["pages"]:
                scores_output["pages"][page_stem] = {}
            page_mean = {
                "cer": _mean([r["cer"] for r in runs]),
                "line_accuracy": _mean([r["line_accuracy"] for r in runs]),
                "structure": _mean([r["structure"] for r in runs]),
                "composite": _mean([r["composite"] for r in runs]),
            }
            scores_output["pages"][page_stem][model_name] = {"runs": runs, "mean": page_mean}

    scores_path = run_dir / "scores.yaml"
    with open(scores_path, "w") as f:
        yaml.dump(scores_output, f, default_flow_style=False, sort_keys=False)

    print(f"\nDetailed scores saved to: {scores_path}")


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    variance = sum((x - avg) ** 2 for x in values) / (len(values) - 1)
    return round(variance**0.5, 4)


def main():
    parser = argparse.ArgumentParser(description="OCR Benchmark Scorer")
    parser.add_argument("--run", type=str, help="Specific run timestamp to score (default: latest)")
    parser.add_argument("--verbose", action="store_true", help="Show per-page breakdown")
    args = parser.parse_args()

    benchmark_dir = Path(__file__).parent
    results_dir = benchmark_dir / "results"
    ground_truth_dir = benchmark_dir / "ground_truth"

    if args.run:
        run_dir = results_dir / args.run
        if not run_dir.exists():
            print(f"ERROR: Run directory not found: {run_dir}")
            sys.exit(1)
    else:
        run_dir = find_latest_run(results_dir)
        if not run_dir:
            print(f"ERROR: No results found in {results_dir}/")
            print("Run 'python benchmark/run.py' first.")
            sys.exit(1)

    score_run(run_dir, ground_truth_dir, args.verbose)


if __name__ == "__main__":
    main()
