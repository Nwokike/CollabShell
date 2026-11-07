# Colab Client Libraries — API Reference & Gap Analysis

> **Generated from installed package source** at `.venv/lib/python3.14/site-packages/colab_cli/` (google-colab-cli 0.7.4) and mapped against ColabShell's `src/services/colab/`.

---

## 1. Authentication (OAuth2 Device Flow, Token Storage/Refresh, Scopes)

### 1.1 Public Scopes (Library)

**Source:** `colab_cli/auth.py:44-51`

```python
PUBLIC_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/colaboratory",
    "https://www.googleapis.com/auth/drive.file",
]
```

### 1.2 AuthProvider Enum

**Source:** `colab_cli/auth.py:33-41`

```python
class AuthProvider(str, enum.Enum):
    OAUTH2 = "oauth2"
    ADC = "adc"
```

### 1.3 Token Config Path

**Source:** `colab_cli/auth.py:54`

```python
TOKEN_CONFIG_PATH = os.path.expanduser("~/.config/colab-cli/token.json")
```

### 1.4 Remote Copy-Paste OAuth Flow (Primary)

**Source:** `colab_cli/auth.py:76-94`

```python
def _run_remote_flow(client_config: dict) -> Credentials:
    """Run the remote copy-paste OAuth2 flow.
    
    Prints an authorization URL, waits for the user to sign in and paste back
    the authorization code shown on Google's landing page, then exchanges the
    code for credentials.
    """
    flow = InstalledAppFlow.from_client_config(client_config, PUBLIC_SCOPES)
    flow.redirect_uri = REMOTE_REDIRECT_URI  # https://sdk.cloud.google.com/applicationdefaultauthcode.html
    auth_url, _ = flow.authorization_url(prompt="consent", token_usage="remote")
    # ... prints URL, reads code from stdin ...
    flow.fetch_token(code=code)
    return flow.credentials
```

**Usage:**
```python
from colab_cli.auth import get_credentials, AuthProvider
from google.auth.transport.requests import AuthorizedSession

# OAuth2 (default)
session = get_credentials(config_path="~/.colab-cli-oauth-config.json", provider=AuthProvider.OAUTH2)
# session is an AuthorizedSession with credentials

# ADC (Application Default Credentials)
session = get_credentials(provider=AuthProvider.ADC)
```

### 1.5 ADC Credentials

**Source:** `colab_cli/auth.py:154-219`

```python
def _get_adc_credentials() -> Credentials:
    """Retrieves credentials using Google Application Default Credentials.
    
    Honors the standard ADC discovery chain (GOOGLE_APPLICATION_CREDENTIALS,
    gcloud auth application-default login, GCE/GKE metadata server, etc.).
    
    The RuntimeService at colab.pa.googleapis.com requires the `colaboratory`
    scope. Most ADC credential types support `with_scopes`; user credentials
    minted by `gcloud auth application-default login` do not.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"Your application has authenticated using end user credentials.*")
        creds, _ = google.auth.default(scopes=list(PUBLIC_SCOPES))
    # ... refresh logic ...
    if getattr(creds, "requires_scopes", False):
        creds = creds.with_scopes(list(PUBLIC_SCOPES))
    return creds
```

### 1.6 Unified Entry Point

**Source:** `colab_cli/auth.py:222-242`

```python
def get_credentials(
    config_path: Optional[str] = None,
    provider: AuthProvider = AuthProvider.OAUTH2,
) -> requests.AuthorizedSession:
    """Unified entry point for retrieving an authorized session.
    
    Args:
        config_path: Path to the OAuth2 client config JSON. Only consulted when
          provider is OAUTH2.
        provider: Which authentication strategy to use.
    """
    if provider == AuthProvider.OAUTH2:
        if not config_path:
            config_path = os.path.expanduser("~/.colab-cli-oauth-config.json")
        creds = _get_google_auth_credentials(config_path)
    elif provider == AuthProvider.ADC:
        creds = _get_adc_credentials()
    else:
        raise ValueError(f"Unknown auth provider: {provider!r}")
    return requests.AuthorizedSession(creds)
```

### 1.7 OAuth2 Client Config (Embedded)

**Source:** `colab_cli/oauth_config.json` (packaged resource)

```json
{
  "installed": {
    "client_id": "764086051850-...apps.googleusercontent.com",
    "project_id": "google.com:colab-cli",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "...",
    "redirect_uris": ["https://sdk.cloud.google.com/applicationdefaultauthcode.html"]
  }
}
```

---

## 2. Session Management

### 2.1 Environment Configurations

**Source:** `colab_cli/client.py:43-52`

```python
@dataclass
class ColabEnvironment(abc.ABC):
    domain: str
    api: str

@dataclass
class Prod(ColabEnvironment):
    domain: str = "https://colab.research.google.com"
    api: str = "https://colab.pa.googleapis.com"
```

### 2.2 Hardware Enums

**Source:** `colab_cli/client.py:62-94`

