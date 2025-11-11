from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from typing import Optional, List

class FineBase(BaseModel):
    
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        validate_assignment=True
    )
    
    prescription_number: str = Field(..., min_length=15, max_length=15)
    license_plate: str = Field(..., min_length=5, max_length=20)
    violation_datetime: datetime
    fine_amount: float = Field(..., gt=0)
    discounted_amount: float = Field(..., gt=0)

class FineCreate(FineBase):

    vehicle_certificate: Optional[str] = None
    vehicle_make_model: Optional[str] = None
    vehicle_color: Optional[str] = None
    violation_location: Optional[str] = None
    violation_description: Optional[str] = None
    detected_speed: Optional[float] = None
    allowed_speed: Optional[float] = None
    speed_with_margin: Optional[float] = None
    device_name: Optional[str] = None
    device_serial: Optional[str] = None
    certificate_number: Optional[str] = None
    certificate_date: Optional[datetime] = None
    certificate_valid_until: Optional[datetime] = None
    owner_name: Optional[str] = None
    owner_bin: Optional[str] = None
    owner_address: Optional[str] = None
    issuing_department: Optional[str] = None
    issuing_officer: Optional[str] = None
    article_code: Optional[str] = None
    
    @field_validator('prescription_number')
    @classmethod
    def validate_prescription_number(cls, v: str) -> str:
        """Ensure prescription number is numeric"""
        if not v.isdigit():
            raise ValueError('Prescription number must contain only digits')
        return v
    
    @field_validator('discounted_amount')
    @classmethod
    def validate_discount(cls, v: float, info) -> float:
        """Ensure discounted amount is approximately 50% of fine"""
        if 'fine_amount' in info.data:
            expected = info.data['fine_amount'] * 0.5
            if abs(v - expected) > 1.0:  # Allow 1 tenge tolerance
                raise ValueError(f'Discounted amount must be ~50% of fine amount')
        return v

class FineResponse(FineBase):
    
    id: int
    vehicle_certificate: Optional[str] = None
    vehicle_make_model: Optional[str] = None
    vehicle_color: Optional[str] = None
    violation_location: Optional[str] = None
    violation_description: Optional[str] = None
    detected_speed: Optional[float] = None
    allowed_speed: Optional[float] = None
    owner_name: Optional[str] = None
    issuing_department: Optional[str] = None
    pdf_url: Optional[str] = None
    created_at: datetime
    is_paid: bool
    
    # Computed fields for client convenience
    discount_available: bool
    days_remaining_for_discount: int
    
    model_config = ConfigDict(from_attributes=True)

class FineListResponse(BaseModel):
    
    total: int = Field(..., description="Total records matching filters")
    items: List[FineResponse]
    
    model_config = ConfigDict(from_attributes=True)

class FineFilterParams(BaseModel):
    
    license_plate: Optional[str] = Field(None, description="Filter by license plate")
    violation_date_from: Optional[datetime] = Field(
        None, 
        description="Filter violations after this date (inclusive)"
    )
    violation_date_to: Optional[datetime] = Field(
        None,
        description="Filter violations before this date (inclusive)"
    )
    discount_available_only: bool = Field(
        False,
        description="Show only fines within discount period"
    )
    is_paid: Optional[bool] = Field(None, description="Filter by payment status")
    
    @field_validator('violation_date_to')
    @classmethod
    def validate_date_range(cls, v: Optional[datetime], info) -> Optional[datetime]:
        """Ensure end date is after start date"""
        if v and 'violation_date_from' in info.data and info.data['violation_date_from']:
            if v < info.data['violation_date_from']:
                raise ValueError('violation_date_to must be after violation_date_from')
        return v

class UploadResponse(BaseModel):
    """Response for PDF upload operations"""
    
    success: bool
    message: str
    fine_id: Optional[int] = None
    prescription_number: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class ErrorResponse(BaseModel):
    """Standardized error response"""
    
    detail: str
    error_code: Optional[str] = None
