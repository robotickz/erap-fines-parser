import asyncio
import os
import logging
from pathlib import Path
from typing import Optional

from anthropic import Anthropic
from playwright.async_api import async_playwright, Page, Browser
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()


class ConfigDict(BaseSettings):
    base_url: str = Field(default="https://erap-public.kgp.kz/#/login")
    cert_password: str = Field(..., description="Certificate password for auto-input")
    cert_path: str = Field(..., description="Path to certificate file")

    download_dir: Path = Field(default=Path("./downloads"))
    screenshot_dir: Path = Field(default=Path("./screenshots"))

    headless: bool = Field(default=False)
    timeout: int = Field(default=60000)

    ncalayer_password_delay: float = Field(default=3.0, description="Delay before entering password (seconds)")
    ncalayer_cert_select_delay: float = Field(default=2.0, description="Delay before certificate selection")

    class ConfigDict:
        env_file = ".env"
        env_prefix = ""


logger = logging.getLogger(__name__)


class ClaudeComputerUseAutomation:
    """Автоматизация ввода пароля в NCALayer используя Claude Computer Use API"""

    def __init__(self, config: ConfigDict) -> None:
        self.config = config
        self.client = Anthropic(api_key=os.environ["CLAUDE_KEY"])
        self.model = "claude-sonnet-4-5"

    async def enter_password_and_select_cert(self) -> bool:
        """
        Использует Claude Computer Use для:
        1. Ввода пароля в NCALayer
        2. Выбора сертификата
        3. Нажатия "Қол қою"
        """
        try:
            if logger:
                logger.info("⚙ Запуск автоматизации через Claude Computer Use...")

            # Ждем появления диалога NCALayer
            await asyncio.sleep(self.config.ncalayer_password_delay)

            # Шаг 1: Ввод пароля
            prompt_password = f"""На экране открыт диалог NCALayer для выбора сертификата и ввода пароля.
            Пожалуйста, выполните следующие действия:
            1. Найдите поле ввода пароля в окне NCALayer
            2. Нажмите на это поле
            3. Введите следующий пароль: {self.config.cert_password}
            4. Выберите сертификат, его путь: {self.config.cert_path}, но только если поле пустое. Если там что-то заполнено, пропускай этот шаг.
            4. Нажмите кнопку OK или нажмите Enter для подтверждения
            
            Убедитесь, что все действия выполнены корректно."""

            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=1024,
                extra_headers={
                    "anthropic-beta": "computer-use-2025-01-24"
                },
                tools=[
                    {
                        "type": "computer_20250124",
                        "name": "computer",
                        "display_width_px": 1920,
                        "display_height_px": 1080
                    },
                    {
                        "type": "bash_20250124",
                        "name": "bash"
                    },
                    {
                        "type": "text_editor_20250728",
                        "name": "str_replace_based_edit_tool"
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": prompt_password
                    }
                ]
            )

            if logger:
                logger.info("✓ Пароль введен через Claude Computer Use")

            await asyncio.sleep(1)

            # Шаг 2: Ожидание диалога выбора сертификата и нажатие Enter
            await asyncio.sleep(self.config.ncalayer_cert_select_delay)

            prompt_cert = f"""Теперь появилось второе окно NCALayer с заголовком "Кілтті таңдаңыз" (Выбор ключа).
            В этом окне показан сертификат:
            Иесі: ФИО
            Жарамдылық мерзімі: некий срок
            
            Пожалуйста, выполните следующие действия:
            1. Нажмите enter, поле станет темнее.
            2. Затем нажмите tab и через секунду enter. Это автоматически активирует кнопку Подписать.
            
            Выполните эти действия последовательно."""

            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=1024,
                extra_headers={
                    "anthropic-beta": "computer-use-2025-01-24"
                },
                tools=[
                    {
                        "type": "computer_20250124",
                        "name": "computer",
                        "display_width_px": 1920,
                        "display_height_px": 1080
                    },
                    {
                        "type": "bash_20250124",
                        "name": "bash"
                    },
                    {
                        "type": "text_editor_20250728",
                        "name": "str_replace_based_edit_tool"
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": prompt_cert
                    }
                ]
            )

            if logger:
                logger.info("✓ Сертификат выбран и действия выполнены")

            return True

        except Exception as e:
            if logger:
                logger.error(f"✗ Ошибка Claude Computer Use: {e}")
            return False


