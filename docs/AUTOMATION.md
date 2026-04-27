# Automation Bridge & Scheduling System

The Gemini WebUI Automation Bridge provides external tools (like Jenkins) programmatic access to the underlying terminal sessions. This allows you to queue commands, wait for them to finish, and retrieve the full output, all through a REST API.

## Security Configuration

All Automation Bridge API endpoints are protected using Bearer token authentication.

1. Generate an API key or define one in your environment:
   ```bash
   export GEMINI_API_KEY="your-secure-api-key"
   ```
2. Include the API key in your HTTP requests using the `Authorization` header:
   ```http
   Authorization: Bearer your-secure-api-key
   ```

## Heuristic vs. Strict Mode (Markers)

When a command is injected into an active terminal session, the backend needs to know when the command has finished executing. The Automation Bridge provides two modes for detecting completion:

### 1. Heuristic Mode

In Heuristic Mode, the backend relies on "idleness detection" to determine if a job is complete. It monitors the terminal output and process tree. If the terminal goes silent for a configurable timeout (e.g., 500ms) and the last line of output matches a standard shell prompt (`$`, `#`, `>`, `%`), the job is considered complete.

- **Pros:** Works out-of-the-box with any standard shell. Doesn't pollute the command history with wrapper scripts.
- **Cons:** Less reliable for commands that naturally pause or produce no output for extended periods. Cannot reliably capture the exit code (`$?`).

### 2. Strict Mode (Markers)

In Strict Mode, the backend wraps your provided prompt with explicit start and end markers.
For example, if your prompt is `npm run build`, the backend actually executes:

```bash
echo ___GAB_START___; npm run build; echo ___GAB_END___ $?
```

The execution engine scans the PTY stream for these exact string markers. It captures everything between them as the job output and parses the final integer as the true exit code.

- **Pros:** 100% reliable completion detection. Definitively captures the exit code. Immune to unexpected silences.
- **Cons:** The marker commands will appear in the shell's history. Only works in shells that support `;` and `$?` (like Bash, Zsh, sh).

## REST API Documentation (v1)

### Queue an Ad-Hoc Job

Queues a command to be executed on a specific terminal session. The backend will wait until the session is idle before injecting the command.

**Endpoint:** `POST /api/v1/automation/queue`

**Request Body (JSON):**

```json
{
  "tab_id": "string",
  "prompt": "string",
  "mode": "strict|heuristic",
  "timeout": 300
}
```

**Response (200 OK):**

```json
{
  "job_id": "string",
  "status": "queued"
}
```

### Poll Job Status and Output

Retrieves the current status, output, and exit code (if applicable) for a queued or completed job.

**Endpoint:** `GET /api/v1/automation/jobs/{job_id}`

**Response (200 OK):**

```json
{
  "job_id": "string",
  "status": "completed",
  "output": "...",
  "exit_code": 0,
  "timestamp": "2024-10-27T10:00:00Z"
}
```

### Manage Schedules

(API details for `/api/v1/schedules` will be documented as the scheduling engine is finalized.)

## Jenkins Integration

You can easily integrate the Automation Bridge into your CI/CD pipelines.

### Example Jenkinsfile Stage

```groovy
pipeline {
    agent any
    environment {
        GEMWEBUI_URL = 'http://gemini-webui:5001'
        // Store your API key in Jenkins credentials
        GEMINI_API_KEY = credentials('gemini-api-key')
    }
    stages {
        stage('Automated Task') {
            steps {
                script {
                    sh '''
                    chmod +x scripts/wait-for-job.sh
                    ./scripts/wait-for-job.sh --tab "target-tab-id" --prompt "npm run test"
                    '''
                }
            }
        }
    }
}
```
