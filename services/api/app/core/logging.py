import logging
import re
from logging.config import dictConfig

ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')


class CustomAnsiFilter(logging.Filter):
    def filter(self, record):
        cleaned_message = ansi_escape.sub('', record.getMessage())

        def get_message_override():
            return cleaned_message

        record.getMessage = get_message_override

        return True


BASE_LOGGERS_LOGGING_CONFIG = {
    'level': logging.INFO,
    'propagate': False,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'ansi_filter': {
            '()': CustomAnsiFilter,
        },
    },
    'formatters': {
        'detailed': {
            'format': '{[%(asctime)s] [%(levelname)s] [%(name)s] - '
                      '[%(module)s] - [%(funcName)s] - line: [%(lineno)d] - [%(message)s]}'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'detailed',
            'stream': 'ext://sys.stdout',
        }
    },
    'loggers': {
        'root': {
            **BASE_LOGGERS_LOGGING_CONFIG,
            'handlers': ['console']
        },
        "gunicorn.access": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False
        },
        "gunicorn.error": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False
        },
        "uvicorn.error": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False
        },
    },
}


def setup_logging():
    dictConfig(LOGGING)
