import asyncio
import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict
from functools import partial
import platform

import pyautogui
import pyperclip
from playwright.async_api import async_playwright, Page, Browser
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()


class ConfigDict(BaseSettings):
    base_url: str = Field(default="https://erap-public.kgp.kz/#/login")
    cert_password: str = Field(..., description="Certificate password")

    coordinates_file: Path = Field(default=Path("./coordinates.json"))
    download_dir: Path = Field(default=Path("./downloads"))
    screenshot_dir: Path = Field(default=Path("./screenshots"))

    headless: bool = Field(default=False)
    timeout: int = Field(default=60000)

    ncalayer_password_delay: float = Field(default=3.0)
    ncalayer_cert_delay: float = Field(default=2.5)
    typing_interval: float = Field(default=0.1)

    class ConfigDict:
        env_file = ".env"
        env_prefix = ""


logger = logging.getLogger(__name__)


class CoordinatesCalibration:
    """Калибровка координат окна NCALayer"""

    def __init__(self, config: ConfigDict):
        self.config = config
        self.coordinates: Dict = {}

    def load_coordinates(self) -> bool:
        """Загрузить сохраненные координаты"""
        if not self.config.coordinates_file.exists():
            return False

        try:
            with open(self.config.coordinates_file, 'r') as f:
                self.coordinates = json.load(f)

            required_keys = ['password_field_x', 'password_field_y',
                             'cert_item_x', 'cert_item_y']

            if all(key in self.coordinates for key in required_keys):
                if logger:
                    logger.info(f"✓ Координаты загружены: {self.coordinates}")
                return True

            return False
        except Exception as e:
            if logger:
                logger.error(f"✗ Ошибка загрузки координат: {e}")
            return False

    async def calibrate(self) -> bool:
        """Интерактивная калибровка координат"""
        print("\n" + "=" * 70)
        print("РЕЖИМ КАЛИБРОВКИ КООРДИНАТ")
        print("=" * 70)

        # Калибровка поля пароля
        print("\n1️⃣  КАЛИБРОВКА ПОЛЯ ВВОДА ПАРОЛЯ")
        print("   Окно NCALayer уже открыто.")
        print("   Кликните ТОЧНО на поле ввода пароля.")
        print("\n   Нажмите Enter когда будете готовы...")
        input()

        print("   ⏳ Ожидание клика...")
        print("   📍 У вас есть 5 секунд, чтобы кликнуть на поле пароля!")
        print("   Кликните прямо сейчас...")

        # Ожидание клика пользователя
        initial_pos = pyautogui.position()
        for i in range(50):  # 5 секунд
            await asyncio.sleep(0.1)
            current_pos = pyautogui.position()
            if current_pos != initial_pos:
                # Детектим клик по изменению позиции
                await asyncio.sleep(0.2)
                password_x, password_y = pyautogui.position()
                print(f"   ✓ Записаны координаты поля пароля: ({password_x}, {password_y})")
                break
        else:
            print("   ✗ Время вышло, используем текущую позицию курсора")
            password_x, password_y = pyautogui.position()

        self.coordinates['password_field_x'] = password_x
        self.coordinates['password_field_y'] = password_y

        # Калибровка сертификата
        print("\n2️⃣  КАЛИБРОВКА ЭЛЕМЕНТА СЕРТИФИКАТА")
        print("   Сейчас введите пароль ВРУЧНУЮ и нажмите Enter.")
        print("   После этого появится второе окно со списком сертификатов.")
        print("\n   Нажмите Enter когда введете пароль и увидите окно с сертификатами...")
        input()

        print("   📍 Кликните на СЕРТИФИКАТ (первый элемент в списке)!")

        print("   📍 У вас есть 5 секунд, чтобы кликнуть на сертификат!")
        print("   Кликните прямо сейчас...")

        initial_pos = pyautogui.position()
        for i in range(50):
            await asyncio.sleep(0.1)
            current_pos = pyautogui.position()
            if current_pos != initial_pos:
                await asyncio.sleep(0.2)
                cert_x, cert_y = pyautogui.position()
                print(f"   ✓ Записаны координаты сертификата: ({cert_x}, {cert_y})")
                break
        else:
            print("   ✗ Время вышло, используем текущую позицию курсора")
            cert_x, cert_y = pyautogui.position()

        self.coordinates['cert_item_x'] = cert_x
        self.coordinates['cert_item_y'] = cert_y

        # Сохранение
        self.config.coordinates_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.coordinates_file, 'w', encoding='utf-8') as f:
            json.dump(self.coordinates, f, indent=2, ensure_ascii=False)

        print("\n✅ Калибровка завершена!")
        print(f"📁 Координаты сохранены в: {self.config.coordinates_file}")
        print("\nТеперь можете запустить скрипт снова для автоматической работы.")
        print("=" * 70 + "\n")

        return True

    def get_coordinates(self) -> Dict:
        return self.coordinates