```python
class Accelerator(str, Enum):
    NONE = "NONE"
    G4 = "G4"
    T4 = "T4"
    L4 = "L4"
    A100 = "A100"
    H100 = "H100"
    V5E1 = "V5E1"
    V6E1 = "V6E1"

class Variant(str, Enum):
    DEFAULT = "DEFAULT"
    GPU = "GPU"
    TPU = "TPU"

class AssignmentVariant(int, Enum):
    DEFAULT = 0
    GPU = 1
    TPU = 2

class Shape(int, Enum):
    STANDARD = 0
    HIGH_RAM = 1
```

### 2.3 Shape Resolution

**Source:** `colab_cli/client.py:97-111`

```python
HIGH_MEM_ONLY_ACCELERATORS = frozenset({Accelerator.L4, Accelerator.V5E1, Accelerator.V6E1})

def resolve_assign_shape(accelerator: Optional[Accelerator], *, high_mem: bool = False) -> Optional[Shape]:
    """Map CLI intent to the shape query param for /tun/m/assign."""
    if not high_mem:
        return None
    if accelerator in HIGH_MEM_ONLY_ACCELERATORS:
        return None
    return Shape.HIGH_RAM
```

### 2.4 Assignment Response Models

**Source:** `colab_cli/client.py:121-166`

```python
class RuntimeProxyInfo(BaseModel):
    token: str
    token_expires_in_seconds: int = Field(..., alias="tokenExpiresInSeconds")
    url: str
    def expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=self.token_expires_in_seconds)

class ListedAssignment(BaseModel):
    accelerator: Accelerator
    endpoint: str
    variant: AssignmentVariant
    machine_shape: Shape = Field(..., alias="machineShape")
    runtime_proxy_info: RuntimeProxyInfo = Field(..., alias="runtimeProxyInfo")

class PostAssignmentResponse(BaseModel):
    accelerator: Accelerator
    endpoint: str
    runtime_proxy_info: RuntimeProxyInfo = Field(..., alias="runtimeProxyInfo")
    variant: AssignmentVariant

class GetAssignmentResponse(BaseModel):
    acc: str = Field(..., alias="acc")
    nbh: str = Field(..., alias="nbh")
    token: str = Field(..., alias="token")
    variant: Variant = Field(..., alias="variant")

class Assignment(BaseModel):
    endpoint: str
    runtime_proxy_info: RuntimeProxyInfo = Field(..., alias="runtimeProxyInfo")
```

### 2.5 Client Class

**Source:** `colab_cli/client.py:184-331`

```python
class Client:
    def __init__(self, env: ColabEnvironment, session, logger=None):
        self.colab_domain = env.domain
        self.colab_api_domain = env.api
        self.session = session  # requests.AuthorizedSession
        self.logger = logger or logging.getLogger(__name__)

    def get_consumption_user_info(self) -> ConsumptionUserInfo:
        """Fetch account-level CCU balance and usage rate from the session backend."""
        url = urljoin(self.colab_domain, f"{TUN_ENDPOINT}/ccu-info")
        ccu = self._issue_request(url, schema=CcuInfo)
        return consumption_user_info_from_tunnel(ccu)

    def list_assignments(self) -> List[ListedAssignment]:
        url = urljoin(self.colab_domain, f"{TUN_ENDPOINT}/assignments")
        assignments = self._issue_request(url, schema=ListedAssignments)
        return assignments.assignments

    def unassign(self, endpoint: str):
        url = urljoin(self.colab_domain, f"{TUN_ENDPOINT}/unassign/{endpoint}")
        resp = self._issue_request(url, schema=GetUnassignRequest)
        headers = {COLAB_XSRF_TOKEN_HEADER["key"]: resp.token}
        return self._issue_request(url, method="POST", headers=headers, schema=BaseModel)

    def assign(
        self,
        notebook_hash: uuid.UUID,
        variant: Optional[Variant] = None,
        accelerator: Optional[Accelerator] = None,
        shape: Optional[Shape] = None,
    ) -> Union[PostAssignmentResponse, Assignment]:
        # GET /tun/m/assign?nbh=... -> GetAssignmentResponse (existing) or Assignment (ready)
        # POST /tun/m/assign with X-Goog-Colab-Token -> PostAssignmentResponse (new assignment)
```

**Usage:**
```python
from colab_cli.client import Client, Prod, Accelerator, Variant, Shape
from colab_cli.auth import get_credentials, AuthProvider
import uuid

session = get_credentials(provider=AuthProvider.OAUTH2)
client = Client(Prod(), session)

# Create new session
res = client.assign(
    uuid.uuid4(),
    variant=Variant.GPU,
    accelerator=Accelerator.T4,
    shape=Shape.STANDARD
)

# List sessions
assignments = client.list_assignments()

# Stop session
client.unassign(endpoint)
```

### 2.6 SessionState (Local Persistence)

**Source:** `colab_cli/state.py:25-37`

