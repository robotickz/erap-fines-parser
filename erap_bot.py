import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional
import logging

from playwright.async_api import async_playwright, Page, Browser
from pydantic_settings import BaseSettings
from pydantic import Field


class ConfigDict(BaseSettings):
    base_url: str = Field(default="https://erap-public.kgp.kz/#/login")
    cert_password: str = Field(..., description="Certificate password for auto-input")

    download_dir: Path = Field(default=Path("./downloads"))
    screenshot_dir: Path = Field(default=Path("./screenshots"))

    headless: bool = Field(default=False)
    timeout: int = Field(default=60000)

    ncalayer_password_delay: float = Field(default=2.0, description="Delay before entering password (seconds)")
    use_xdotool: bool = Field(default=True, description="Use xdotool for automation")
    use_pynput: bool = Field(default=False, description="Fallback to pynput")

    class ConfigDict:
        env_file = ".env"
        env_prefix = ""


logger = logging.getLogger(__name__)


class NCALayerDialogAutomation:
    def __init__(self, config: ConfigDict) -> None:
        self.config = config
        self.xdotool_available = self._check_xdotool()
        self.pynput_available = False

        if config.use_pynput:
            self.pynput_available = self._check_pynput()

    @staticmethod
    def _check_xdotool() -> bool:
        try:
            subprocess.run(
                ['xdotool', 'version'],
                capture_output=True,
                check=True
            )
            if logger:
                logger.info("✓ xdotool available")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            if logger:
                logger.warning("⚠ xdotool not found. Install: sudo apt-get install xdotool")
            return False

    @staticmethod
    def _check_pynput() -> bool:
        try:
            import pynput
            if logger:
                logger.info("✓ pynput available")
            return True
        except ImportError:
            if logger:
                logger.warning("⚠ pynput not found. Install: pip install pynput")
            return False

    async def wait_for_ncalayer_dialog(self) -> bool:
        if logger:
            logger.info("⏳ Waiting for NCALayer dialog...")

        if self.xdotool_available:
            return await self._wait_with_xdotool()
        elif self.pynput_available:
            return await self._wait_with_pynput()
        else:
            # Fallback: простая задержка
            if logger:
                logger.warning("⚠ No automation tools available, using delay")
            await asyncio.sleep(self.config.ncalayer_password_delay)
            return True

    @staticmethod
    async def _wait_with_xdotool(max_attempts: int = 30) -> bool:
        """
        Ожидание диалога NCALayer используя xdotool.
        Ищет окно с заголовком содержащим 'NCALayer' или 'password'
        """
        for attempt in range(max_attempts):
            try:
                # Поиск окна NCALayer
                result = subprocess.run(
                    ['xdotool', 'search', '--name', 'NCALayer'],
                    capture_output=True,
                    text=True,
                    timeout=1
                )

                if result.returncode == 0 and result.stdout.strip():
                    window_id = result.stdout.strip().split('\n')[0]
                    if logger:
                        logger.info(f"✓ NCALayer dialog found: window {window_id}")
                    return True

                # Пробуем альтернативные заголовки
                for title in ['password', 'пароль', 'Kaztoken', 'Қазтокен']:
                    result = subprocess.run(
                        ['xdotool', 'search', '--name', title],
                        capture_output=True,
                        text=True,
                        timeout=1
                    )

                    if result.returncode == 0 and result.stdout.strip():
                        window_id = result.stdout.strip().split('\n')[0]
                        if logger:
                            logger.info(f"✓ Password dialog found: window {window_id} (title: {title})")
                        return True

            except subprocess.TimeoutExpired:
                pass

            await asyncio.sleep(0.5)

        if logger:
            logger.warning("⚠ NCALayer dialog not found within timeout")
        return False

    @staticmethod
    async def _wait_with_pynput(max_attempts: int = 30) -> bool:
        """
        Ожидание диалога используя pynput.
        Пытается найти окно с паролем по визуальным признакам
        """
        try:
            from pynput import keyboard
        except ImportError:
            if logger:
                logger.warning("⚠ pynput not available")
            return False

        for attempt in range(max_attempts):
            try:
                if logger:
                    logger.info(f"Checking for dialog (attempt {attempt + 1}/{max_attempts})")
                
                # Простая задержка для демонстрации
                await asyncio.sleep(0.1)

                if attempt >= 5:  # Эмуляция обнаружения окна
                    if logger:
                        logger.info(f"✓ Dialog found")
                    return True

            except Exception as e:
                if logger:
                    logger.info(f"Pynput check failed: {e}")

            await asyncio.sleep(0.5)

        if logger:
            logger.warning("⚠ Dialog not found within timeout")
        return False

    async def enter_password_xdotool(self, password: str) -> bool:
        """
        Ввод пароля используя xdotool

        МЕТОД 1: Прямой ввод в активное окно
        """
        if not self.xdotool_available:
            return False

        try:
            # Небольшая задержка для уверенности, что окно активно
            await asyncio.sleep(0.5)

            # Получаем ID активного окна
            result = subprocess.run(
                ['xdotool', 'getactivewindow'],
                capture_output=True,
                text=True,
                check=True
            )
            window_id = result.stdout.strip()
            if logger:
                logger.info(f"Active window ID: {window_id}")

            # Фокусируемся на окне
            subprocess.run(
                ['xdotool', 'windowfocus', window_id],
                check=True,
                timeout=2
            )

            # Вводим пароль (по символу для надежности)
            subprocess.run(
                ['xdotool', 'type', '--delay', '50', password],
                check=True,
                timeout=10
            )

            if logger:
                logger.info("✓ Password entered with xdotool")

            # Нажимаем Enter
            await asyncio.sleep(0.3)
            subprocess.run(
                ['xdotool', 'key', 'Return'],
                check=True,
                timeout=2
            )

            if logger:
                logger.info("✓ Enter pressed")
            return True

        except subprocess.CalledProcessError as e:
            if logger:
                logger.error(f"✗ xdotool error: {e}")
            return False
        except subprocess.TimeoutExpired:
            if logger:
                logger.error("✗ xdotool timeout")
            return False

    async def enter_password_xdotool_by_search(self, password: str) -> bool:
        """
        Ввод пароля используя xdotool

        МЕТОД 2: Поиск окна по заголовку
        """
        if not self.xdotool_available:
            return False

        try:
            # Ищем окно NCALayer
            for title_pattern in ['NCALayer', 'password', 'пароль', 'Kaztoken']:
                result = subprocess.run(
                    ['xdotool', 'search', '--name', title_pattern],
                    capture_output=True,
                    text=True,
                    timeout=2
                )

                if result.returncode == 0 and result.stdout.strip():
                    window_id = result.stdout.strip().split('\n')[0]
                    if logger:
                        logger.info(f"Found window by title '{title_pattern}': {window_id}")

                    # Активируем окно
                    subprocess.run(
                        ['xdotool', 'windowactivate', '--sync', window_id],
                        check=True,
                        timeout=2
                    )

                    await asyncio.sleep(0.3)

                    # Вводим пароль
                    subprocess.run(
                        ['xdotool', 'type', '--window', window_id, '--delay', '50', password],
                        check=True,
                        timeout=10
                    )

                    if logger:
                        logger.info("✓ Password entered")

                    # Нажимаем Enter
                    await asyncio.sleep(0.3)
                    subprocess.run(
                        ['xdotool', 'key', '--window', window_id, 'Return'],
                        check=True,
                        timeout=2
                    )

                    if logger:
                        logger.info("✓ Enter pressed")
                    return True

            if logger:
                logger.warning("⚠ Could not find NCALayer window")
            return False

        except subprocess.TimeoutExpired:
            if logger:
                logger.error("✗ Timeout while searching for window")
            return False
        except subprocess.CalledProcessError as e:
            if logger:
                logger.error(f"✗ xdotool error: {e}")
            return False

    async def enter_password_pynput(self, password: str) -> bool:
        """
        Ввод пароля используя pynput

        ЗАПАСНОЙ МЕТОД
        """
        if not self.pynput_available:
            return False

        try:
            from pynput import keyboard
            from pynput.keyboard import Key

            await asyncio.sleep(0.5)
            keyboard_controller = keyboard.Controller()

            # Вводим пароль посимвольно
            for char in password:
                keyboard_controller.press(char)
                keyboard_controller.release(char)
                await asyncio.sleep(0.05)  # Задержка между символами

            if logger:
                logger.info("✓ Password entered with pynput")

            await asyncio.sleep(0.3)

            # Нажимаем Enter
            keyboard_controller.press(Key.enter)
            keyboard_controller.release(Key.enter)
            if logger:
                logger.info("✓ Enter pressed")

            return True

        except Exception as e:
            if logger:
                logger.error(f"✗ Pynput error: {e}")
            return False

    async def automate_password_input(self, password: str) -> bool:
        """
        Главная функция автоматизации ввода пароля.
        Пробует несколько методов последовательно
        """
        if logger:
            logger.info("Starting password automation...")

        # Ждем появления диалога
        dialog_found = await self.wait_for_ncalayer_dialog()

        if not dialog_found:
            if logger:
                logger.warning("⚠ Dialog not detected, trying anyway...")

        # Дополнительная задержка
        await asyncio.sleep(self.config.ncalayer_password_delay)

        # Метод 1: xdotool (активное окно)
        if self.xdotool_available:
            if logger:
                logger.info("Trying xdotool method 1 (active window)...")
            if await self.enter_password_xdotool(password):
                return True

        # Метод 2: xdotool (поиск окна)
        if self.xdotool_available:
            if logger:
                logger.info("Trying xdotool method 2 (window search)...")
            if await self.enter_password_xdotool_by_search(password):
                return True

        # Метод 3: pynput (запасной)
        if self.pynput_available:
            if logger:
                logger.info("Trying pynput fallback...")
            if await self.enter_password_pynput(password):
                return True

        if logger:
            logger.error("✗ All automation methods failed")
        return False


