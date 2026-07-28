from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    REAL,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ExternalOrganization(Base):
    """Client, entreprise, école, université, commune ou autre organisme externe."""

    __tablename__ = "external_organization"
    __table_args__ = {"schema": "faceid"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    legal_name: Mapped[str] = mapped_column(String(160), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(60))
    organization_type: Mapped[str] = mapped_column(String(40), nullable=False)
    relationship_to_onee: Mapped[str] = mapped_column(String(40), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    visitor_profiles: Mapped[list[VisitorProfile]] = relationship(
        "VisitorProfile",
        back_populates="organization",
        foreign_keys="VisitorProfile.organization_id",
    )
    visits: Mapped[list[Visit]] = relationship(
        "Visit",
        back_populates="organization",
        foreign_keys="Visit.organization_id",
    )


class OrganizationalUnit(Base):
    """Unité interne ONEE : direction régionale, division ou service."""

    __tablename__ = "organizational_unit"
    __table_args__ = {"schema": "faceid"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.organizational_unit.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    parent: Mapped[OrganizationalUnit | None] = relationship(
        "OrganizationalUnit",
        remote_side="OrganizationalUnit.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    children: Mapped[list[OrganizationalUnit]] = relationship(
        "OrganizationalUnit",
        back_populates="parent",
        foreign_keys="OrganizationalUnit.parent_id",
    )
    assignments: Mapped[list[InternalAssignment]] = relationship(
        "InternalAssignment",
        back_populates="organizational_unit",
        foreign_keys="InternalAssignment.organizational_unit_id",
    )
    hosted_visits: Mapped[list[Visit]] = relationship(
        "Visit",
        back_populates="host_unit",
        foreign_keys="Visit.host_unit_id",
    )


class Person(Base):
    """Identité commune d'un agent ONEE ou d'un visiteur."""

    __tablename__ = "person"
    __table_args__ = {"schema": "faceid"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    cin: Mapped[str | None] = mapped_column(String(30))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(160))
    person_type: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    employee_profile: Mapped[EmployeeProfile | None] = relationship(
        "EmployeeProfile",
        back_populates="person",
        uselist=False,
        foreign_keys="EmployeeProfile.person_id",
    )
    visitor_profile: Mapped[VisitorProfile | None] = relationship(
        "VisitorProfile",
        back_populates="person",
        uselist=False,
        foreign_keys="VisitorProfile.person_id",
    )
    assignments: Mapped[list[InternalAssignment]] = relationship(
        "InternalAssignment",
        back_populates="person",
        foreign_keys="InternalAssignment.person_id",
    )
    face_embeddings: Mapped[list[FaceEmbedding]] = relationship(
        "FaceEmbedding",
        back_populates="person",
        foreign_keys="FaceEmbedding.person_id",
    )
    recognition_events: Mapped[list[RecognitionEvent]] = relationship(
        "RecognitionEvent",
        back_populates="matched_person",
        foreign_keys="RecognitionEvent.matched_person_id",
    )
    presence_events: Mapped[list[PresenceEvent]] = relationship(
        "PresenceEvent",
        back_populates="person",
        foreign_keys="PresenceEvent.person_id",
    )
    user_account: Mapped[UserAccount | None] = relationship(
        "UserAccount",
        back_populates="person",
        uselist=False,
        foreign_keys="UserAccount.person_id",
    )


class EmployeeProfile(Base):
    """Informations propres à une personne de type EMPLOYEE."""

    __tablename__ = "employee_profile"
    __table_args__ = {"schema": "faceid"}

    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.person.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    matricule: Mapped[str] = mapped_column(String(50), nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    job_title: Mapped[str | None] = mapped_column(String(140))
    employment_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'ACTIVE'"),
    )

    person: Mapped[Person] = relationship(
        "Person",
        back_populates="employee_profile",
        foreign_keys=[person_id],
    )
    hosted_visits: Mapped[list[Visit]] = relationship(
        "Visit",
        back_populates="host_employee",
        foreign_keys="Visit.host_employee_id",
    )


class VisitorProfile(Base):
    """Informations propres à une personne de type VISITOR."""

    __tablename__ = "visitor_profile"
    __table_args__ = {"schema": "faceid"}

    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.person.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    visitor_type: Mapped[str] = mapped_column(String(40), nullable=False)
    organization_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.external_organization.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )

    person: Mapped[Person] = relationship(
        "Person",
        back_populates="visitor_profile",
        foreign_keys=[person_id],
    )
    organization: Mapped[ExternalOrganization] = relationship(
        "ExternalOrganization",
        back_populates="visitor_profiles",
        foreign_keys=[organization_id],
    )
    visits: Mapped[list[Visit]] = relationship(
        "Visit",
        back_populates="visitor_profile",
        foreign_keys="Visit.visitor_person_id",
    )


class InternalAssignment(Base):
    """Affectation historique d'un agent ou d'un stagiaire à une unité ONEE."""

    __tablename__ = "internal_assignment"
    __table_args__ = {"schema": "faceid"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.person.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    organizational_unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.organizational_unit.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    position_title: Mapped[str | None] = mapped_column(String(140))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    person: Mapped[Person] = relationship(
        "Person",
        back_populates="assignments",
        foreign_keys=[person_id],
    )
    organizational_unit: Mapped[OrganizationalUnit] = relationship(
        "OrganizationalUnit",
        back_populates="assignments",
        foreign_keys=[organizational_unit_id],
    )


class FaceEmbedding(Base):
    """Un embedding SFace de 128 nombres réels appartenant à une personne."""

    __tablename__ = "face_embedding"
    __table_args__ = {"schema": "faceid"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.person.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(
        ARRAY(REAL, dimensions=1),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        server_default=text("'SFace'"),
    )
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    capture_label: Mapped[str | None] = mapped_column(String(80))
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    person: Mapped[Person] = relationship(
        "Person",
        back_populates="face_embeddings",
        foreign_keys=[person_id],
    )


class UserAccount(Base):
    """Compte de connexion au dashboard."""

    __tablename__ = "user_account"
    __table_args__ = {"schema": "faceid"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    person_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.person.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        unique=True,
    )
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    person: Mapped[Person | None] = relationship(
        "Person",
        back_populates="user_account",
        foreign_keys=[person_id],
    )
    created_visits: Mapped[list[Visit]] = relationship(
        "Visit",
        back_populates="creator",
        foreign_keys="Visit.created_by",
    )
    created_presence_events: Mapped[list[PresenceEvent]] = relationship(
        "PresenceEvent",
        back_populates="creator",
        foreign_keys="PresenceEvent.created_by",
    )


class Visit(Base):
    """Contexte métier d'une venue d'un visiteur."""

    __tablename__ = "visit"
    __table_args__ = {"schema": "faceid"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    visitor_person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.visitor_profile.person_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    organization_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.external_organization.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    host_employee_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.employee_profile.person_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )
    host_unit_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.organizational_unit.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )
    purpose: Mapped[str] = mapped_column(String(300), nullable=False)
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'PLANNED'"),
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.user_account.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    visitor_profile: Mapped[VisitorProfile] = relationship(
        "VisitorProfile",
        back_populates="visits",
        foreign_keys=[visitor_person_id],
    )
    organization: Mapped[ExternalOrganization] = relationship(
        "ExternalOrganization",
        back_populates="visits",
        foreign_keys=[organization_id],
    )
    host_employee: Mapped[EmployeeProfile | None] = relationship(
        "EmployeeProfile",
        back_populates="hosted_visits",
        foreign_keys=[host_employee_id],
    )
    host_unit: Mapped[OrganizationalUnit | None] = relationship(
        "OrganizationalUnit",
        back_populates="hosted_visits",
        foreign_keys=[host_unit_id],
    )
    creator: Mapped[UserAccount | None] = relationship(
        "UserAccount",
        back_populates="created_visits",
        foreign_keys=[created_by],
    )
    presence_events: Mapped[list[PresenceEvent]] = relationship(
        "PresenceEvent",
        back_populates="visit",
        foreign_keys="PresenceEvent.visit_id",
    )


class RecognitionEvent(Base):
    """Résultat de chaque tentative de reconnaissance faciale."""

    __tablename__ = "recognition_event"
    __table_args__ = {"schema": "faceid"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    matched_person_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.person.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    threshold_used: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    liveness_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    device_code: Mapped[str | None] = mapped_column(String(80))
    snapshot_path: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)

    matched_person: Mapped[Person | None] = relationship(
        "Person",
        back_populates="recognition_events",
        foreign_keys=[matched_person_id],
    )
    presence_event: Mapped[PresenceEvent | None] = relationship(
        "PresenceEvent",
        back_populates="recognition_event",
        uselist=False,
        foreign_keys="PresenceEvent.recognition_event_id",
    )


class PresenceEvent(Base):
    """Entrée ou sortie réellement enregistrée."""

    __tablename__ = "presence_event"
    __table_args__ = {"schema": "faceid"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.person.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    recognition_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.recognition_event.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )
    visit_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.visit.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )
    event_type: Mapped[str] = mapped_column(String(10), nullable=False)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'VALID'"),
    )
    note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "faceid.user_account.id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    person: Mapped[Person] = relationship(
        "Person",
        back_populates="presence_events",
        foreign_keys=[person_id],
    )
    recognition_event: Mapped[RecognitionEvent | None] = relationship(
        "RecognitionEvent",
        back_populates="presence_event",
        foreign_keys=[recognition_event_id],
    )
    visit: Mapped[Visit | None] = relationship(
        "Visit",
        back_populates="presence_events",
        foreign_keys=[visit_id],
    )
    creator: Mapped[UserAccount | None] = relationship(
        "UserAccount",
        back_populates="created_presence_events",
        foreign_keys=[created_by],
    )