```python
class SessionState(BaseModel):
    name: str
    token: str
    url: str
    endpoint: str
    token_expires_at: Optional[datetime] = None
    variant: str = "DEFAULT"
    accelerator: str = "NONE"
    machine_shape: str = "STANDARD"
    kernel_id: Optional[str] = None
    session_id: Optional[str] = None
    last_execution: Optional[Tuple[str, Optional[str], str]] = None
    running: Optional[str] = None
```

### 2.7 State Store (Thread-Safe File Lock)

**Source:** `colab_cli/state.py:112-159`

```python
class StateStore(_LockedFileStore):
    def __init__(self, path: Optional[str] = None):
        if not path:
            path = os.path.expanduser("~/.config/colab-cli/sessions.json")
        super().__init__(path)

    def add(self, state: SessionState): ...
    def get(self, name: str) -> Optional[SessionState]: ...
    def remove(self, name: str): ...
    def list(self) -> Dict[str, SessionState]: ...
```

---

## 3. Code Execution

### 3.1 ColabRuntime

**Source:** `colab_cli/runtime.py:23-262`

```python
class ColabRuntime:
    def __init__(
        self,
        url: str,
        token: str,
        session_name: Optional[str] = None,
        history: Optional[Any] = None,
        kernel_id: Optional[str] = None,
        session_id: Optional[str] = None,
        on_kernel_started: Optional[Callable[[str], None]] = None,
        on_session_started: Optional[Callable[[str], None]] = None,
    ):
        self.url = url
        self.token = token
        self.session_name = session_name
        self.history = history
        self.kernel_id = kernel_id
        self.session_id = session_id
        self.on_kernel_started = on_kernel_started
        self.on_session_started = on_session_started
        self._kernel_client = None
        self.colab_request_hook: Optional[Callable[[Dict[str, Any], Any], None]] = None
```

### 3.2 execute_code

**Source:** `colab_cli/runtime.py:180-262`

```python
def execute_code(
    self,
    code: str,
    allow_stdin: bool = False,
    stdin_hook: Any = None,
    output_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Execute code in the Colab kernel.
    
    Args:
        code: Python code to execute.
        allow_stdin: Allow stdin prompts (input()).
        stdin_hook: Callable(prompt) -> str for stdin handling.
        output_hook: Callable(output_dict) for streaming outputs.
        timeout: Wall-clock timeout in seconds (default: upstream default ~10s).
    
    Returns:
        List of output dicts with keys: output_type, text, data, ename, evalue, traceback, etc.
    """
    kwargs = {"allow_stdin": allow_stdin}
    if timeout is not None:
        kwargs["timeout"] = timeout

    # ... stdin_hook wrapping for history logging ...

    if output_hook:
        # Streaming path via execute_interactive
        outputs = []
        def wrapped_output_hook(msg):
            new_indexes = default_output_hook(outputs, msg)
            if new_indexes:
                for idx in sorted(new_indexes):
                    if idx < len(outputs):
                        output_hook(outputs[idx])
        reply = self.kernel_client.execute_interactive(code, output_hook=wrapped_output_hook, **kwargs)
        reply_content = reply["content"] if reply else {"status": "error"}
    else:
        # Batch path via execute
        reply = self.kernel_client.execute(code, **kwargs)
        if not reply:
            return []
        outputs = reply.get("outputs", [])
        reply_content = reply

    # Error synthesis
    if reply_content.get("status") == "error":
        has_error_output = any(o.get("output_type") == "error" for o in outputs)
        if not has_error_output:
            outputs.append({
                "output_type": "error",
                "ename": reply_content.get("ename", "Error"),
                "evalue": reply_content.get("evalue", "Unknown error"),
                "traceback": reply_content.get("traceback", []),
            })
    return outputs
```

### 3.3 restart / stop

**Source:** `colab_cli/runtime.py:174-178, 264-278`

```python
def restart(self, timeout: Optional[float] = None):
    self.kernel_client.restart(timeout=timeout)

def stop(self, shutdown_kernel: bool = False):
    if self._kernel_client:
        try:
            client = self._kernel_client._manager.client
            client.stop_channels()
            if client.kernel_socket:
                client.kernel_socket.close()
            if shutdown_kernel:
                self._kernel_client._manager.shutdown_kernel(now=True)
        except Exception:
            logging.exception("Error stopping kernel client")
```

### 3.4 Output Types (from jupyter_kernel_client)

```python
# Stream output
{"output_type": "stream", "name": "stdout|stderr", "text": "..."}

# Execute result / display data
{"output_type": "execute_result|display_data", "data": {"text/plain": "...", "image/png": "base64...", ...}, "metadata": {...}}

# Error
{"output_type": "error", "ename": "ErrorType", "evalue": "message", "traceback": ["line1", "line2", ...]}
```

---

## 4. Files API (ContentsClient)

**Source:** `colab_cli/contents.py:24-93`

