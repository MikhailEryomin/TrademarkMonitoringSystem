from sentence_transformers import SentenceTransformer
import os

# Путь, куда мы сохраним модель внутри проекта
MODEL_PATH = os.path.join("..", "core", "rubert-tiny2-local")

print("Скачивание модели из Hugging Face...")
model = SentenceTransformer('cointegrated/rubert-tiny2')
#model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

print(f"Сохранение модели локально в папку {MODEL_PATH}...")
model.save(MODEL_PATH)

print("Успешно!")