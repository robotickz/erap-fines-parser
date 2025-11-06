import asyncio
import os
import logging
from pathlib import Path
from typing import Optional
from functools import partial

import pyautogui
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

    ncalayer_password_delay: float = Field(default=3.0, description="Delay before entering password (seconds)")
    typing_interval: float = Field(default=0.1, description="Interval between keystrokes (seconds)")
    click_before_type: bool = Field(default=True, description="Click window before typing (for macOS)")
    use_typewrite_method: bool = Field(default=True, description="Use typewrite instead of write")

    class ConfigDict:
        env_file = ".env"
        env_prefix = ""


logger = logging.getLogger(__name__)


class NCALayerDialogAutomation:
    """Автоматизация ввода пароля в NCALayer используя PyAutoGUI"""

    def __init__(self, config: ConfigDict) -> None:
        self.config = config
        self._check_pyautogui()

    @staticmethod
    def _check_pyautogui() -> bool:
        """Проверка доступности PyAutoGUI и разрешений"""
        try:
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.1

            # Тест работоспособности
            pos = pyautogui.position()

            if logger:
                logger.info(f"✓ PyAutoGUI available (mouse at {pos})")

            import platform
            if platform.system() == 'Darwin':
                logger.warning("⚠ macOS: Ensure Python has Accessibility permissions!")
                logger.warning("   Settings → Privacy & Security → Accessibility")

            return True
        except Exception as e:
            if logger:
                logger.error(f"✗ PyAutoGUI error: {e}")
            return False

    async def enter_password(self, password: str) -> bool:
        """
        Ввод пароля используя PyAutoGUI
        Оптимизировано для macOS
        """
        try:
            if logger:
                logger.info("⚙ Starting password input with PyAutoGUI...")

            # Задержка для появления диалога
            await asyncio.sleep(self.config.ncalayer_password_delay)

            # Клик в центр экрана для активации окна (для macOS)
            if self.config.click_before_type:
                screen_width, screen_height = pyautogui.size()
                center_x, center_y = screen_width // 2, screen_height // 2

                click_func = partial(pyautogui.click, center_x, center_y)
                await asyncio.to_thread(click_func)

                if logger:
                    logger.info(f"✓ Clicked at center ({center_x}, {center_y})")

                await asyncio.sleep(0.5)

            # Ввод пароля
            if self.config.use_typewrite_method:
                # Метод 1: typewrite (лучше для macOS)
                for char in password:
                    write_func = partial(pyautogui.typewrite, char, interval=self.config.typing_interval)
                    await asyncio.to_thread(write_func)
                if logger:
                    logger.info("✓ Password entered (typewrite)")
            else:
                # Метод 2: write
                write_func = partial(pyautogui.write, password, interval=self.config.typing_interval)
                await asyncio.to_thread(write_func)
                if logger:
                    logger.info("✓ Password entered (write)")

            # Задержка перед Enter
            await asyncio.sleep(0.5)

            # Нажатие Enter
            press_func = partial(pyautogui.press, 'enter')
            await asyncio.to_thread(press_func)

            if logger:
                logger.info("✓ Enter pressed (password dialog)")

            return True

        except Exception as e:
            if logger:
                logger.error(f"✗ PyAutoGUI error: {e}")
            return False

    @staticmethod
    async def select_certificate_and_sign() -> bool:
        """
        Выбор сертификата и нажатие кнопки "Қол қою" во втором окне NCALayer
        """
        try:
            if logger:
                logger.info("⚙ Waiting for certificate selection dialog...")

            # Ждем появления второго окна
            await asyncio.sleep(2.0)

            # Клик в центр экрана для выбора первого сертификата
            screen_width, screen_height = pyautogui.size()
            center_x, center_y = screen_width // 2, screen_height // 2

            click_func = partial(pyautogui.click, center_x, center_y)
            await asyncio.to_thread(click_func)

            if logger:
                logger.info(f"✓ Clicked on certificate at ({center_x}, {center_y})")

            await asyncio.sleep(0.5)

            # Нажатие Enter или Tab+Enter для кнопки "Қол қою"
            press_func = partial(pyautogui.press, 'enter')
            await asyncio.to_thread(press_func)

            if logger:
                logger.info("✓ Sign button pressed")

            return True

        except Exception as e:
            if logger:
                logger.error(f"✗ Certificate selection error: {e}")
            return False

    async def automate_password_input(self, password: str) -> bool:
        """
        Полная автоматизация: ввод пароля + выбор сертификата
        """
        if logger:
            logger.info("Starting full NCALayer automation (password + certificate)...")

        # Шаг 1: Ввод пароля в первом окне
        if not await self.enter_password(password):
            return False

        # Шаг 2: Выбор сертификата и нажатие "Қол қою" во втором окне
        if not await self.select_certificate_and_sign():
            return False

        if logger:
            logger.info("✓ Full automation completed")

        return True


class ERAPBotWithAutomation:
    """eRAP Bot с автоматизацией ввода пароля через PyAutoGUI"""

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
            await asyncio.sleep(2)

            # ШАГ 1: Нажать кнопку "Войти в личный кабинет"
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
                        await asyncio.sleep(1.5)
                        break
                except Exception as e:
                    if logger:
                        logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not login_button_found:
                if logger:
                    logger.error("✗ Login button not found")
                return False

            # ШАГ 2: Нажать кнопку "Выбрать сертификат"
            cert_button_selectors = [
                'text=Выбрать сертификат',
                'text=Сертификатты таңдау',
                'button:has-text("Выбрать сертификат")',
                'button:has-text("Сертификатты таңдау")',
                'a:has-text("Выбрать сертификат")',
                'a:has-text("Сертификатты таңдау")',
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
                        await asyncio.sleep(1)
                        break
                except Exception as e:
                    if logger:
                        logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not cert_button_found:
                if logger:
                    logger.error("✗ Certificate button not found")
                try:
                    screenshot_path = self.config.screenshot_dir / "cert_button_not_found.png"
                    await self.page.screenshot(path=str(screenshot_path))
                    if logger:
                        logger.info(f"Screenshot saved: {screenshot_path}")
                except:
                    pass
                return False

            # ШАГ 3: Запустить автоматизацию ввода пароля в NCALayer
            if logger:
                logger.info("⚙ Starting NCALayer password automation...")

            automation_task = asyncio.create_task(
                self.automation.automate_password_input(self.config.cert_password)
            )

            # Ждем успешной авторизации
            try:
                await asyncio.sleep(3)

                # Проверяем изменение URL
                for _ in range(15):
                    current_url = self.page.url
                    if logger:
                        logger.info(f"Current URL: {current_url}")

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

                # Проверяем успешность автоматизации
                try:
                    automation_success = await automation_task
                    if automation_success:
                        if logger:
                            logger.info("✓ Password automation completed")
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
        logger.info("=" * 70)
        logger.info("eRAP Bot with PyAutoGUI Password Automation")
        logger.info("=" * 70)

    bot = ERAPBotWithAutomation(config)
    success = await bot.run()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)