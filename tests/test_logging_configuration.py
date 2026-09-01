import io
import logging
import time

import agent_col_turn_service
import main


def test_configure_agent_col_logging_writes_diagnostics_once_without_dependency_noise():
    stream = io.StringIO()
    loggers = (
        logging.getLogger("main"),
        logging.getLogger("agent_col_turn_service"),
    )
    original_state = {
        logger.name: (list(logger.handlers), logger.level, logger.propagate)
        for logger in loggers
    }
    try:
        main.configure_agent_col_logging(stream=stream)
        main.configure_agent_col_logging(stream=stream)

        main._log_chat_pipeline(
            "turn_service_finish",
            route="chat_json",
            started_at=time.monotonic(),
            stream_started=True,
        )
        agent_col_turn_service._log_turn_pipeline(
            "routing_finish",
            started_at=0.0,
            clock=lambda: 0.25,
            route=agent_col_turn_service.AgentColRouteV4.ARTIFACT,
        )
        logging.getLogger("google.cloud.firestore").info(
            "private dependency noise marker"
        )

        output = stream.getvalue()
        assert output.count("Agent_Col chat pipeline") == 1
        assert output.count("Agent_Col turn pipeline") == 1
        assert "INFO:main:Agent_Col chat pipeline" in output
        assert "stage=turn_service_finish" in output
        assert "route=chat_json" in output
        assert (
            "INFO:agent_col_turn_service:Agent_Col turn pipeline"
            in output
        )
        assert "stage=routing_finish" in output
        assert "route=artifact" in output
        assert "private dependency noise marker" not in output
    finally:
        for logger in loggers:
            original_handlers, original_level, original_propagate = (
                original_state[logger.name]
            )
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                if handler not in original_handlers:
                    handler.close()
            for handler in original_handlers:
                logger.addHandler(handler)
            logger.setLevel(original_level)
            logger.propagate = original_propagate
