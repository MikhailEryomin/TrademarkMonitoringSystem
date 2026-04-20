import json
import os
import sys
import pandas as pd
from sklearn.model_selection import cross_validate
from sklearn.metrics import classification_report
from sklearn.ensemble import RandomForestClassifier

# Добавляем путь к корню, чтобы импортировать классификатор
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.classifier import TrademarkClassifier


def get_system_metrics():
    print("--- ЗАПУСК РАСЧЕТА МЕТРИК ---")

    # 1. Загрузка данных
    with open("../core/training_data.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)

    clf_helper = TrademarkClassifier()

    X = []
    y = []

    for item in dataset:
        # Превращаем словарь признаков в числовой вектор (используя логику из классификатора)
        vector = clf_helper._dict_to_vector(item['features'])
        X.append(vector)
        y.append(clf_helper.label_map[item['label']])

    # 2. Кросс-валидация (Разбиваем на 5 частей и тестируем)
    # На малых данных это лучший способ получить "научные" цифры
    scoring = ['precision_macro', 'recall_macro', 'f1_macro']

    # Мы используем ту же модель, что и в проекте
    model = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        class_weight='balanced'
    )

    results = cross_validate(model, X, y, cv=5, scoring=scoring)

    print("\n" + "=" * 30)
    print("ИТОГОВЫЕ МЕТРИКИ ДЛЯ СТАТЬИ (Macro Average):")
    print(f"Precision: {results['test_precision_macro'].mean():.2f}")
    print(f"Recall:    {results['test_recall_macro'].mean():.2f}")
    print(f"F1-score:  {results['test_f1_macro'].mean():.2f}")
    print("=" * 30)

    # 3. Детальный отчет по каждому классу (на всем датасете для справки)
    model.fit(X, y)
    y_pred = model.predict(X)
    report = classification_report(y, y_pred, target_names=clf_helper.inv_label_map.values())

    print("\nДЕТАЛЬНЫЙ ОТЧЕТ ПО КЛАССАМ:")
    print(report)


if __name__ == "__main__":
    get_system_metrics()
