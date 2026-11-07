"""Application entry point and health/readiness/version endpoints."""
import logging
from flask import jsonify

from app.config import HOST, PORT, DEBUG, APP_VERSION, GIT_SHA
from app.ui.dashboard import app as dash_app
from app.services.market_data_service import market_data_service
from app.observability.logging_config import configure_logging

logger = logging.getLogger(__name__)


def register_operational_endpoints(server):
    @server.get("/health")
    def health():
        return jsonify({"status": "healthy"}), 200

    @server.get("/ready")
    def ready():
        is_ready, detail = market_data_service.check_ready()
        payload = {
            "status": "ready" if is_ready else "not_ready",
            "data_mode": market_data_service.mode,
            "data_source": market_data_service.last_source,
            "detail": detail,
        }
        return jsonify(payload), (200 if is_ready else 503)

    @server.get("/version")
    def version():
        return jsonify({"version": APP_VERSION, "commit": GIT_SHA}), 200


register_operational_endpoints(dash_app.server)


def main():
    configure_logging()
    if DEBUG:
        logging.getLogger().setLevel(logging.DEBUG)
    logger.info("Starting %s version=%s", dash_app.title, APP_VERSION)
    dash_app.run(host=HOST, port=PORT, debug=DEBUG)


if __name__ == "__main__":
    main()
