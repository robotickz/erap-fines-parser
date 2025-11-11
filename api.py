from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Optional
import logging

from database_config import get_db
from models import TrafficFine
from pdf_parser import TrafficFinePDFParser
from pdf_downloader import fetch_and_process_fines
from schemas import UploadResponse, FineListResponse, FineResponse
from security_layer import verify_token

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Application initialization
app = FastAPI(
    title="Traffic Fine Management API",
    description="Secure API for managing traffic violation fines from Almaty Region Police",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Upload directory configuration
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

@app.get("/health", tags=["System"])
async def health_check():

    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "1.0.0"
    }

@app.post(
    "/fines/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_token)],
    tags=["Fines from PDF"]
)
async def upload_fine_pdf(
    file: UploadFile = File(..., description="PDF file with traffic fine"),
    db: Session = Depends(get_db)
):

    
    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are accepted"
        )
    
    # Generate unique filename
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    file_path = UPLOAD_DIR / f"{timestamp}_{file.filename}"
    
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"Saved uploaded file: {file_path}")
        
        # Parse PDF
        parser = TrafficFinePDFParser()
        parsed_data = parser.parse_file(file_path)
        
        if not parsed_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Failed to extract data from PDF"
            )
        
        logger.info(f"Parsed data: {parsed_data.get('prescription_number')}")
        
        existing = db.query(TrafficFine).filter(
            TrafficFine.prescription_number == parsed_data.get('prescription_number')
        ).first()
        
        if existing:
            logger.warning(f"Duplicate prescription number: {parsed_data.get('prescription_number')}")
            return UploadResponse(
                success=False,
                message="Fine already exists in database",
                fine_id=int(existing.id),
                prescription_number=str(existing.prescription_number)
            )
        
        fine = TrafficFine(**parsed_data)
        db.add(fine)
        db.commit()
        db.refresh(fine)
        
        logger.info(f"Created fine record: ID={fine.id}")
        
        return UploadResponse(
            success=True,
            message="Fine successfully processed and saved",
            fine_id=int(fine.id),
            prescription_number=str(fine.prescription_number)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload processing error: {str(e)}")
        # Cleanup file on error
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}"
        )

@app.get(
    "/fines",
    response_model=FineListResponse,
    dependencies=[Depends(verify_token)],
    tags=["Fines from PDF"]
)
async def list_fines(
    license_plate: Optional[str] = Query(None, description="Filter by license plate"),
    violation_date_from: Optional[datetime] = Query(None, description="Start date (inclusive)"),
    violation_date_to: Optional[datetime] = Query(None, description="End date (inclusive)"),
    discount_available_only: bool = Query(False, description="Show only discountable fines"),
    is_paid: Optional[bool] = Query(None, description="Filter by payment status"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
    db: Session = Depends(get_db)
):
 
    
    query = db.query(TrafficFine)
    filters = []
    
    if license_plate:
        filters.append(TrafficFine.license_plate == license_plate.upper())
    
    if violation_date_from:
        filters.append(TrafficFine.violation_datetime >= violation_date_from)
    
    if violation_date_to:
        filters.append(TrafficFine.violation_datetime <= violation_date_to)
    
    if is_paid is not None:
        filters.append(TrafficFine.is_paid == is_paid)
    
    if discount_available_only:
        # Calculate cutoff date for discount eligibility
        cutoff_date = datetime.now(UTC) - timedelta(days=7)
        filters.append(TrafficFine.violation_datetime >= cutoff_date)
        filters.append(TrafficFine.is_paid == False)
    
    if filters:
        query = query.filter(and_(*filters))
    
    total = query.count()    
    fines = query.order_by(TrafficFine.violation_datetime.desc()).offset(skip).limit(limit).all()
    logger.info(f"Retrieved {len(fines)} fines (total: {total})")
    
    # Convert SQLAlchemy models to Pydantic models
    fine_responses = [FineResponse.model_validate(fine) for fine in fines]
    
    return FineListResponse(
        total=total,
        items=fine_responses
    )

@app.get(
    "/fines/{fine_id}",
    response_model=FineResponse,
    dependencies=[Depends(verify_token)],
      tags=["Fines from PDF"]
)
async def get_fine(
    fine_id: int,
    db: Session = Depends(get_db)
):

    fine = db.query(TrafficFine).filter(TrafficFine.id == fine_id).first()
    
    if not fine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fine with ID {fine_id} not found"
        )
    
    return FineResponse.model_validate(fine)

@app.patch(
    "/fines/{fine_id}/mark-paid",
    response_model=FineResponse,
    dependencies=[Depends(verify_token)],
      tags=["Fines from PDF"]
)
async def mark_fine_paid(
    fine_id: int,
    db: Session = Depends(get_db)
):
    fine = db.query(TrafficFine).filter(TrafficFine.id == fine_id).first()
    
    if not fine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fine with ID {fine_id} not found"
        )
    
    fine.is_paid = True
    db.commit()
    db.refresh(fine)
    
    logger.info(f"Marked fine {fine_id} as paid")
    
    return FineResponse.model_validate(fine)

@app.post(
    "/fines/fetch",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_token)],
    tags=["Fines from ERAP API"]
)
async def fetch_fines_from_erap(
    plate_number: str,
    tech_passport: str,
    db: Session = Depends(get_db)
):
    """
    Загружает штрафы из системы eRAP по номеру автомобиля и паспорту ТС
    """
    try:
        logger.info(f"Fetching fines for plate: {plate_number}, passport: {tech_passport}")
        result = fetch_and_process_fines(plate_number, tech_passport, db)
        
        if result["success"]:
            logger.info(f"Successfully fetched fines: {result['message']}")
            
            # Получаем первый сохраненный штраф для отображения в ответе
            first_fine_id = result["saved_ids"][0] if result["saved_ids"] else None
            first_prescription_number = None
            
            if first_fine_id:
                first_fine = db.query(TrafficFine).filter(TrafficFine.id == first_fine_id).first()
                if first_fine:
                    first_prescription_number = first_fine.prescription_number
            
            return UploadResponse(
                success=True,
                message=result["message"],
                fine_id=first_fine_id,
                prescription_number=first_prescription_number
            )
        else:
            logger.error(f"Failed to fetch fines: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching fines from eRAP: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching fines: {str(e)}"
        )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    # Request parameter is required by FastAPI even if not used
    _ = request  # Mark as intentionally unused
    
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    
    # Development server configuration
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
