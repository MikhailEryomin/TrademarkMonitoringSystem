import json
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay
from sklearn.ensemble import RandomForestClassifier

# Добавляем путь к корню, чтобы импортировать классификатор
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.classifier import TrademarkClassifier


def get_system_metrics():
    print("--- ЗАПУСК ФИНАЛЬНОГО ТЕСТИРОВАНИЯ (80/20) ---")

    # 1. Загрузка данных
    file_path = "../core/training_data_final.json"
    if not os.path.exists(file_path):
        print(f"[!] Файл {file_path} не найден!")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    clf_helper = TrademarkClassifier()

    X = []
    y = []

    for item in dataset:
        # Превращаем словарь признаков в числовой вектор
        vector = clf_helper._dict_to_vector(item['features'])
        X.append(vector)
        y.append(clf_helper.label_map[item['label']])

    X = np.array(X)
    y = np.array(y)

    print(f"Всего загружено записей: {len(X)}")

    # 2. Разделение на Train (80%) и Test (20%)
    # stratify=y гарантирует, что пропорции классов в тесте будут такими же, как в полном датасете
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print(f"Обучающая выборка (Train): {len(X_train)} записей")
    print(f"Тестовая выборка (Test):   {len(X_test)} записей\n")

    # 3. Инициализация и обучение модели только на Train
    model = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        class_weight='balanced'
    )
    model.fit(X_train, y_train)

    # 4. Предсказание на незнакомых данных (Test)
    y_pred = model.predict(X_test)

    # 5. Вывод детального отчета
    print("==================================================")
    print("ОТЧЕТ НА ОТЛОЖЕННОЙ ТЕСТОВОЙ ВЫБОРКЕ (20%)")
    print("==================================================")

    # Чтобы имена классов выводились правильно, достанем их из словаря
    class_names = [clf_helper.inv_label_map[i] for i in sorted(clf_helper.inv_label_map.keys())]

    report = classification_report(y_test, y_pred, target_names=class_names)
    print(report)

    # 6. Отрисовка Матрицы ошибок
    try:
        cm = confusion_matrix(y_test, y_pred)
        disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=class_names)

        # Настройка графики
        fig, ax = plt.subplots(figsize=(8, 6))
        disp.plot(cmap=plt.cm.Blues, ax=ax)
        plt.title("Матрица ошибок (Test Set)")
        plt.tight_layout()

        # Сохраняем картинку
        save_path = "../output/confusion_matrix.png"
        plt.savefig(save_path, dpi=300)
        print(f"\n[+] Матрица ошибок сохранена в: {save_path}")

        # Показываем на экране (можешь закомментировать, если не нужно)
        plt.show()
    except Exception as e:
        print(f"[!] Не удалось отрисовать матрицу ошибок: {e}")


if __name__ == "__main__":
    get_system_metrics()