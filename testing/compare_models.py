"""
Сравнение моделей классификации: Random Forest, KNN, CatBoost
Запуск: python compare_models.py
Результат: два графика (bar chart + boxplot) в папке скрипта
"""

import json
import matplotlib
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import StratifiedKFold, cross_validate
from catboost import CatBoostClassifier

# ── Настройки ────────────────────────────────────────────────────────────────
matplotlib.use("Agg")
TRAINING_DATA_FILE = "../core/training_data_final.json"  # путь относительно корня проекта
N_SPLITS = 5
RANDOM_STATE = 42

FEATURE_ORDER = [
    "domain_similarity", "homogeneity_score",
    "commercial_intent", "is_marketplace", "is_review_news_site", "claims_official",
    "has_legal_info", "is_private_whois", "is_fake_inn"
]

LABEL_MAP = {
    "Легальный": 0,
    "Нарушение": 1,
    "Парковка": 2,
}


# ── Загрузка данных ───────────────────────────────────────────────────────────

def load_dataset(path: str):
    with open(path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    X, y = [], []
    skipped = 0
    for item in dataset:
        features = item.get("features")
        label = item.get("label")
        if not features or label not in LABEL_MAP:
            skipped += 1
            continue
        vector = [features.get(key, 0) for key in FEATURE_ORDER]
        X.append(vector)
        y.append(LABEL_MAP[label])

    print(f"Загружено: {len(X)} примеров, пропущено: {skipped}")

    # Распределение классов
    inv_map = {v: k for k, v in LABEL_MAP.items()}
    from collections import Counter
    counts = Counter(y)
    for label_idx, count in sorted(counts.items()):
        print(f"  {inv_map[label_idx]}: {count}")

    return np.array(X, dtype=float), np.array(y, dtype=int)


# ── Модели ────────────────────────────────────────────────────────────────────

def get_models():
    return {
        "Random Forest": RandomForestClassifier(
            n_estimators=100,
            random_state=RANDOM_STATE,
            class_weight="balanced",
        ),
        "KNN": KNeighborsClassifier(
            n_neighbors=5,
            weights="distance",
            metric="euclidean",
        ),
        "CatBoost": CatBoostClassifier(
            iterations=200,
            learning_rate=0.05,
            depth=6,
            random_seed=RANDOM_STATE,
            verbose=0,
            train_dir="",
            auto_class_weights="Balanced",
        )
    }


# ── Кросс-валидация ───────────────────────────────────────────────────────────

def run_cv(models: dict, X: np.ndarray, y: np.ndarray, n_splits: int):
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
    scoring = {
        "f1_macro": "f1_macro",
        "precision": "precision_macro",
        "recall": "recall_macro",
    }

    results = {}
    for name, model in models.items():
        print(f"\nОбучение {name}...")
        cv_res = cross_validate(
            model, X, y,
            cv=cv,
            scoring=scoring,
            return_train_score=False,
            n_jobs=-1,
        )
        results[name] = {
            "f1_macro": cv_res["test_f1_macro"],
            "precision": cv_res["test_precision"],
            "recall": cv_res["test_recall"],
        }
        print(f"  Macro F1:       {cv_res['test_f1_macro'].mean():.3f} ± {cv_res['test_f1_macro'].std():.3f}")
        print(f"  Macro Precision:{cv_res['test_precision'].mean():.3f} ± {cv_res['test_precision'].std():.3f}")
        print(f"  Macro Recall:   {cv_res['test_recall'].mean():.3f} ± {cv_res['test_recall'].std():.3f}")

    return results


# ── График 1: Барчарт средних метрик ─────────────────────────────────────────

def plot_bar_chart(results: dict, save_path: str = "comparison_bar.png"):
    metrics = ["f1_macro", "precision", "recall"]
    metric_labels = ["Макро F1", "Макро Точность", "Макро Полнота"]
    model_names = list(results.keys())

    n_metrics = len(metrics)
    n_models = len(model_names)
    x = np.arange(n_metrics)
    width = 0.25

    colors = ["#1565c0", "#2e7d32", "#c62828"]
    fig, ax = plt.subplots(figsize=(10, 6))

    for i, (name, color) in enumerate(zip(model_names, colors)):
        means = [results[name][m].mean() for m in metrics]
        stds = [results[name][m].std() for m in metrics]
        offset = (i - n_models / 2 + 0.5) * width
        bars = ax.bar(x + offset, means, width, label=name,
                      color=color, alpha=0.85, edgecolor="white")
        ax.errorbar(x + offset, means, yerr=stds,
                    fmt="none", color="black", capsize=4, linewidth=1.2)
        for bar, mean in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.01,
                    f"{mean:.2f}", ha="center", va="bottom",
                    fontsize=9, fontweight="bold")

    ax.set_ylim(0, 1.1)
    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels, fontsize=11)
    ax.set_ylabel("Значение метрики", fontsize=11)
    ax.set_title(f"Сравнение моделей классификации\n(стратифицированная кросс-валидация, {N_SPLITS} фолдов)",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, alpha=0.4, linestyle="--")
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\nБарчарт сохранён: {save_path}")


