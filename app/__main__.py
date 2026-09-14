import argparse
import logging
import signal

from waitress import create_server

from app.config import load_config
from app.controller import Controller
from app.instance import InstanceLock
from app.storage import Store
from app.web import create_app


def main():
    argparse.ArgumentParser(description="Start the Digital Azan controller and local web UI").parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = load_config()
    ownership = InstanceLock(cfg.data_dir / "controller.lock")
    ownership.acquire()
    controller = None
    server = None
    try:
        store = Store(cfg.database)
        store.import_legacy(cfg.data_dir / "scheduler_state.json", cfg.ramadan_override_enabled)
        controller = Controller(cfg, store=store)
        server = create_server(create_app(controller), host=cfg.host, port=cfg.port, threads=6,
                               max_request_body_size=8 * 1024 * 1024)
        controller.start()

        def shutdown(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        logging.info("Digital Azan listening on %s:%s", cfg.host, cfg.port)
        server.run()
    except KeyboardInterrupt:
        logging.info("Shutting down")
    finally:
        if controller:
            controller.close()
        if server:
            server.close()
        ownership.release()


if __name__ == "__main__":
    main()
