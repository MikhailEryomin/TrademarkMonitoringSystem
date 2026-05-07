from datetime import datetime
from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Table, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()
DATABASE_URL = "postgresql://postgres:postgres@localhost:5430/trademarks"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

trademark_mktu_association = Table(
    "trademark_mktu_association",
    Base.metadata,
    Column("trademark_id", Integer, ForeignKey("trademarks.id"), primary_key=True),
    Column("mktu_class_id", Integer, ForeignKey("mktu_classes.id"), primary_key=True),
)


class Trademark(Base):
    __tablename__ = "trademarks"

    id = Column(Integer, primary_key=True)
    registration_number = Column(String(50), unique=True, index=True, nullable=True)
    name = Column(String(255), index=True)
    application_number = Column(String(50), unique=True, index=True, nullable=True)
    application_date = Column(Date, nullable=True)
    registration_date = Column(Date, nullable=True)
    status = Column(String(200), nullable=True)
    licensees = Column(String(2000), nullable=True)
    sign_type = Column(String(100), nullable=True)
    image_url = Column(String(512))
    owner_id = Column(Integer, ForeignKey("owners.id"), nullable=False)

    owner = relationship("Owner", back_populates="trademarks")
    mktu_classes = relationship(
        "MKTUClass",
        secondary=trademark_mktu_association,
        back_populates="trademarks",
    )

    def __repr__(self):
        return f"<Trademark(id={self.id}, name='{self.name}')>"


class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)

    trademarks = relationship("Trademark", back_populates="owner")

    def __repr__(self):
        return f"<Owner(id={self.id}, name='{self.name}')>"


class MKTUClass(Base):
    __tablename__ = "mktu_classes"

    id = Column(Integer, primary_key=True)
    number = Column(Integer, nullable=False, index=True)
    description = Column(Text, nullable=False)

    trademarks = relationship(
        "Trademark",
        secondary=trademark_mktu_association,
        back_populates="mktu_classes",
    )

    def __repr__(self):
        return f"<MKTUClass(number={self.number})>"


class ScanResult(Base):
    __tablename__ = "scan_results"

    id = Column(Integer, primary_key=True)
    trademark_id = Column(Integer, ForeignKey("trademarks.id"), nullable=False)
    domain_name = Column(String(255), index=True, nullable=False)
    url = Column(String(512), nullable=False)
    scan_date = Column(DateTime, default=datetime.now)
    features = Column(JSON, nullable=False)
    predicted_category = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=True)

    trademark = relationship("Trademark")

    def __repr__(self):
        return f"<ScanResult(domain='{self.domain_name}', category='{self.predicted_category}')>"


def create_db_and_tables():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created")


if __name__ == "__main__":
    create_db_and_tables()
