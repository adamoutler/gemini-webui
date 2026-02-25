# Gemini WebUI

**The ultimate "Couch-Friendly" terminal for your Gemini AI.**

Gemini WebUI provides a high-fidelity, persistent web interface for the Gemini CLI. It allows you to monitor your projects, run long-running AI tasks, and interact with your host machine from any device with a browser—whether you're at your desk or relaxing on the couch with a tablet.

## 🚀 Key Features

### 🖥️ Persistence & Multi-Tab
*   **Always-On Background Sessions**: Backend processes continue running even if you close your browser or navigate away.
*   **One Session, Many Views**: Real-time mirroring across multiple devices or tabs—input and output stay perfectly in sync.
*   **Session Context Tracking**: The "Restart" button and page refresh intelligently maintain your session state (Fresh vs. Resume).
*   **Dynamic Tab Titles**: Terminal escape sequences automatically update tab names in real-time.
*   **Back Button Hijacking**: Navigate "back" from a terminal to instantly open the connection launcher in a new tab.
*   **PTY Lifecycle Management**: Automatic cleanup of orphaned PTY processes after 60 seconds of disconnection.

### 🔌 Advanced Connectivity
*   **Host Management**: Add, Edit, Delete, and Reorder connection cards with an optimistic, animated drag-and-drop interface.
*   **Quick Connect Bar**: Instantly connect via SSH using `user@host[:port] [directory]` syntax with automatic persistence.
*   **Remote Session Management**: List and Terminate active Gemini sessions on remote hosts directly from the launcher.
*   **Tilde-Aware Pathing**: Intelligent handling of `~/` directory paths for both local and remote SSH sessions.
*   **Login Shell Parity**: Remote commands are executed via `bash -l -c` to ensure your full remote environment (`.profile`, `.bashrc`) is loaded.

### 🔑 Robust SSH Key Management
*   **Instance Key Generation**: Automatic generation of a unique Ed25519 key pair on first run.
*   **Manual Key Management**: Add and Delete your own private keys for specific hosts.
*   **One-Click Authorization**: Dedicated "Copy Snippet" button provides a one-liner to authorize the instance on any remote host.
*   **Secure Rotation**: Rotate the instance-wide SSH key with a single click and safety confirmation.

### 🎨 High-Fidelity Experience
*   **Full Color Support**: Forced 256-color and Truecolor (`FORCE_COLOR=3`) ensure progress bars and graphics look perfect.
*   **Interactive Links**: Intelligent multi-line link detection allows you to click URLs that wrap across terminal lines.
*   **Modern Aesthetics**: Custom dark-themed scrollbars and ephemeral "Success" feedback (✓) on action buttons.

### 📱 Mobile Optimized
*   **Visual Viewport Integration**: Dynamically adjusts layout and terminal fit when the on-screen keyboard is toggled.
*   **Android Keyboard Workaround**: Implements a "Single Character Buffer" to prevent mobile OS autocorrect from interfering with terminal input.
*   **ANSI Navigation Overlay**: Dedicated mobile control bar for sending raw arrow keys and Ctrl sequences to the PTY.

### 🔒 Security & Operations
*   **Exclusive Authentication**: Uses LDAP/AD as the sole method if configured; otherwise, falls back to a secure local admin account.
*   **Hardened Docker Architecture**: Runs with a **Read-Only Root Filesystem** and `tmpfs` for maximum security.
*   **Storage Resilience**: Automatic failover to `/tmp` if persistent storage is unavailable, with clear on-screen guidance.
*   **Automatic Permissions**: Startup logic detects and corrects root-owned volume mounts to the `node` user.
*   **Proxy-Ready**: Built-in support for `X-Forwarded-For` and `X-Forwarded-Proto` headers via `ProxyFix`.

---

## 🏗 Architecture

```mermaid
graph TD
    User([User Browser]) -- WebSockets --> App[Docker Container: Flask App]
    App --> Local[Local Gemini CLI]
    App -- SSH --> Remote[Remote Host]
    Remote --> RemoteGemini[Remote Gemini CLI]
```

## 🛠 Configuration

### Authentication Modes
1.  **LDAP (Enterprise)**: If `LDAP_SERVER` is configured, it is the **only** permitted method.
2.  **Local Admin (Stand-alone)**: If LDAP is **not** configured, the app uses `ADMIN_USER` and `ADMIN_PASS` (both default to `admin`).

### Environment Variables
| Variable | Description | Default |
| :--- | :--- | :--- |
| `LDAP_SERVER` | Address of the LDAP/AD server | - |
| `LDAP_BASE_DN` | Base DN for user searches | - |
| `LDAP_BIND_USER_DN` | Service account for LDAP lookups | - |
| `LDAP_BIND_PASS` | Password for the service account | - |
| `ADMIN_USER` | Local admin username | `admin` |
| `ADMIN_PASS` | Local admin password | `admin` |
| `ALLOWED_ORIGINS` | CORS whitelist (comma-separated) | `*` |
| `GEMINI_BIN` | Path to the Gemini executable | `/usr/local/bin/gemini` |

### Volumes
*   `data:/data`: Persists app config, SSH keys, and CLI state (linked to `/home/node/.gemini`).

---

## 🏗 Quick Start

Build and launch the container with a single command:

```bash
docker compose up --build --force-recreate -d
```

Once running, access the interface at `http://localhost:5000`.
