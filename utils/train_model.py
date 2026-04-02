import json
import os
from modules.classifier import TrademarkClassifier

# Путь к файлу с обучающей выборкой (собранной скриптом build_dataset.py)
TRAINING_DATA_FILE = "../core/training_data.json"


def train_classifier():
    print(f"--- ЗАПУСК ОБУЧЕНИЯ ML-МОДЕЛИ ---")

    if not os.path.exists(TRAINING_DATA_FILE):
        print(f"[!] Файл с датасетом {TRAINING_DATA_FILE} не найден!")
        print("Сначала запустите скрипт сборки датасета (build_dataset.py).")
        return

    print("1. Загрузка обучающих данных...")
    with open(TRAINING_DATA_FILE, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    if not dataset:
        print("[!] Датасет пуст. Обучение невозможно.")
        return

    # 2. Подготовка списков X (признаки) и y (метки классов)
    X_train = []
    y_train = []

    # Подсчет статистики для отчета
    class_counts = {}

    for item in dataset:
        features = item.get("features")
        label = item.get("label")

        if not features or not label:
            continue

        # В тренировочную выборку не берем URL или другие метаданные,
        # только словарь с признаками
        X_train.append(features)
        y_train.append(label)

        # Считаем количество примеров каждого класса
        class_counts[label] = class_counts.get(label, 0) + 1

    print(f"Всего загружено примеров: {len(X_train)}")
    print("Распределение классов в датасете:")
    for label, count in class_counts.items():
        print(f"  - {label}: {count} шт.")

    # 3. Инициализация и обучение классификатора
    print("\n2. Инициализация Random Forest Classifier...")
    clf = TrademarkClassifier()

    # Метод train внутри classifier.py:
    # - Превратит словари X_train в строгие числовые массивы (векторы).
    # - Превратит текстовые метки y_train в числа (0, 1, 2, 3).
    # - Обучит модель (model.fit).
    # - Сохранит веса в core/model_dump.pkl (joblib.dump).
    clf.train(X_train, y_train)

    print("\nМодель успешно обучена и сохранена.")
    print("Теперь при запуске пайплайна система будет использовать эту ML-модель для предсказаний.")


if __name__ == "__main__":
    train_classifier()