```python
class ContentsClient:
    def __init__(self, session_state: SessionState):
        self.base_url = session_state.url.rstrip("/")
        self.token = session_state.token

    def _request(self, method: str, path: str, params: dict = None, json_data: dict = None):
        quoted_path = quote(path.strip("/"), safe="/")
        url = f"{self.base_url}/api/contents/{quoted_path}"
        req_params = {"authuser": "0", "colab-runtime-proxy-token": self.token}
        if params:
            req_params.update(params)
        response = requests.request(method, url, params=req_params, json=json_data)
        # 404 -> FileNotFoundError
        if method == "DELETE":
            return None
        return response.json()

    def list_dir(self, path: str):
        return self._request("GET", path)

    def upload(self, local_path: str, remote_path: str):
        """Upload a file (base64 encoded)."""
        with open(local_path, "rb") as f:
            content = f.read()
        b64_content = base64.b64encode(content).decode("ascii")
        filename = remote_path.split("/")[-1]
        payload = {
            "name": filename,
            "path": remote_path,
            "type": "file",
            "format": "base64",
            "content": b64_content,
            "chunk": 1,
        }
        return self._request("PUT", remote_path, json_data=payload)

    def download(self, remote_path: str, local_path: str):
        data = self._request("GET", remote_path, params={"content": "1"})
        if data.get("type") == "directory":
            raise IsADirectoryError(f"Cannot download a directory: {remote_path}")
        content = data.get("content", "")
        fmt = data.get("format")
        if fmt == "base64":
            content_bytes = base64.b64decode(content)
        else:
            content_bytes = str(content).encode("utf-8")
        with open(local_path, "wb") as f:
            f.write(content_bytes)

    def rm(self, remote_path: str):
        self._request("DELETE", remote_path)
```

**Usage:**
```python
from colab_cli.contents import ContentsClient
from colab_cli.state import SessionState

s = SessionState(name="test", token="...", url="...", endpoint="...")
client = ContentsClient(s)

# List
items = client.list_dir("/content")

# Upload
client.upload("local.py", "/content/remote.py")

# Download
client.download("/content/remote.py", "local.py")

# Delete
client.rm("/content/remote.py")
```

---

## 5. Logs / History

### 5.1 HistoryLogger

**Source:** `colab_cli/history.py:21-65`

```python
class HistoryLogger:
    def __init__(self, log_dir: str = "~/.config/colab-cli/history"):
        self.log_dir = os.path.expanduser(log_dir)
        os.makedirs(self.log_dir, exist_ok=True)

    def log_event(self, session_name: str, event_type: str, data: Dict[str, Any]):
        """Append a structured event to the session's history file.
        
        event_types:
          - session_created
          - session_terminated
          - execution (code + outputs)
          - input_requested (stdin prompts/replies)
          - file_operation (ls, rm, upload, download)
          - automation (auth, install, drivemount)
        """
        log_path = os.path.join(self.log_dir, f"{session_name}.jsonl")
        event = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event_type": event_type,
            **data,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def list_sessions(self) -> List[str]: ...
    def get_history(self, session_name: str) -> List[Dict[str, Any]]: ...
```

### 5.2 Export (Converter)

**Source:** `colab_cli/converter.py:22-184`

```python
def export_history(events: List[Dict[str, Any]], session_name: str, output_path: str):
    """Export to .ipynb, .jsonl, .md, or .txt based on extension."""
    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".ipynb":
        nb = convert_history_to_ipynb(events, session_name)
        with open(output_path, "w") as f: nbformat.write(nb, f)
    elif ext == ".jsonl": ...
    elif ext == ".md": ...
    elif ext == ".txt": ...

def convert_history_to_ipynb(events, session_name) -> nbformat.NotebookNode:
    """Convert events to Jupyter Notebook v4."""
    nb = nbformat.v4.new_notebook()
    # ... builds markdown + code cells from history ...
    return nb
```

---

## 6. Usage / Quota (GPU/TPU Availability, Compute Units)

### 6.1 Consumption Models

**Source:** `colab_cli/consumption.py:20-44`

```python
class CcuInfo(BaseModel):
    current_balance: float = Field(..., alias="currentBalance")
    consumption_rate_hourly: float = Field(..., alias="consumptionRateHourly")
    assignments_count: int = Field(..., alias="assignmentsCount")

class ConsumptionUserInfo(BaseModel):
    paid_compute_units_balance: float = Field(..., alias="paidComputeUnitsBalance")
    consumption_rate_hourly: float = Field(..., alias="consumptionRateHourly")
    assignments_count: int = Field(..., alias="assignmentsCount")

def consumption_user_info_from_tunnel(ccu: CcuInfo) -> ConsumptionUserInfo:
    return ConsumptionUserInfo(
        paid_compute_units_balance=ccu.current_balance,
        consumption_rate_hourly=ccu.consumption_rate_hourly,
        assignments_count=ccu.assignments_count,
    )

def format_consumption_status(info: ConsumptionUserInfo) -> str:
    return f"Current balance: {info.paid_compute_units_balance:.2f} compute units\nUsage rate: {info.consumption_rate_hourly:.2f}/hr\nActive assignments: {info.assignments_count:.0f}"
```

