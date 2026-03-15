import csv
import datetime
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# -------------------------------------------------------------

from core.models import SessionLocal, Owner, Trademark, TrademarkMKTUClass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNERS_FILE = os.path.join(BASE_DIR, 'utils', 'data', 'owners.csv')
TRADEMARKS_FILE = os.path.join(BASE_DIR, 'utils', 'data', 'trademarks.csv')


def seed_owners(session):
    print("Seeding owners...")
    with open(OWNERS_FILE, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file, delimiter=';')
        for row in reader:
            
            # Проверяем, существует ли уже такой владелец
            existing_owner = session.query(Owner).filter_by(name=row['name']).first()
            if not existing_owner:
                owner = Owner(name=row['name'], correspondence_address=row['correspondence_address'])
                session.add(owner)
                print(f"  - Added owner: {row['name']}")

    session.commit()


def seed_trademarks(session):
    print("Seeding trademarks...")
    with open(TRADEMARKS_FILE, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file, delimiter=';')
        for row in reader:
            reg_num = row['registration_number']
            
            # Проверяем, существует ли уже такой знак
            existing_trademark = session.query(Trademark).filter_by(registration_number=reg_num).first()
            if existing_trademark:
                print(f"  - Trademark {reg_num} already exists. Skipping.")
                continue

            # Находим ID владельца в нашей БД
            owner = session.query(Owner).filter_by(name=row['owner_name']).first()
            if not owner:
                print(f"  - ERROR: Owner '{row['owner_name']}' not found for trademark {reg_num}. Skipping.")
                continue

            # Создаем объект товарного знака
            new_trademark = Trademark(
                registration_number=reg_num,
                application_number=row['application_number'],
                application_date=datetime.datetime.strptime(row['application_date'], '%Y-%m-%d').date(),
                registration_date=datetime.datetime.strptime(row['registration_date'], '%Y-%m-%d').date() if row['registration_date'] else None,
                name=row['name'],
                status=row['status'],
                sign_type=row['sign_type'],
                image_url=row['image_url'] if row['image_url'] else None,
                owner=owner
            )

            # Парсим и добавляем классы МКТУ
            mktu_classes_str = row['mktu_classes']
            if mktu_classes_str:
                class_parts = mktu_classes_str.split('|')
                for part in class_parts:
                    try:
                        number_str, description = part.split('::', 1)
                        mktu_class = TrademarkMKTUClass(
                            mktu_class_number=int(number_str),
                            description=description.strip()
                        )
                        new_trademark.mktu_classes.append(mktu_class)
                    except ValueError:
                        print(f"  - WARNING: Could not parse MKTU class part: '{part}' for trademark {reg_num}")

            session.add(new_trademark)
            print(f"  - Added trademark: {reg_num} ('{row['name']}')")
    session.commit()


def seed_database():
    print("Starting database seeding...")
    
    with SessionLocal() as session:
        try:
            # Сначала заполняем владельцев, потом знаки, т.к. знаки на них ссылаются
            seed_owners(session)
            seed_trademarks(session)
            
            print("Database seeding completed successfully.")

        except Exception as e:
            print(f"An error occurred during seeding: {e}")
            session.rollback()

if __name__ == "__main__":
    seed_database()