class NCALayerAutomation:
    """Автоматизация NCALayer с использованием сохраненных координат"""

    def __init__(self, config: ConfigDict, coordinates: Dict):
        self.config = config
        self.coords = coordinates
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1

    async def enter_password(self, password: str) -> bool:
        try:
            if logger:
                logger.info("⚙ Ввод пароля...")

            await asyncio.sleep(self.config.ncalayer_password_delay)

            # Клик на поле пароля
            x, y = self.coords['password_field_x'], self.coords['password_field_y']
            click_func = partial(pyautogui.click, x, y)
            await asyncio.to_thread(click_func)

            if logger:
                logger.info(f"✓ Клик на поле ({x}, {y})")

            await asyncio.sleep(0.8)

            # Попытка 1: write() с interval
            try:
                write_func = partial(pyautogui.write, password, interval=0.15)
                await asyncio.to_thread(write_func)
                if logger:
                    logger.info("✓ Пароль введен (write)")
            except:
                # Попытка 2: Буфер обмена
                if logger:
                    logger.info("Переход к методу буфера обмена...")
                await asyncio.to_thread(pyperclip.copy, password)
                await asyncio.sleep(0.2)

                is_mac = platform.system() == 'Darwin'
                paste_func = partial(pyautogui.hotkey, 'command' if is_mac else 'ctrl', 'v')
                await asyncio.to_thread(paste_func)
                if logger:
                    logger.info("✓ Пароль вставлен (paste)")

            await asyncio.sleep(0.8)

            # Enter
            press_func = partial(pyautogui.press, 'enter')
            await asyncio.to_thread(press_func)
            if logger:
                logger.info("✓ Enter нажат")

            return True

        except Exception as e:
            if logger:
                logger.error(f"✗ Ошибка: {e}")
            return False

    async def select_certificate(self) -> bool:
        try:
            if logger:
                logger.info("⚙ Выбор сертификата...")

            await asyncio.sleep(self.config.ncalayer_cert_delay)

            # Enter - выбор сертификата
            press_func = partial(pyautogui.press, 'enter')
            await asyncio.to_thread(press_func)
            if logger:
                logger.info("✓ Enter нажат (выбор сертификата)")

            await asyncio.sleep(0.5)

            # Tab - переход на кнопку "Подписать"
            tab_func = partial(pyautogui.press, 'tab')
            await asyncio.to_thread(tab_func)
            if logger:
                logger.info("✓ Tab нажат")

            await asyncio.sleep(0.5)

            # Enter - подписать
            await asyncio.to_thread(press_func)
            if logger:
                logger.info("✓ Enter нажат (подписать)")

            return True

        except Exception as e:
            if logger:
                logger.error(f"✗ Ошибка: {e}")
            return False

    async def automate_full_flow(self, password: str) -> bool:
        if logger:
            logger.info("🔄 Запуск автоматизации...")

        if not await self.enter_password(password):
            return False

        if not await self.select_certificate():
            return False

        if logger:
            logger.info("✓ Автоматизация завершена")

        return True