# ── График 2: Boxplot F1 по фолдам ───────────────────────────────────────────

def plot_boxplot(results: dict, save_path: str = "comparison_boxplot.png"):
    model_names = list(results.keys())
    f1_data = [results[name]["f1_macro"] for name in model_names]

    colors = ["#1565c0", "#2e7d32", "#c62828"]
    fig, ax = plt.subplots(figsize=(7, 5))

    bp = ax.boxplot(f1_data, patch_artist=True, notch=False,
                    medianprops=dict(color="white", linewidth=2.5),
                    whiskerprops=dict(linewidth=1.5),
                    capprops=dict(linewidth=1.5),
                    flierprops=dict(marker="o", markersize=5, alpha=0.5))

    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.8)

    # Подписи медиан
    for i, data in enumerate(f1_data, 1):
        median = np.median(data)
        ax.text(i, median + 0.012, f"{median:.3f}",
                ha="center", va="bottom", fontsize=10,
                fontweight="bold", color="black")

    ax.set_xticks(range(1, len(model_names) + 1))
    ax.set_xticklabels(model_names, fontsize=11)
    ax.set_ylabel("Macro F1", fontsize=11)
    ax.set_title(f"Устойчивость моделей по фолдам кросс-валидации\n({N_SPLITS}-fold, стратификация по классам)",
                 fontsize=12, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, alpha=0.4, linestyle="--")
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Boxplot сохранён: {save_path}")


# ── Точечные метрики для таблицы в ВКР ───────────────────────────────────────

def print_summary_table(results: dict):
    metrics = ["f1_macro", "precision", "recall"]
    metric_labels = ["Макро F1", "Макро Точность", "Макро Полнота"]
    print("\n" + "=" * 65)
    print("СВОДНАЯ ТАБЛИЦА (среднее ± стд. откл. по фолдам)")
    print("=" * 65)
    header = f"{'Модель':<20}" + "".join(f"{m:<22}" for m in metric_labels)
    print(header)
    print("-" * 65)
    for name, res in results.items():
        row = f"{name:<20}"
        for m in metrics:
            row += f"{res[m].mean():.3f} ± {res[m].std():.3f}    "
        print(row)
    print("=" * 65)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Сравнение моделей классификации ===\n")

    X, y = load_dataset(TRAINING_DATA_FILE)
    models = get_models()
    results = run_cv(models, X, y, N_SPLITS)

    print_summary_table(results)
    plot_bar_chart(results, save_path="comparison_bar.png")
    plot_boxplot(results, save_path="comparison_boxplot.png")

    print("\nГотово. Графики сохранены в папке проекта.")