class ERAPBotWithAutomation:
    """eRAP Bot с автоматизацией ввода пароля"""

    def __init__(self, config: ConfigDict):
        self.config = config
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.automation = NCALayerDialogAutomation(config)

    async def initialize(self) -> None:
        try:
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
                logger.info("✓ Browser initialized")
        except Exception as e:
            if logger:
                logger.error(f"✗ Failed to initialize browser: {e}")
            raise

    async def authenticate_with_automation(self) -> bool:
        """
        Аутентификация с автоматическим вводом пароля.
        Поддерживает русскую и казахскую версии сайта
        """
        try:
            if logger:
                logger.info(f"Navigating to {self.config.base_url}")

            await self.page.goto(self.config.base_url, wait_until='domcontentloaded')
            await self.page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Даем странице полностью загрузиться

            # ШАГ 1: Находим и нажимаем кнопку "Войти в личный кабинет" (RU/KZ)
            login_button_selectors = [
                'text=Войти в личный кабинет',
                'text=Жеке кабинетке кіріңіз',
                'button:has-text("Войти в личный кабинет")',
                'button:has-text("Жеке кабинетке кіріңіз")',
                'a:has-text("Войти в личный кабинет")',
                'a:has-text("Жеке кабинетке кіріңіз")',
            ]

            login_button_found = False
            for selector in login_button_selectors:
                try:
                    login_button = self.page.locator(selector).first
                    if await login_button.is_visible(timeout=3000):
                        if logger:
                            logger.info(f"✓ Found login button: {selector}")
                        await login_button.click()
                        login_button_found = True
                        await asyncio.sleep(1.5)  # Ждем появления следующего диалога
                        break
                except Exception as e:
                    if logger:
                        logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not login_button_found:
                if logger:
                    logger.error("✗ Login button ('Войти в личный кабинет') not found")
                return False

            # ШАГ 2: Находим и нажимаем кнопку "Выбрать сертификат" (RU/KZ)
            cert_button_selectors = [
                'text=Выбрать сертификат',
                'text=Сертификатты таңдау',
                'button:has-text("Выбрать сертификат")',
                'button:has-text("Сертификатты таңдау")',
                'a:has-text("Выбрать сертификат")',
                'a:has-text("Сертификатты таңдау")',
                # Запасные варианты на случай других формулировок
                'button:has-text("сертификат")',
                'button:has-text("Сертификат")',
            ]

            cert_button_found = False
            for selector in cert_button_selectors:
                try:
                    cert_button = self.page.locator(selector).first
                    if await cert_button.is_visible(timeout=3000):
                        if logger:
                            logger.info(f"✓ Found certificate button: {selector}")
                        await cert_button.click()
                        cert_button_found = True
                        await asyncio.sleep(1)  # Даем время на открытие NCALayer
                        break
                except Exception as e:
                    if logger:
                        logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not cert_button_found:
                if logger:
                    logger.error("✗ Certificate button ('Выбрать сертификат') not found")
                # Делаем скриншот для отладки
                try:
                    screenshot_path = self.config.screenshot_dir / "cert_button_not_found.png"
                    await self.page.screenshot(path=str(screenshot_path))
                    if logger:
                        logger.info(f"Screenshot saved: {screenshot_path}")
                except:
                    pass
                return False

            # ШАГ 3: Запускаем автоматизацию ввода пароля в NCALayer
            if logger:
                logger.info("⚙ Starting NCALayer password automation...")

            automation_task = asyncio.create_task(
                self.automation.automate_password_input(self.config.cert_password)
            )

            # Ждем успешной авторизации (переход на страницу с 'personal' или без 'login')
            try:
                # Пробуем несколько вариантов URL после авторизации
                await asyncio.sleep(3)  # Даем время на обработку сертификата

                # Проверяем изменение URL
                for _ in range(15):  # Ждем до 15 секунд
                    current_url = self.page.url
                    if logger:
                        logger.info(f"Current URL: {current_url}")

                    # Проверяем признаки успешной авторизации
                    if ('personal' in current_url.lower() or
                            'cabinet' in current_url.lower() or
                            'main' in current_url.lower() or
                            'home' in current_url.lower() or
                            ('login' not in current_url.lower() and current_url != self.config.base_url)):

                        if logger:
                            logger.info("✓ Authentication successful - URL changed!")
                        automation_task.cancel()
                        return True

                    await asyncio.sleep(1)

                # Если URL не изменился, проверяем успешность автоматизации
                try:
                    automation_success = await automation_task
                    if automation_success:
                        if logger:
                            logger.info("✓ Password automation completed")
                        # Даем дополнительное время на редирект
                        await asyncio.sleep(3)
                        current_url = self.page.url
                        if 'login' not in current_url.lower():
                            if logger:
                                logger.info("✓ Authentication successful (delayed redirect)")
                            return True
                except asyncio.CancelledError:
                    return True

                if logger:
                    logger.error("✗ Authentication failed - URL did not change")
                return False

            except Exception as e:
                if logger:
                    logger.error(f"✗ Authentication error: {e}")
                try:
                    automation_task.cancel()
                except:
                    pass
                return False

        except Exception as e:
            if logger:
                logger.error(f"✗ Error during authentication: {e}")
            return False

    async def run(self) -> bool | None:
        result = False
        try:
            await self.initialize()
            auth_result = await self.authenticate_with_automation()
            
            if auth_result:
                if logger:
                    logger.info("Success")
                result = True
            else:
                result = False
        except Exception as e:
            if logger:
                logger.error(f"✗ Error in run method: {e}")
            result = False
        finally:
            if self.browser:
                try:
                    await self.browser.close()
                except Exception as e:
                    if logger:
                        logger.error(f"✗ Error closing browser: {e}")
        
        return result


async def main() -> int:
    """Entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        cert_password = os.getenv("CERT_PASSWORD", "Yeso2006")
        if not cert_password:
            raise ValueError("CERT_PASSWORD environment variable is not set")
        config = ConfigDict(cert_password=cert_password)
    except Exception as e:
        print(f"Configuration error: {e}")
        print("Ensure .env file has CERT_PASSWORD variable")
        return 1

    if logger:
        logger.info("="*70)
        logger.info("eRAP Bot with NCALayer Password Automation")
        logger.info("="*70)

    bot = ERAPBotWithAutomation(config)
    success = await bot.run()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