### 6.2 Client Method

**Source:** `colab_cli/client.py:246-250`

```python
def get_consumption_user_info(self) -> ConsumptionUserInfo:
    url = urljoin(self.colab_domain, f"{TUN_ENDPOINT}/ccu-info")
    ccu = self._issue_request(url, schema=CcuInfo)
    return consumption_user_info_from_tunnel(ccu)
```

---

## 7. VM / Hardware Operations

### 7.1 Accelerator/Variants (see Section 2.2)

### 7.2 Automation Commands (Auth, Drive Mount, Package Install)

**Source:** `colab_cli/commands/automation.py:42-264`

```python
INTERACTIVE_AUTOMATION_TIMEOUT_SEC = 600  # 10 min for OAuth flows

def run_automation(name, op, code, allow_stdin=False, path=None, timeout=None):
    # ... sets up runtime with colab_request_hook for Drive auth ...
    runtime.colab_request_hook = drivefs_hook  # handles dfs_ephemeral authType
    outputs = runtime.execute_code(code, allow_stdin=allow_stdin, timeout=timeout)

def auth(session=None):
    code = "import os\nos.environ['USE_AUTH_EPHEM'] = '0'\nfrom google.colab import auth\nauth.authenticate_user()"
    run_automation(name, "auth", code, allow_stdin=True, timeout=INTERACTIVE_AUTOMATION_TIMEOUT_SEC)

def drivemount(session=None, path="/content/drive"):
    code = f"from google.colab import drive\ndrive.mount('{path}')"
    run_automation(name, "drivemount", code, allow_stdin=True, path=path, timeout=INTERACTIVE_AUTOMATION_TIMEOUT_SEC)

def install(session=None, packages=None, requirement=None):
    # Uses uv or pip
    code = f"""import subprocess, sys
try: subprocess.check_call(['uv', 'pip', 'install', '--system'] + {packages!r})
except: subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + {packages!r})"""
    run_automation(name, "install", code)
```

**Drive Auth Hook Pattern (Source: `colab_cli/commands/automation.py:55-132`):**

```python
def drivefs_hook(deserialize_msg, wsclient):
    content = deserialize_msg.get("content", {})
    if content.get("request", {}).get("authType") == "dfs_ephemeral":
        msg_id = deserialize_msg.get("metadata", {}).get("colab_msg_id")
        # 1. Dry-run GET to check if creds authorized
        # 2. If not authorized, get redirect URI, prompt user
        # 3. POST with dryrun=false to propagate credentials
        # 4. Send input_reply to kernel to continue mount
        return True  # intercept handled
    return False
```

---

## 8. Terminal (WebSocket Attach, Input, Resize)

### 8.1 Library Terminal (WebSocket-based)

**Source:** `colab_cli/console.py:45-172`

```python
def connect_console(session: SessionState):
    parsed = urlparse(session.url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{parsed.netloc}/colab/tty?colab-runtime-proxy-token={session.token}"

    ws = websocket.WebSocketApp(
        url=ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    # Raw TTY mode with termios, SIGWINCH handling
    ws.run_forever()
```

### 8.2 Terminal Messages

```python
# Server -> Client
{"data": "ANSI escape sequences and text"}

# Client -> Server
{"data": "keystroke characters"}
{"cols": 80, "rows": 24}  # resize
```

---

## 9. REPL

**Source:** `colab_cli/repl.py:32-174`

```python
class ColabREPL:
    def __init__(self, runtime, session_name=None, history_logger=None, output_image=None):
        self.runtime = runtime
        self.session_name = session_name
        self.history_logger = history_logger
        self.output_image = output_image
        # prompt_toolkit session with Python lexer, key bindings

    def execute(self, code: str):
        outputs = self.runtime.execute_code(code, output_hook=lambda o: self.display_output(o))
        self.repl_history.append({"input": code, "outputs": outputs or []})
        if self.history_logger and self.session_name:
            self.history_logger.log_event(self.session_name, "execution", {"code": code, "outputs": outputs or []})

    def run(self):
        while True:
            result = self.session.prompt(">>> ", style=self.style, multiline=True)
            if result is None or not result.strip(): continue
            if result.lower() in ("/quit", "quit()", "exit()"): break
            self.execute(result)
```

---

## 10. `colab run` — One-Shot Script Execution

**Source:** `colab_cli/commands/run.py:198-508`

```python
def run_command(
    script: str,
    script_args: List[str] = None,
    session: str = None,
    tpu: str = None,
    gpu: str = None,
    high_mem: bool = False,
    keep: bool = False,
    timeout: float = 30.0,
    env: List[str] = None,
):
    """Create session -> execute script -> stop session (unless --keep).
    
    Supports shebang: #!/usr/bin/env -S colab run --gpu T4
    """
    # 1. Create session with requested hardware
    # 2. Build payload: sys.argv, __name__='__main__', env vars, strip shebang
    # 3. Execute with SystemExit handling (maps to exit codes)
    # 4. Teardown unless --keep
```

