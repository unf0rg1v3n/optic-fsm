"""
Точка входа в приложение OpticFSM.
Настраивает корневой логгер и инициализирует работу движка.
"""
import logging
import sys

from configuration import load_config
from core import OpticFSMEngine

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - [%(name)s] - %(message)s'
)
logger = logging.getLogger("OpticFSM.Main")


def main() -> None:
    """Главная функция приложения."""
    try:
        fsm_config = load_config("config.json")

        engine = OpticFSMEngine(fsm_config)
        engine.run()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Глобальный сбой выполнения: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
