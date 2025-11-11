import requests
import urllib3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import logging

from models import TrafficFine

fines_base_url = "https://erap-public.kgp.kz/psap/api/fine/"
pdf_base_url = "https://erap-public.kgp.kz/psap/api/pdf/showpdf/av/"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Отключаем предупреждения о небезопасном SSL соединении
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Directory for PDF files
PDF_DIR = Path(__file__).parent / "traffic_fines" / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)


def download_data(plateNumber: str, techPassport: str, page: int = 1, limit: int = 10):
    """
    Загружает данные о штрафах с API eRAP по номеру автомобиля и паспорту ТС
    
    Args:
        plateNumber: Номерной знак автомобиля
        techPassport: Номер технического паспорта
        page: Номер страницы для пагинации
        limit: Количество записей на странице
        
    Returns:
        dict: JSON ответ от API с данными о штрафах
    """
    try:
        final_url = f"{fines_base_url}?pageNum={page}&limit={limit}&plateNumber={plateNumber}&srtsNum={techPassport}&orderBy=desc"
        logger.info(f"Requesting fines data from: {final_url}")
        response = requests.get(final_url, timeout=30, verify=False)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Successfully retrieved {len(data) if isinstance(data, list) else 0} fines")
        
        return data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading fines data: {str(e)}")
        raise
    except ValueError as e:
        logger.error(f"Error parsing JSON response: {str(e)}")
        raise

def process_data(data: List[Dict], db_session):
    """
    Обрабатывает данные о штрафах и сохраняет их в базу данных
    
    Args:
        data: Список словарей с данными о штрафах
        db_session: Сессия базы данных
        
    Returns:
        List[int]: Список ID созданных записей
    """
    saved_fine_ids = []
    
    for fine_data in data:
        try:
            existing_fine = db_session.query(TrafficFine).filter(
                TrafficFine.prescription_number == fine_data.get('caseNumber')
            ).first()
            
            if existing_fine:
                logger.info(f"Fine with case number {fine_data.get('caseNumber')} already exists")
                continue
            
            pdf_url = f"{pdf_base_url}{fine_data.get('rid')}"
            pdf_path = download_pdf(pdf_url, fine_data.get('caseNumber'))
            
            # Конвертируем даты
            commit_date = None
            if fine_data.get('commitDate'):
                commit_date = datetime.fromisoformat(fine_data['commitDate'].replace('Z', '+00:00'))
            
            decision_date = None
            if fine_data.get('decisionDate'):
                decision_date = datetime.fromisoformat(fine_data['decisionDate'].replace('Z', '+00:00'))
            
            # Создаем запись о штрафе
            penalty_size = fine_data.get('penaltySize', 0)
            # Проверяем, что penalty_size не является пустой строкой или дефисом
            if penalty_size in ('-', '', None):
                penalty_size = 0
            
            new_fine = TrafficFine(
                prescription_number=fine_data.get('caseNumber'),
                license_plate="",  # Будет заполнено позже из запроса
                violation_datetime=commit_date or datetime.now(),
                fine_amount=float(penalty_size),
                discounted_amount=float(penalty_size) * 0.5,  # 50% скидка
                issuing_department=fine_data.get('organ', {}).get('nameRu', ''),
                violation_description=fine_data.get('penaltyMeasure', {}).get('nameRu', ''),
                is_paid=(fine_data.get('status') == 'Оплачен'),
                pdf_url=pdf_path  # Сохраняем путь к PDF файлу
            )
            
            db_session.add(new_fine)
            db_session.flush()  # Получаем ID без коммита
            saved_fine_ids.append(new_fine.id)
            
            logger.info(f"Saved fine with case number: {fine_data.get('caseNumber')}")
            
        except Exception as e:
            logger.error(f"Error processing fine data: {str(e)}")
            db_session.rollback()
            raise
    
    return saved_fine_ids


def download_pdf(link: str, case_number: str) -> Optional[str]:

    try:
        logger.info(f"Downloading PDF from: {link}")
        response = requests.get(link, timeout=30, verify=False)
        response.raise_for_status()
        content_type = response.headers.get('content-type', '')
        if 'application/pdf' not in content_type:
            logger.warning(f"Response does not contain PDF, content-type: {content_type}")
        
        # Формируем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{case_number}_{timestamp}.pdf"
        file_path = PDF_DIR / filename
        
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"PDF saved to: {file_path}")
        return str(file_path)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading PDF: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error saving PDF: {str(e)}")
        return None


def fetch_and_process_fines(plate_number: str, tech_passport: str, db_session) -> Dict:
    # for api
    try:
        fines_data = download_data(plate_number, tech_passport)
        
        if not fines_data:
            logger.info("No fines found for the specified vehicle")
            return {
                "success": True,
                "message": "No fines found",
                "fines_count": 0,
                "saved_ids": []
            }
        
        saved_ids = process_data(fines_data, db_session)
        
        for fine_id in saved_ids:
            fine = db_session.query(TrafficFine).filter(TrafficFine.id == fine_id).first()
            if fine:
                fine.license_plate = plate_number
        
        db_session.commit()
        
        logger.info(f"Successfully processed and saved {len(saved_ids)} fines")
        
        return {
            "success": True,
            "message": f"Successfully processed {len(saved_ids)} fines",
            "fines_count": len(fines_data),
            "saved_ids": saved_ids
        }
        
    except Exception as e:
        logger.error(f"Error in fetch_and_process_fines: {str(e)}")
        db_session.rollback()
        return {
            "success": False,
            "message": f"Error processing fines: {str(e)}",
            "fines_count": 0,
            "saved_ids": []
        }
    