**Script Payload Builder (Source: `colab_cli/commands/run.py:56-88`):**

```python
def _build_script_payload(script_path, script_args, env_vars) -> str:
    argv_literal = f"[{', '.join(repr(x) for x in [basename] + script_args)}]"
    return (
        "import sys, warnings\n"
        f"sys.argv = {argv_literal}\n"
        "__name__ = '__main__'\n"
        "warnings.filterwarnings('ignore', message=\"To exit: use\")\n"
        + _build_env_prelude(env_vars or {})
        + _strip_shebang(body)
    )
```

---

## GAP ANALYSIS

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **high** | `services/colab/auth.py:78-107` (`get_auth_url_impl`) | `colab_cli/auth.py:76-94` (`_run_remote_flow`) | **Duplicates OAuth flow logic** — reimplements `InstalledAppFlow` setup, redirect_uri, code_verifier storage. The library already has `_run_remote_flow` that does this; app should call `get_credentials()` which handles the full flow. | Use `get_credentials()` directly. If custom UI needed, extract auth URL from the library's flow object rather than recreating. |
| 2 | **high** | `services/colab/auth.py:110-176` (`authenticate_oauth2_impl`) | `colab_cli/auth.py:76-94, 120-151` | **Full OAuth token exchange reimplemented** — duplicates `flow.fetch_token()`, credential refresh, token storage to `TOKEN_CONFIG_PATH`, and tokeninfo call. Library's `_get_google_auth_credentials` already handles load/refresh/save. | Call `get_credentials()` which returns an `AuthorizedSession`; extract token from `session.credentials.token` if needed. |
| 3 | **high** | `services/colab/auth.py:179-262` (`check_auth_impl`) | `colab_cli/auth.py:120-151` (`_get_google_auth_credentials`) | **Reimplements token load/refresh/validation** — manually loads from `TOKEN_CONFIG_PATH`, refreshes, calls tokeninfo. Library does this internally in `_get_google_auth_credentials`. | Use `get_credentials()` and check `creds.valid` / `creds.expired`; or call the internal `_get_google_auth_credentials` if exposed. |
| 4 | **high** | `services/colab/session_ops.py:80-203` (`new_session_impl`) | `colab_cli/commands/session.py:94-217` (`new`) | **Reimplements `colab new` command logic** — duplicates hardware mapping, `resolve_assign_shape`, error handling for `TooManyAssignmentsError`/`ColabRequestError` (400/500), session state creation, history logging. | Call `commands.session.new()` or extract a reusable `create_session()` from the library. |
| 5 | **high** | `services/colab/session_ops.py:210-315` (`list_sessions_impl`) | `colab_cli/commands/session.py:254-278` (`sessions_command`) | **Reimplements session listing & recovery** — duplicates assignment fetch, local/remote reconciliation, recovered session creation, stale pruning, status formatting. | Use `client.list_assignments()` directly; use `State.sync_sessions()` for reconciliation. |
| 6 | **high** | `services/colab/session_ops.py:318-352` (`load_session_fresh`) | `colab_cli/common.py:86-112` (`State.get_session`) | **Duplicates token refresh logic** — checks `token_expires_at` margin, calls `list_assignments`, updates token/url/expires_at. `State.get_session` does exactly this. | Call `State().get_session(name)` which handles refresh and pruning. |
| 7 | **high** | `services/colab/session_ops.py:355-389` (`_refresh_runtime_token_sync`) | `colab_cli/common.py:86-112` (`State.get_session`) | **Duplicates token heal logic** — same as `load_session_fresh` but returns bool. Library's `get_session` already returns fresh session or None. | Use `State().get_session(name, ignore_missing_session=True)` and compare token. |
| 8 | **high** | `services/colab/session_ops.py:410-445` (`stop_session_impl`) | `colab_cli/commands/session.py:324-348` (`stop`) | **Reimplements `colab stop`** — duplicates runtime.stop(shutdown_kernel=True), client.unassign, store.remove, history log. | Call `commands.session.stop()` or use `State().prune_session()` + `client.unassign()`. |
| 9 | **high** | `services/colab/session_ops.py:448-531` (`restart_kernel_impl`) | `colab_cli/commands/session.py:220-252` (`restart_kernel`) | **Reimplements kernel restart with 404 retry** — duplicates the token heal + retry pattern. `commands.session.restart_kernel` does this. | Call `commands.session.restart_kernel()` or replicate via `ColabRuntime.restart()` with token heal. |
| 10 | **medium** | `services/colab/execution.py:90-428` (`exec_code_impl`) | `colab_cli/commands/execution.py:140-283` (`exec_command`) | **Reimplements code execution pipeline** — duplicates preflight `/content` setup, env prelude building, output streaming hook, Drive auth intercept (`drivefs_hook`), stdin hook wrapping, 404 retry with token heal, history logging (with divergence: app logs `env_keys` only, library logs full prelude). | Use `ColabRuntime.execute_code()` directly. For Drive auth, use `runtime.colab_request_hook` pattern from library. |
| 11 | **medium** | `services/colab/execution.py:201-318` (`drivefs_hook` inside `exec_code_impl`) | `colab_cli/commands/automation.py:55-132` (`drivefs_hook`) | **Duplicates Drive auth hook** — nearly identical logic for `dfs_ephemeral` interception, dry-run check, user prompt, credential propagation. App version adds retry loop (6×2s) which is an improvement. | Extract `drivefs_hook` to shared utility; app's retry loop is better — contribute upstream. |
| 12 | **medium** | `services/colab/files_ops.py:15-41` (`_run_with_token_heal`) | `colab_cli/common.py:86-112` (`State.get_session`) | **Custom token heal wrapper** — catches 404, calls `refresh_session_token`, retries once. Duplicates `load_session_fresh` pattern. | Use `load_session_fresh(st, name)` before each operation; it already heals token. |
| 13 | **medium** | `services/colab/files_ops.py:44-101` (`ls_impl`), `104-148` (`upload_impl`), `151-195` (`download_impl`), `291-322` (`rm_impl`) | `colab_cli/commands/files.py:26-132` (`ls`, `upload`, `download`, `rm`) | **Reimplements file commands** — duplicates `ContentsClient` usage, path normalization, history logging. `commands.files` functions do this. | Call `commands.files.ls/upload/download/rm()` or use `ContentsClient` directly with `load_session_fresh`. |
| 14 | **medium** | `services/colab/files_ops.py:198-289` (`download_folder_impl`) | *No direct library equivalent* | **Custom folder download via VM-side zip** — executes shell `zip`/`shutil.make_archive` on VM, downloads zip, cleans up. Not in library. | This is a valid app-specific extension. Consider adding to library as `ContentsClient.download_folder()`. |
| 15 | **low** | `services/colab/vm_ops.py:7-34` (`mount_drive_impl`) | `colab_cli/commands/automation.py:197-216` (`drivemount`) | **Thin wrapper calling `exec_code`** — duplicates the `drive.mount()` code string. Library has `drivemount()` command. | Call `commands.automation.drivemount()` or use shared code string constant. |
| 16 | **low** | `services/colab/vm_ops.py:37-66` (`install_packages_impl`) | `colab_cli/commands/automation.py:219-264` (`install`) | **Duplicates package install code** — same uv/pip fallback code string. | Call `commands.automation.install()` or use shared template. |
| 17 | **low** | `services/colab/vm_ops.py:69-95` (`auth_gcp_on_vm_impl`) | `colab_cli/commands/automation.py:177-194` (`auth`) | **Duplicates GCP auth code** — same `auth.authenticate_user()` code string. | Call `commands.automation.auth()` or use shared constant. |
| 18 | **medium** | `services/colab/terminal_client.py:33-65` (`create_terminal_ws_url`) | `colab_cli/console.py:123-133` (`connect_console` URL building) | **Reimplements terminal WS URL construction** — library uses `/colab/tty` endpoint, app uses `/terminals/websocket` + POST `/api/terminals` for PTY creation. Different endpoints! | App's PTY approach is more featureful (resize, persistent shell). Document the difference; consider contributing PTY support upstream. |
| 19 | **medium** | `services/colab/terminal_client.py:68-402` (`ColabTerminalClient`) | `colab_cli/console.py:45-172` (`connect_console`) | **Full custom WebSocket client** — uses Tornado, handles reconnection, ping/pong, resize, stdin. Library uses `websocket-client` with raw TTY (`/colab/tty`). Different protocols. | App's PTY client is superior for interactive use. Library's `/colab/tty` is simpler but less capable. No direct replacement. |
| 20 | **low** | `services/colab/usage_ops.py:20-72` (`get_usage_impl`) | `colab_cli/client.py:246-250` (`get_consumption_user_info`) | **Wraps library call with auth/online checks** — adds `is_authenticated`, `is_online` guards, cached fallback. Library method is raw. | Wrapper is reasonable for GUI; consider exposing `get_consumption_user_info` on `State.client`. |
| 21 | **low** | `services/colab/logs.py:5-59` | `colab_cli/history.py:21-65`, `colab_cli/converter.py:22-184` | **Uses library history but with custom log dir** — `HistoryLogger(log_dir=...)` pointed at `core.storage_patch.resolve_storage_dir()`. Library defaults to `~/.config/colab-cli/history`. | Pass `log_dir` to `HistoryLogger` (already done). OK. |
| 22 | **info** | `services/colab/text_files.py` | `colab_cli/contents.py:74-90` (`download`/`upload`) | **Text file helpers with size limits** — wraps download/upload with temp files and 512KB limit. Not in library. | Valid app-specific utility. OK. |
| 23 | **medium** | `services/colab/execution.py:119-134` (env validation) | `colab_cli/commands/execution.py:41-62` (`_parse_env_vars`/`_build_env_prelude`) | **Duplicates env var parsing** — app reimplements KEY=VALUE validation (regex `^[A-Za-z_][A-Za-z0-9_]*$`) and prelude building to avoid importing `execution.py` (pulls `termios` on Windows). | Extract `_parse_env_vars`/`_build_env_prelude` to a shared non-POSIX module in library. |
| 24 | **high** | `services/colab/session_ops.py:59-66` (`_load_local_sessions`) | `colab_cli/common.py:38-77` (`State`) | **Creates new `State()` instance per call** — bypasses singleton `state` in `colab_cli.common`, so OAuth config, auth provider, stores are reinitialized each call. | Use the shared `state` singleton from `colab_cli.common` (as library commands do). |
| 25 | **high** | Multiple files (`services/colab/*.py`) | `colab_cli/common.py:183` (`state = State()`) | **App doesn't use the library's singleton `state`** — each `_impl` function creates `State()` anew, losing cached client, stores, history logger. This causes redundant auth, token loads, and potential race conditions. | Import `from colab_cli.common import state` and use `state.client`, `state.store`, `state.history` everywhere. |
| 26 | **medium** | `services/colab/session_ops.py:120-148` (error handling) | `colab_cli/commands/session.py:144-171` | **App adds 500+high_mem handling** — detects 503 on free accounts for CPU+high_mem and raises friendly error. Library only handles 400 (quota) and 412 (precondition). | Good improvement — consider contributing upstream. |
| 27 | **medium** | `services/colab/execution.py:364-397` (404 retry) | `colab_cli/runtime.py:174-178` (restart) | **App retries execution on 404 with token heal** — library's `restart` doesn't auto-heal. App pattern is more robust. | Good pattern — consider adding token heal to `ColabRuntime.execute_code` or documenting. |
| 28 | **info** | `services/colab/execution.py` history logging | `colab_cli/history.py` | **App logs `env_keys` only (security)** — library logs full prelude with values. App deliberately diverges to avoid secrets in history. | Documented divergence; consider adding `log_env_values=False` option to library. |
| 29 | **low** | `services/colab/terminal_client.py:97-144` (`_refresh_cached_credentials`) | `colab_cli/common.py:86-112` (`State.get_session`) | **Terminal client re-reads session for token refresh** — duplicates `load_session_fresh` logic. | Call `State().get_session(session_name)` to get fresh token. |
| 30 | **info** | `colab_cli/commands/run.py` (`colab run`) | *No app equivalent* | **Library has `colab run` for shebang one-shot execution** — app doesn't expose this. | Could add `colab run` support to GUI for script execution. |

