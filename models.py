from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, UTC

Base = declarative_base()

class TrafficFine(Base):
    """Normalized traffic fine record with temporal tracking"""
    __tablename__ = "traffic_fines"
    
    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    prescription_number = Column(String(20), unique=True, nullable=False, index=True)
    
    # Vehicle information
    license_plate = Column(String(20), nullable=False, index=True)
    vehicle_certificate = Column(String(20))
    vehicle_make_model = Column(String(100))
    vehicle_color = Column(String(50))
    
    # Violation details
    violation_datetime = Column(DateTime, nullable=False, index=True)
    violation_location = Column(Text)
    violation_description = Column(Text)
    detected_speed = Column(Float)
    allowed_speed = Column(Float)
    speed_with_margin = Column(Float)
    
    # Camera/Device information
    device_name = Column(String(50))
    device_serial = Column(String(50))
    certificate_number = Column(String(50))
    certificate_date = Column(DateTime)
    certificate_valid_until = Column(DateTime)
    
    # Financial data
    fine_amount = Column(Float, nullable=False)
    discounted_amount = Column(Float, nullable=False)
    discount_deadline_days = Column(Integer, default=7)
    
    # Legal entity information
    owner_name = Column(String(255))
    owner_bin = Column(String(20))
    owner_address = Column(Text)
    
    # Administrative metadata
    issuing_department = Column(String(255))
    issuing_officer = Column(String(255))
    article_code = Column(String(20))  # КоАП article
    
    # Temporal tracking
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    is_paid = Column(Boolean, default=False)
    
    @property
    def discount_available(self) -> bool:
        """Check if discount period is still active"""
        if not self.violation_datetime:
            return False
        # Make both datetimes comparable
        now = datetime.now(UTC)
        violation_dt = self.violation_datetime
        if violation_dt.tzinfo is None:
            violation_dt = violation_dt.replace(tzinfo=UTC)
        delta = now - violation_dt
        return delta.days <= self.discount_deadline_days
    
    @property
    def days_remaining_for_discount(self) -> int:
        """Calculate remaining days for discount"""
        if not self.violation_datetime:
            return 0
        # Make both datetimes comparable
        now = datetime.now(UTC)
        violation_dt = self.violation_datetime
        if violation_dt.tzinfo is None:
            violation_dt = violation_dt.replace(tzinfo=UTC)
        delta = now - violation_dt
        remaining = self.discount_deadline_days - delta.days
        return max(0, remaining)
