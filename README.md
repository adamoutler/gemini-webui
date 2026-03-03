# Gemini WebUI

**The ultimate "Couch-Friendly" terminal for your Gemini AI.**

Gemini WebUI provides a high-fidelity, persistent web interface for the Gemini CLI. It allows you to monitor your projects, run long-running AI tasks, and interact with your host machine from any device with a browser—whether you're at your desk or relaxing on the couch with a tablet.

## 🚀 Key Features

### 📱 Mobile-First Accessibility
*   **Touch-Native Drag & Drop**: Reorder connection cards with smooth, mobile-optimized touch handles—bypassing unreliable mobile browser drag-and-drop APIs.
*   **Adaptive Viewport Integration**: Dynamically adjusts layout and terminal fit when the on-screen keyboard is toggled, ensuring your prompt is always visible.
*   **Compact UI Controls**: Optimized mobile control bar with reduced footprint, perfectly fitting narrow displays like the Pixel 9 Pro Fold.
*   **Smart Keyboard Handling**: implemements a "Single Character Buffer" to prevent mobile OS autocorrect and predictive text from corrupting terminal input.

### 🖥️ True Cross-Device Persistence
*   **Independent Window State**: Each browser tab maintains its own workspace configuration using `sessionStorage`, enabling native multi-monitor workflows.
*   **Session Reclaiming**: Easily "pull" running terminal sessions from one device to another via the "Backend Managed Sessions" dashboard.
*   **Real-time Reattach Notifications**: Instantly notified if another device reclaims your active session ("Session stolen by another device").
*   **Visual Continuity**: Every session maintains a 10,000-character rolling buffer, ensuring your visual state is perfectly restored upon reattachment or refresh.
*   **Always-On Background Tasks**: Backend PTY processes continue running even if all browser windows are closed.

### 🔌 Advanced Connectivity
*   **Dynamic Launcher**: Backend session states are polled every 10 seconds, ensuring your connection dashboard is always up-to-date without refreshing.
*   **Host Management**: Add, Edit, Delete, and Reorder connection cards with an optimistic, animated interface.
*   **Quick Connect Bar**: Instantly connect via SSH using `user@host[:port] [directory]` syntax with automatic persistence.
*   **Descriptive Tab Titles**: Tab titles automatically sync with resumed Gemini session names or terminal escape sequences.

### 🔑 Robust SSH Key Management
*   **Instance Key Generation**: Automatic generation of a unique Ed25519 key pair on first run.
*   **Clipboard Fallback**: Robust "Copy to Clipboard" support that works in both secure (HTTPS) and non-secure (HTTP/IP-based) dev environments.
*   **Secure Authorization Snippet**: One-click "Copy Snippet" provides a one-liner to authorize the WebUI instance on any remote host.

---

## 🏗 Architecture

```mermaid
graph TD
    User([User Device]) -- WebSockets --> App[Flask SessionManager]
    App -- PTY + Buffer --> Local[Local Gemini CLI]
    App -- SSH Tunnel --> Remote[Remote Host]
    subgraph Backend Persistence
        App -- Registry --> Sessions[(Active Registry)]
    end
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
| `GEMINI_BIN` | Path to the Gemini executable | `gemini` |

### Volumes
*   `data:/data`: Persists app config, SSH keys, and CLI state (linked to `/home/node/.gemini`).

---

## 🏗 Quick Start

Build and launch the container with a single command:

```bash
docker compose up --build --force-recreate -d
```

Once running, access the interface at `http://localhost:5000`.