---

## Summary

### Critical/High Issues (Must Fix)
1. **Singleton bypass** (#24, #25): App creates new `State()` per call instead of using `colab_cli.common.state` singleton — causes redundant auth, token loads, race conditions.
2. **Full command reimplementation** (#4, #5, #8, #9, #10, #13): App duplicates `colab new`, `colab sessions`, `colab stop`, `colab restart-kernel`, `colab exec`, `colab ls/upload/download/rm` logic instead of calling library commands.
3. **Auth flow duplication** (#1, #2, #3): App reimplements OAuth device flow, token exchange, and validation that library already provides via `get_credentials()`.

### Medium Issues (Should Fix)
4. **Token heal pattern** (#12): Custom `_run_with_token_heal` wrapper; should use `load_session_fresh` / `State.get_session`.
5. **Drive auth hook duplication** (#11): App and library have nearly identical `drivefs_hook`; app's retry loop is better.
6. **Env var parsing** (#23): Duplicated to avoid `termios` import; should be extracted to shared module.
7. **Terminal protocol difference** (#18, #19): App uses PTY (`/terminals/websocket`) vs library's raw TTY (`/colab/tty`). Different capabilities.

### Low/Info
8. **Folder download** (#14), **text file helpers** (#22): Valid app extensions not in library.
9. **Usage wrapper** (#20): Reasonable GUI-layer additions.
10. **`colab run`** (#30): Library feature not exposed in app.

---

## Recommendations

1. **Adopt the singleton `state`** from `colab_cli.common` throughout `services/colab/`.
2. **Replace reimplemented commands** with calls to `colab_cli.commands.*` functions or direct `Client`/`ColabRuntime`/`ContentsClient` usage with `state.get_session()`.
3. **Extract shared utilities** (env parsing, Drive auth hook, hardware mapping) to a common module in the library.
4. **Contribute improvements upstream**: 503 handling for high_mem, execution 404 retry with token heal, Drive auth retry loop.
5. **Document PTY vs TTY terminal difference** — app's approach is more capable for interactive use.