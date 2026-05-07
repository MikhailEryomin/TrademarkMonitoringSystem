import json
import os
import sys

import matplotlib.pyplot as plt
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay
from sklearn.model_selection import train_test_split
from modules.classifier import TrademarkClassifier


def run_system_test():
    print("--- ЗАПУСК СИСТЕМНОГО ТЕСТИРОВАНИЯ (ЭВРИСТИКИ + ML) ---")

    # 1. Загрузка исходного JSON
    file_path = "../core/training_data_final.json"
    with open(file_path, "r", encoding="utf-8") as f:
        full_dataset = json.load(f)

    # 2. Подготовка данных для разделения
    # Нам нужны отдельно списки словарей признаков и текстовых меток
    all_features = [item['features'] for item in full_dataset]
    all_labels = [item['label'] for item in full_dataset]

    # 3. Разделение 80/20
    X_train, X_test, y_train, y_test = train_test_split(
        all_features,
        all_labels,
        test_size=0.2,
        random_state=42,
        stratify=all_labels
    )

    print(f"Обучение на: {len(X_train)} сайтах")
    print(f"Тестирование на: {len(X_test)} сайтах\n")

    # 4. Инициализация и обучение системы
    clf = TrademarkClassifier()
    # Используем ТВОЙ метод train (принимает список диктов и список строк)
    clf.train(X_train, y_train)

    # 5. Тестирование через системный метод predict (Эвристики + ML)
    y_pred_system = []

    for feat_dict in X_test:
        # Вызываем боевой метод, который сначала прогоняет эвристики, а потом ML
        res = clf.predict(feat_dict)

        # Если модель выдала "Требует проверки" из-за низкой уверенности,
        # для расчета метрик нам нужно сопоставить это с каким-то базовым классом.
        # Но в идеале predict должен вернуть класс, а мы его замерим.
        y_pred_system.append(res['class'])

    # 6. Вывод отчета
    # Важно: в y_test у нас могут быть "Легальный", "Нарушение", "Парковка".
    # Если predict выдал "Требует проверки", это будет считаться ошибкой в данном отчете,
    # что методически верно (система не смогла принять решение сама).

    print("==================================================")
    print("ИТОГОВЫЕ МЕТРИКИ ВСЕЙ СИСТЕМЫ (ГИБРИДНЫЙ ПОДХОД)")
    print("==================================================")

    # Определяем уникальные метки, которые реально есть в тесте и предсказании
    target_names = sorted(list(set(y_test) | set(y_pred_system)))

    report = classification_report(y_test, y_pred_system, target_names=target_names)
    print(report)

    # 7. Матрица ошибок
    cm = confusion_matrix(y_test, y_pred_system, labels=target_names)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=target_names)
    fig, ax = plt.subplots(figsize=(10, 8))
    disp.plot(cmap=plt.cm.Greens, ax=ax)
    plt.title("System Confusion Matrix (Heuristics + ML)")
    plt.savefig("../output/system_confusion_matrix.png")
    print("\n[+] Матрица ошибок системы сохранена в output/system_confusion_matrix.png")
    plt.show()


if __name__ == "__main__":
    run_system_test()