class ERAPBot:
    def __init__(self, config: ConfigDict):
        self.config = config
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.calibration = CoordinatesCalibration(config)
        self.automation: Optional[NCALayerAutomation] = None

    async def initialize(self) -> None:
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.config.headless,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        self.page = await context.new_page()
        self.page.set_default_timeout(self.config.timeout)

        if logger:
            logger.info("✓ Браузер инициализирован")

    async def authenticate(self) -> bool:
        try:
            await self.page.goto(self.config.base_url, wait_until='domcontentloaded')
            await self.page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)

            # Кнопка входа
            login_selectors = ['text=Войти в личный кабинет', 'text=Жеке кабинетке кіріңіз']
            for selector in login_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await asyncio.sleep(1.5)
                        break
                except:
                    continue

            # Кнопка сертификата
            cert_selectors = ['text=Выбрать сертификат', 'text=Сертификатты таңдау']
            for selector in cert_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await asyncio.sleep(1)
                        break
                except:
                    continue

            # Автоматизация
            automation_task = asyncio.create_task(
                self.automation.automate_full_flow(self.config.cert_password)
            )

            await asyncio.sleep(3)

            # Проверка авторизации
            for i in range(20):
                url = self.page.url

                if ('personal' in url.lower() or 'cabinet' in url.lower() or
                        ('login' not in url.lower() and url != self.config.base_url)):

                    if logger:
                        logger.info(f"✓ Авторизация успешна!")
                    automation_task.cancel()
                    return True

                if i % 5 == 0 and logger:
                    logger.info(f"Ожидание ({i + 1}/20)...")

                await asyncio.sleep(1)

            return False

        except Exception as e:
            if logger:
                logger.error(f"✗ Ошибка: {e}")
            return False

    async def run(self) -> bool:
        try:
            # Проверка калибровки
            needs_calibration = not self.calibration.load_coordinates()

            if needs_calibration:
                print("\n⚠️  Координаты не найдены. Запуск режима калибровки...")
                print("Сначала откроем браузер и дойдем до окна NCALayer...\n")

            # Инициализация браузера
            await self.initialize()

            # Открываем сайт и доходим до NCALayer
            await self.page.goto(self.config.base_url, wait_until='domcontentloaded')
            await self.page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)

            # Кнопка входа
            login_selectors = ['text=Войти в личный кабинет', 'text=Жеке кабинетке кіріңіз']
            for selector in login_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if await btn.is_visible(timeout=3000):
                        if logger:
                            logger.info(f"✓ Кнопка входа: {selector}")
                        await btn.click()
                        await asyncio.sleep(1.5)
                        break
                except:
                    continue

            # Кнопка сертификата
            cert_selectors = ['text=Выбрать сертификат', 'text=Сертификатты таңдау']
            for selector in cert_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if await btn.is_visible(timeout=3000):
                        if logger:
                            logger.info(f"✓ Кнопка сертификата: {selector}")
                        await btn.click()
                        await asyncio.sleep(1)
                        break
                except:
                    continue

            # Если нужна калибровка - запускаем
            if needs_calibration:
                await self.calibration.calibrate()
                print("\n🔄 Перезапустите программу для автоматической работы.")
                return False

            # Инициализация автоматизации с координатами
            self.automation = NCALayerAutomation(
                self.config,
                self.calibration.get_coordinates()
            )

            # Автоматизация
            automation_task = asyncio.create_task(
                self.automation.automate_full_flow(self.config.cert_password)
            )

            await asyncio.sleep(3)

            # Проверка авторизации
            for i in range(20):
                url = self.page.url

                if ('personal' in url.lower() or 'cabinet' in url.lower() or
                        'main' in url.lower() or
                        ('login' not in url.lower() and url != self.config.base_url)):

                    if logger:
                        logger.info(f"✓ Авторизация успешна! URL: {url}")
                        logger.info("✅ Браузер остается открытым. Нажмите Ctrl+C для выхода.")
                    automation_task.cancel()

                    # Ждем бесконечно, пока пользователь не закроет
                    try:
                        while True:
                            await asyncio.sleep(60)
                    except KeyboardInterrupt:
                        if logger:
                            logger.info("👋 Закрытие...")

                    return True

                if i % 5 == 0 and logger:
                    logger.info(f"Ожидание ({i + 1}/20)...")

                await asyncio.sleep(1)

            if logger:
                logger.error("✗ Авторизация не удалась")
            return False

        finally:
            # Закрываем браузер только при ошибке или неудачной калибровке
            if self.browser and not getattr(self, '_keep_browser_open', False):
                try:
                    await self.browser.close()
                except:
                    pass


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        cert_password = os.getenv("CERT_PASSWORD")
        if not cert_password:
            raise ValueError("CERT_PASSWORD не установлен в .env")

        config = ConfigDict(cert_password=cert_password)
    except Exception as e:
        print(f"Ошибка: {e}")
        return 1

    if logger:
        logger.info("=" * 70)
        logger.info("eRAP Bot с PyAutoGUI")
        logger.info("=" * 70)

    bot = ERAPBot(config)
    success = await bot.run()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)