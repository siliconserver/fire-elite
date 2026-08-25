import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Role(str, enum.Enum):
    admin = "admin"
    viewer = "viewer"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.viewer)

    totp_secret = Column(String(32), nullable=True)
    totp_enabled = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Art(str, enum.Enum):
    th = "TH"
    brand = "Brand"
    dienstleistung = "Dienstleistung"
    gefahrstoffe = "Gefahrstoffe"


class Funktion(str, enum.Enum):
    tm = "TM"
    agt = "AGT"
    ma = "MA"
    fez = "FEZ"
    gf = "GF"
    el = "EL"
    in_bereitstellung = "In Bereitstellung"


class AgtGeraet(str, enum.Enum):
    pa = "PA"
    filter = "Filter"
    csa = "CSA"


class Einsatzmittel(Base):
    __tablename__ = "einsatzmittel"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    einsaetze = relationship("Einsatz", back_populates="einsatzmittel")


class Einsatz(Base):
    __tablename__ = "einsaetze"

    # id ist der reine Datenbank-Primärschlüssel, unveränderlich.
    # nummer ist die fortlaufende, vom Nutzer sichtbare/editierbare
    # Einsatznummer - getrennt voneinander, damit ein nachträglich
    # eingefügter Einsatz alle folgenden Nummern verschieben kann,
    # ohne dass sich die interne Identität der Zeilen ändert.
    id = Column(Integer, primary_key=True)
    nummer = Column(Integer, unique=True, nullable=False, index=True)

    start = Column(DateTime(timezone=True), nullable=False)
    ende = Column(DateTime(timezone=True), nullable=False)

    ort = Column(String(255), nullable=False)
    art = Column(Enum(Art), nullable=False)
    funktion = Column(Enum(Funktion), nullable=False)
    eingesetzt = Column(Boolean, nullable=False, default=True)
    alarmierung = Column(String(255), nullable=False)
    bemerkungen = Column(Text, nullable=True)

    einsatzmittel_id = Column(
        Integer, ForeignKey("einsatzmittel.id", ondelete="RESTRICT"), nullable=True
    )
    einsatzmittel = relationship("Einsatzmittel", back_populates="einsaetze")

    # nur befüllt, wenn funktion == AGT
    angeschnauft = Column(Boolean, nullable=True)
    # nur befüllt, wenn angeschnauft == True
    agt = Column(Enum(AgtGeraet), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


DEFAULT_WEEKLY_REPORT_SUBJECT = "Wöchentlicher Einsatz-Report"
DEFAULT_WEEKLY_REPORT_INTRO = (
    "Hallo,\n\nhier der wöchentliche Überblick über die Einsätze der letzten 7 Tage:\n"
)


class Settings(Base):
    """Singleton-Tabelle (immer nur die Zeile mit id=1) mit allen konfigurierbaren Einstellungen."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, default=1)

    # Empfänger des wöchentlichen Reports
    admin_email = Column(String(255), nullable=True)

    # Zeitplan (jeweils "HH:MM", 24h)
    weekly_report_day = Column(String(3), nullable=False, default="mon")  # mon..sun
    weekly_report_time = Column(String(5), nullable=False, default="07:00")
    backup_time = Column(String(5), nullable=False, default="03:00")
    backup_retention = Column(Integer, nullable=False, default=14)

    # E-Mail-Texte
    weekly_report_subject = Column(Text, nullable=False, default=DEFAULT_WEEKLY_REPORT_SUBJECT)
    weekly_report_intro = Column(Text, nullable=False, default=DEFAULT_WEEKLY_REPORT_INTRO)

    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
