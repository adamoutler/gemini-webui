import threading

ephemeral_sessions = {}
ephemeral_sessions_lock = threading.Lock()

abandoned_pids = set()
abandoned_pids_lock = threading.Lock()

session_results_cache = {}
session_results_cache_lock = threading.Lock()

active_fake_sockets = {}
active_fake_sockets_lock = threading.Lock()

active_monitors = {}
active_monitors_lock = threading.Lock()
