import requests
import urllib3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from models import TrafficFine
from pdf_parser import TrafficFinePDFParser

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
    pdf_downloads = []
    
    # Первый проход: проверяем существующие штрафы и готовим скачивание PDF
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
            
            if pdf_path:
                pdf_downloads.append({
                    'fine_data': fine_data,
                    'pdf_path': pdf_path,
                    'pdf_url': pdf_url  # Сохраняем оригинальный URL
                })
            
        except Exception as e:
            logger.error(f"Error preparing fine data: {str(e)}")
            continue
    
    # Запускаем параллельный парсинг PDF файлов
    if pdf_downloads:
        logger.info(f"Starting parallel parsing of {len(pdf_downloads)} PDF files")
        logger.debug(f"PDF downloads prepared: {[item['fine_data'].get('caseNumber') for item in pdf_downloads]}")
        
        # Используем последовательную обработку вместо параллельной из-за проблем с сессиями
        for i, item in enumerate(pdf_downloads, 1):
            try:
                fine_id = parse_pdf_and_create_fine(item, db_session)
                if fine_id:
                    saved_fine_ids.append(fine_id)
                    logger.info(f"[{i}/{len(pdf_downloads)}] Successfully processed fine: {item['fine_data'].get('caseNumber')}")
                else:
                    logger.warning(f"[{i}/{len(pdf_downloads)}] Failed to process fine: {item['fine_data'].get('caseNumber')}")
            except Exception as e:
                logger.error(f"[{i}/{len(pdf_downloads)}] Error processing PDF for {item['fine_data'].get('caseNumber')}: {str(e)}")
        
        logger.info(f"Processing completed. Successfully processed {len(saved_fine_ids)} out of {len(pdf_downloads)} files")
    
    return saved_fine_ids


def parse_pdf_and_create_fine(item: Dict, db_session) -> Optional[int]:
    """
    Парсит PDF файл и создает запись о штрафе в базе данных
    
    Args:
        item: Словарь с данными о штрафе и путем к PDF
        db_session: Сессия базы данных
        
    Returns:
        Optional[int]: ID созданной записи или None в случае ошибки
    """
    fine_data = item['fine_data']
    pdf_path = item['pdf_path']
    pdf_url = item['pdf_url']
    case_number = fine_data.get('caseNumber')
    
    logger.info(f"Starting PDF parsing for case number: {case_number}")
    logger.debug(f"PDF path: {pdf_path}, Original URL: {pdf_url}")
    
    try:
        # Парсим PDF файл
        logger.info(f"Initializing parser for {case_number}")
        parser = TrafficFinePDFParser()
        parsed_data = parser.parse_file(Path(pdf_path))
        
        logger.info(f"Successfully parsed PDF for {case_number}")
        logger.debug(f"Parsed data keys: {list(parsed_data.keys())}")
        
        # Конвертируем даты
        commit_date = None
        if fine_data.get('commitDate'):
            commit_date = datetime.fromisoformat(fine_data['commitDate'].replace('Z', '+00:00'))
        
        decision_date = None
        if fine_data.get('decisionDate'):
            decision_date = datetime.fromisoformat(fine_data['decisionDate'].replace('Z', '+00:00'))
        
        # Создаем запись о штрафе с данными из API и парсинга
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
            pdf_url=pdf_url,  # Сохраняем оригинальный URL вместо локального пути
            
            # Данные из парсера (если они есть)
            vehicle_certificate=parsed_data.get('vehicle_certificate'),
            vehicle_make_model=parsed_data.get('vehicle_make_model'),
            vehicle_color=parsed_data.get('vehicle_color'),
            violation_location=parsed_data.get('violation_location'),
            detected_speed=parsed_data.get('detected_speed'),
            allowed_speed=parsed_data.get('allowed_speed'),
            speed_with_margin=parsed_data.get('speed_with_margin'),
            device_name=parsed_data.get('device_name'),
            device_serial=parsed_data.get('device_serial'),
            certificate_number=parsed_data.get('certificate_number'),
            certificate_date=parsed_data.get('certificate_date'),
            certificate_valid_until=parsed_data.get('certificate_valid_until'),
            owner_name=parsed_data.get('owner_name'),
            owner_bin=parsed_data.get('owner_bin'),
            owner_address=parsed_data.get('owner_address'),
            issuing_officer=parsed_data.get('issuing_officer'),
            article_code=parsed_data.get('article_code')
        )
        
        # Если есть данные из парсера, обновляем некоторые поля
        if parsed_data.get('fine_amount'):
            new_fine.fine_amount = parsed_data.get('fine_amount')
        if parsed_data.get('discounted_amount'):
            new_fine.discounted_amount = parsed_data.get('discounted_amount')
        if parsed_data.get('violation_description'):
            new_fine.violation_description = parsed_data.get('violation_description')
        
        db_session.add(new_fine)
        db_session.flush()  # Получаем ID без коммита
        logger.info(f"Created fine record with ID: {new_fine.id} from parsed PDF")
        logger.debug(f"Fine details - Plate: {new_fine.license_plate}, Amount: {new_fine.fine_amount}, URL: {new_fine.pdf_url}")
        
        return new_fine.id
        
    except Exception as e:
        logger.error(f"Error parsing PDF and creating fine for case {case_number}: {str(e)}")
        logger.debug(f"Exception details:", exc_info=True)
        db_session.rollback()
        return None


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
    