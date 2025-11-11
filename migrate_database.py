#!/usr/bin/env python3
"""
Скрипт для миграции базы данных и добавления недостающих колонок
"""
import logging
from sqlalchemy import create_engine, text
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Путь к базе данных
DATABASE_DIR = Path(__file__).parent / "traffic_fines"
DATABASE_URL = f"sqlite:///{DATABASE_DIR}/fines.db"

def migrate_database():
    """Выполняет миграцию базы данных"""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # Проверяем, существует ли колонка pdf_url
            result = conn.execute(text("PRAGMA table_info(traffic_fines)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'pdf_url' not in columns:
                logger.info("Adding pdf_url column to traffic_fines table...")
                conn.execute(text("ALTER TABLE traffic_fines ADD COLUMN pdf_url VARCHAR(500)"))
                conn.commit()
                logger.info("Successfully added pdf_url column")
            else:
                logger.info("pdf_url column already exists")
            
            # Проверяем другие возможные недостающие колонки
            required_columns = [
                'vehicle_certificate', 'vehicle_make_model', 'vehicle_color',
                'violation_location', 'detected_speed', 'allowed_speed',
                'speed_with_margin', 'device_name', 'device_serial',
                'certificate_number', 'certificate_date', 'certificate_valid_until',
                'owner_name', 'owner_bin', 'owner_address',
                'issuing_officer', 'article_code'
            ]
            
            for column in required_columns:
                if column not in columns:
                    column_type = "TEXT" if column.endswith('_name') or column.endswith('_address') or column in ['vehicle_make_model', 'vehicle_color', 'violation_location', 'device_name', 'device_serial', 'certificate_number', 'article_code'] else "FLOAT"
                    if column.endswith('_date') or column == 'violation_datetime':
                        column_type = "DATETIME"
                    elif column in ['is_paid']:
                        column_type = "BOOLEAN"
                    
                    logger.info(f"Adding {column} column to traffic_fines table...")
                    conn.execute(text(f"ALTER TABLE traffic_fines ADD COLUMN {column} {column_type}"))
                    conn.commit()
                    logger.info(f"Successfully added {column} column")
            
            logger.info("Database migration completed successfully")
            
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise

if __name__ == "__main__":
    migrate_database()