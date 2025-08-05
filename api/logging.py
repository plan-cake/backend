import logging

from colorama import Fore, Style


class FancyFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.WHITE,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.MAGENTA,
    }
    BOLD_LEVELS = {"ERROR", "CRITICAL"}

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, Style.RESET_ALL)
        bold = Style.BRIGHT if record.levelname in self.BOLD_LEVELS else ""
        message = super().format(record)
        return f"{bold}{log_color}{message}{Style.RESET_ALL}"
