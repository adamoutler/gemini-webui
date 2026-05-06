import logging
import time
import eventlet

from src.config import get_config, env_config
from src.services.process_engine import fetch_sessions_for_host

logger = logging.getLogger(__name__)


class SessionPollerManager:
    """
    Singleton manager for backend-driven session polling.
    It spawns an eventlet greenlet per host that continuously polls
    for sessions using a smart backoff strategy.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SessionPollerManager, cls).__new__(cls)
            cls._instance.last_frontend_request_time = time.time()
            cls._instance.greenlets = {}
            cls._instance.is_running = False
        return cls._instance

    def start(self):
        """Starts the polling greenlets if they are not already running."""
        if self.is_running:
            return

        self.is_running = True
        self.update_hosts()
        logger.info("SessionPollerManager started.")

    def stop(self):
        """Stops all running polling greenlets."""
        self.is_running = False
        for host_label, g in self.greenlets.items():
            g.kill()
        self.greenlets.clear()
        logger.info("SessionPollerManager stopped.")

    def update_hosts(self):
        """Reads current hosts from config and updates running greenlets."""
        if not self.is_running:
            return

        conf = get_config()
        hosts = conf.get("HOSTS", [])

        # Ensure local host is always polled even if empty
        if not hosts:
            hosts = [{"label": "local", "target": "local"}]

        current_host_labels = {host.get("label", "local") for host in hosts}

        # Start greenlets for new hosts
        for host in hosts:
            label = host.get("label", "local")
            if label not in self.greenlets:
                logger.info("Starting poller greenlet for host")
                self.greenlets[label] = eventlet.spawn(self._poll_host, host)

        # Stop greenlets for removed hosts
        labels_to_remove = []
        for label, g in self.greenlets.items():
            if label not in current_host_labels:
                logger.info("Stopping poller greenlet for removed host")
                g.kill()
                labels_to_remove.append(label)

        for label in labels_to_remove:
            del self.greenlets[label]

    def update_frontend_activity(self):
        """Updates the timestamp of the last frontend request."""
        self.last_frontend_request_time = time.time()
        # Periodically evaluate config changes when activity happens
        self.update_hosts()

    def _poll_host(self, host):
        """
        Background loop for polling a single host.
        Uses a smart backoff:
        - 5s sleep if frontend requested within last 2 minutes.
        - 120s sleep otherwise.
        """
        label = host.get("label", "local")
        from src.config import get_config_paths

        _, _, ssh_dir_path = get_config_paths()
        gemini_bin = getattr(env_config, "GEMINI_BIN", "gemini")

        while self.is_running:
            try:
                # Calculate sleep interval based on frontend activity
                time_since_last_request = time.time() - self.last_frontend_request_time
                if time_since_last_request <= 120:
                    sleep_interval = 5
                else:
                    sleep_interval = 120

                # Fetch sessions (Internally populates src.shared_state.session_results_cache)
                fetch_sessions_for_host(host, ssh_dir_path, gemini_bin)

            except Exception as e:
                logger.error(f"Error polling sessions for host {label}: {e}")

            eventlet.sleep(sleep_interval)


# Singleton Instance
session_poller_manager = SessionPollerManager()
