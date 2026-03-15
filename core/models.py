from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Date,
    Text,
    ForeignKey
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker

Base = declarative_base()


class Trademark(Base):
    __tablename__ = 'trademarks'

    id = Column(Integer, primary_key=True)
    registration_number = Column(String(50), unique=True, index=True,
                                 nullable=True)  # Номер регистрации (Может быть NULL для заявок)
    application_number = Column(String(50), unique=True, index=True, nullable=False)  # Номер заявки
    application_date = Column(Date, nullable=False)  # Дата подачи заявки
    registration_date = Column(Date, nullable=True)  # Дата регистрации (Может быть NULL для заявок)
    name = Column(String(255), index=True)  # Имя товарного знака
    status = Column(String(50), nullable=False, default='Заявка',
                    index=True)  # Статус: Заявка, Действует, Недействует (истекший срок/прекратил действие)
    sign_type = Column(String(100), nullable=False)  # Тип: Словесный, Изобразительный, Комбинированный
    image_url = Column(String(512))  # Путь к локально сохраненному файлу изображения

    # --- Внешние связи ---
    owner_id = Column(Integer, ForeignKey('owners.id'), nullable=False)

    # Устанавливаем связи: 
    owner = relationship("Owner", back_populates="trademarks")
    mktu_classes = relationship("TrademarkMKTUClass", back_populates="trademark", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Trademark(id={self.id}, name='{self.name}', reg_num='{self.registration_number}')>"


class Owner(Base):
    __tablename__ = 'owners'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    correspondence_address = Column(Text, nullable=True)

    # Устанавливаем обратную связь: у одного владельца может быть много товарных знаков.
    trademarks = relationship("Trademark", back_populates="owner")

    def __repr__(self):
        return f"<Owner(id={self.id}, name='{self.name}')>"


class TrademarkMKTUClass(Base):
    __tablename__ = 'trademark_mktu_classes'

    id = Column(Integer, primary_key=True)
    mktu_class_number = Column(Integer, nullable=False, index=True)
    description = Column(Text, nullable=False)

    trademark_id = Column(Integer, ForeignKey('trademarks.id'), nullable=False)

    trademark = relationship("Trademark", back_populates="mktu_classes")

    def __repr__(self):
        return f"<MKTUClass(class={self.mktu_class_number}, trademark_id={self.trademark_id})>"


class ScanResult(Base):
    __tablename__ = 'scan_results'

    id = Column(Integer, primary_key=True)
    trademark_id = Column(Integer, ForeignKey('trademarks.id'))
    domain_name = Column(String(255), index=True)
    scan_date = Column(DateTime, default=datetime.utcnow)

    # Raw Data from Scraper
    url = Column(String)
    http_status = Column(Integer)
    is_parked = Column(Boolean, default=False)

    # Calculated Features
    domain_similarity = Column(Float)  # Левенштейн
    content_homogeneity = Column(Float)  # Косинусное сходство векторов

    # LLM Extracted Features
    llm_verdict_json = Column(JSON)  # Ответ от LLM

    # Final Classification
    predicted_category = Column(String(50))  # Legal, Infringement...
    is_confirmed = Column(Boolean, default=False)  # Флаг проверки человеком

    trademark = relationship("Trademark")


DATABASE_URL = "postgresql://postgres:postgres@localhost/trademarks"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_db_and_tables():
    print("Creating database and tables...")
    Base.metadata.create_all(bind=engine)
    print("Database and tables created successfully.")


if __name__ == "__main__":
    create_db_and_tables()