class ERAPBotWithClaudeAutomation:
    """eRAP Bot с автоматизацией через Claude Computer Use"""

    def __init__(self, config: ConfigDict):
        self.config = config
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.automation = ClaudeComputerUseAutomation(config)

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
                logger.info("✓ Браузер инициализирован")
        except Exception as e:
            if logger:
                logger.error(f"✗ Ошибка инициализации браузера: {e}")
            raise

    async def authenticate_with_automation(self) -> bool:
        """
        Аутентификация с автоматическим вводом пароля через Claude.
        Поддерживает русскую и казахскую версии сайта
        """
        try:
            if logger:
                logger.info(f"Переход на {self.config.base_url}")

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
                            logger.info(f"✓ Найдена кнопка входа: {selector}")
                        await login_button.click()
                        login_button_found = True
                        await asyncio.sleep(1.5)
                        break
                except Exception as e:
                    if logger:
                        logger.debug(f"Селектор {selector} не найден: {e}")
                    continue

            if not login_button_found:
                if logger:
                    logger.error("✗ Кнопка входа не найдена")
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
                            logger.info(f"✓ Найдена кнопка сертификата: {selector}")
                        await cert_button.click()
                        cert_button_found = True
                        await asyncio.sleep(1)
                        break
                except Exception as e:
                    if logger:
                        logger.debug(f"Селектор {selector} не найден: {e}")
                    continue

            if not cert_button_found:
                if logger:
                    logger.error("✗ Кнопка сертификата не найдена")
                try:
                    screenshot_path = self.config.screenshot_dir / "cert_button_not_found.png"
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    await self.page.screenshot(path=str(screenshot_path))
                    if logger:
                        logger.info(f"Скриншот сохранен: {screenshot_path}")
                except:
                    pass
                return False

            # ШАГ 3: Запустить автоматизацию ввода пароля и выбора сертификата через Claude
            if logger:
                logger.info("⚙ Запуск автоматизации Claude Computer Use...")

            automation_task = asyncio.create_task(
                self.automation.enter_password_and_select_cert()
            )

            # Ждем успешной аутентификации
            try:
                await asyncio.sleep(3)

                # Проверяем изменение URL
                for i in range(20):
                    current_url = self.page.url
                    if logger:
                        logger.info(f"Текущий URL ({i+1}/20): {current_url}")

                    if ('personal' in current_url.lower() or
                            'cabinet' in current_url.lower() or
                            'main' in current_url.lower() or
                            'home' in current_url.lower() or
                            ('login' not in current_url.lower() and current_url != self.config.base_url)):

                        if logger:
                            logger.info("✓ Аутентификация успешна - URL изменился!")
                        automation_task.cancel()
                        return True

                    await asyncio.sleep(1)

                # Проверяем успешность автоматизации
                try:
                    automation_success = await automation_task
                    if automation_success:
                        if logger:
                            logger.info("✓ Автоматизация Claude завершена")
                        await asyncio.sleep(3)
                        current_url = self.page.url
                        if 'login' not in current_url.lower():
                            if logger:
                                logger.info("✓ Аутентификация успешна (отложенный редирект)")
                            return True
                except asyncio.CancelledError:
                    return True

                if logger:
                    logger.error("✗ Аутентификация не удалась - URL не изменился")
                return False

            except Exception as e:
                if logger:
                    logger.error(f"✗ Ошибка аутентификации: {e}")
                try:
                    automation_task.cancel()
                except:
                    pass
                return False

        except Exception as e:
            if logger:
                logger.error(f"✗ Ошибка во время аутентификации: {e}")
            return False

    async def run(self) -> bool | None:
        result = False
        try:
            await self.initialize()
            auth_result = await self.authenticate_with_automation()

            if auth_result:
                if logger:
                    logger.info("✓ Успешно завершено")
                result = True
            else:
                result = False
        except Exception as e:
            if logger:
                logger.error(f"✗ Ошибка в методе run: {e}")
            result = False
        finally:
            if self.browser:
                try:
                    await self.browser.close()
                except Exception as e:
                    if logger:
                        logger.error(f"✗ Ошибка при закрытии браузера: {e}")

        return result


async def main() -> int:
    """Точка входа"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        cert_password = os.getenv("CERT_PASSWORD")
        cert_path = os.getenv("CERT_PATH")

        if not cert_password:
            raise ValueError("CERT_PASSWORD переменная окружения не установлена")
        if not cert_path:
            raise ValueError("CERT_PATH переменная окружения не установлена")

        config = ConfigDict(cert_password=cert_password, cert_path=cert_path)
    except Exception as e:
        print(f"Ошибка конфигурации: {e}")
        print("Убедитесь, что файл .env содержит переменные CERT_PASSWORD и CERT_PATH")
        return 1

    if logger:
        logger.info("=" * 70)
        logger.info("eRAP Bot с Claude Computer Use API")
        logger.info("=" * 70)

    bot = ERAPBotWithClaudeAutomation(config)
    success = await bot.run()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)