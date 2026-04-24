from news_observability.logging import get_logger, setup_logging


def test_get_logger_returns_bound_logger():
    log = get_logger("t")
    log.info("hello")  # no raise


def test_setup_logging_json_mode_runs():
    setup_logging(level="DEBUG", json_mode=True)
    setup_logging(level="INFO", json_mode=False)  # revert
