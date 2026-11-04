# Audit: AI Libraries (kani, openai, httpx, tiktoken) — since v2.1.2

**Baseline:** tag `v2.1.2` (50fe98b) → HEAD `76a9d4b` (squashed 61 commits)  
**Source of truth:** `/home/maikel/Desktop/kiri-apps/CollabShell/.venv/lib/python3.14/site-packages/`  
**Scope:** `kani 1.10.0`, `openai 2.54.0`, `httpx 0.28.1`, `tiktoken 0.14.0`, plus `pydantic 2.14.1`, `anyio 4.15.1`, `rich 15.0.0`  
**App files audited:** `src/services/kani_backend.py`, `src/services/ai_service.py`, `src/services/ai_tools.py`, `src/services/reasoning.py`, `src/services/ai_quick.py`, `src/services/cell_ai.py`, `src/services/model_catalog.py`, `src/services/conversation_service.py`, `src/services/ai_credits.py`

---

## 1. kani API Reference (v1.10.0)

### 1.1 Core Classes & Signatures

#### `kani.Kani` — Main agent class (`kani/kani.py:28`)
```python
class Kani:
    def __init__(
        self,
        engine: BaseEngine,
        system_prompt: str = None,
        always_included_messages: list[ChatMessage] = None,
        desired_response_tokens: int = None,
        chat_history: list[ChatMessage] = None,
        functions: list[AIFunction] = None,
        retry_attempts: int = 1,
    ):
```

**Key attributes** (all mutable after init):
- `engine: BaseEngine` — the LM engine
- `system_prompt: str | None` — system prompt (not in `chat_history`)
- `always_included_messages: list[ChatMessage]` — prefix messages (includes system)
- `chat_history: list[ChatMessage]` — conversation history (excludes system/always)
- `functions: dict[str, AIFunction]` — registered functions (name → AIFunction)
- `retry_attempts: int` — how many times model may retry failed tool calls
- `desired_response_tokens: int` — min space to leave for response (default: min(context//10, 8192))
- `max_context_size: int` — from engine
- `lock: asyncio.Lock` — prevents concurrent rounds

**Entry points** (`kani/kani.py:241-360`):
```python
async def chat_round(self, query: QueryType, **kwargs) -> ChatMessage
async def chat_round_str(self, query: QueryType, **kwargs) -> str
def chat_round_stream(self, query: QueryType, **kwargs) -> StreamManager
async def full_round(self, query: QueryType, *, max_function_rounds: int = None, **kwargs) -> AsyncIterable[ChatMessage]
async def full_round_str(self, query: QueryType, message_formatter: Callable[[ChatMessage], str|None] = assistant_message_contents, *, max_function_rounds: int = None, **kwargs) -> AsyncIterable[str]
async def full_round_stream(self, query: QueryType, *, max_function_rounds: int = None, **kwargs) -> AsyncIterable[StreamManager]
```

**Lower-level methods** (`kani/kani.py:374-421`):
```python
async def get_model_completion(self, include_functions: bool = True, **kwargs) -> BaseCompletion
async def get_model_stream(self, include_functions: bool = True, **kwargs) -> AsyncIterable[str | BaseCompletion]
async def get_prompt(self, include_functions: bool = True, **kwargs) -> list[ChatMessage]
async def prompt_token_len(self, messages: list[ChatMessage], functions: list[AIFunction] | None = None, **kwargs) -> int
def get_enabled_functions(self) -> list[AIFunction]
```

**Function calling hooks** (overridable, `kani/kani.py:555-651`):
```python
async def do_function_call(self, call: FunctionCall, tool_call_id: str = None) -> FunctionCallResult
async def handle_function_call_exception(self, call: FunctionCall, err: FunctionCallException, attempt: int, tool_call_id: str = None) -> ExceptionHandleResult
async def add_completion_to_history(self, completion: BaseCompletion) -> ChatMessage
async def add_to_history(self, message: ChatMessage)
```

#### `kani.AIFunction` — Function wrapper (`kani/ai_function.py:15`)
```python
class AIFunction:
    def __init__(
        self,
        inner: Callable,
        after: ChatRole = ChatRole.ASSISTANT,
        name: str | None = None,
        desc: str | None = None,
        auto_retry: bool = True,
        json_schema: dict | None = None,
        auto_truncate: int | None = None,
        enabled: bool = True,
    ):
```
- `inner` is wrapped with `pydantic.validate_call` (line 51)
- `json_schema` auto-generated from signature via `create_json_schema()` (line 115) unless overridden
- `auto_truncate` truncates function response to N chars using paragraph-aware algorithm (`kani/kani.py:706-731`)

#### `@kani.ai_function` — Decorator (`kani/ai_function.py:134`)
```python
def ai_function(
    func=None,
    *,
    after: ChatRole = ChatRole.ASSISTANT,
    name: str | None = None,
    desc: str | None = None,
    auto_retry: bool = True,
    json_schema: dict | None = None,
    auto_truncate: int | None = None,
    enabled: bool = True,
):
```
Attaches `__ai_function__` dict to method; `Kani.__init__` discovers and registers them (lines 123-140).

#### `kani.engines.base.BaseEngine` — Engine interface (`kani/engines/base.py:56`)
```python
class BaseEngine(abc.ABC):
    max_context_size: int
    
    def prompt_len(self, messages: list[ChatMessage], functions: list[AIFunction] | None = None, **kwargs) -> int | Awaitable[int]: ...
    
    async def predict(self, messages: list[ChatMessage], functions: list[AIFunction] | None = None, **hyperparams) -> BaseCompletion: ...
    
    async def stream(self, messages: list[ChatMessage], functions: list[AIFunction] | None = None, **hyperparams) -> AsyncIterable[str | BaseCompletion]: ...
    
    async def close(self): ...
    
    disable_function_calling_kwargs = {"include_functions": False}
```

#### `kani.engines.openai.OpenAIEngine` — OpenAI-compatible engine (`kani/engines/openai/engine.py:34`)
```python
class OpenAIEngine(TokenCached, BaseEngine):
    def __init__(
        self,
        api_key: str = None,
        model: str = "gpt-4.1-nano",
        max_context_size: int = None,
        *,
        api_type: Literal["chat_completions", "responses"] = None,
        organization: str = None,
        retry: int = 5,
        api_base: str = "https://api.openai.com/v1",
        headers: dict = None,
        client: OpenAIClient = None,
        tokenizer=None,
        **hyperparams,
    ):
```
- `api_type` selects Chat Completions vs Responses API (auto-detected by model prefix, `model_constants.py:44-60`)
- `tokenizer` injected for token counting (property at line 120-133)
- `hyperparams` passed to every `create_chat_completion`/`responses.create` call
- `disable_function_calling_kwargs = {"tool_choice": "none"}` (line 49)

#### `kani.models` — Message types (`kani/models.py:35-331`)
```python
class ChatRole(Enum): SYSTEM, USER, ASSISTANT, FUNCTION
class FunctionCall(BaseModel): name: str; arguments: str (JSON); .kwargs -> dict
class ToolCall(BaseModel): id: str; type: str; function: FunctionCall; .from_function(), .from_function_call()
class ChatMessage(BaseModel):
    role: ChatRole
    content: str | list[MessagePart|str] | None
    name: str | None
    tool_call_id: str | None
    tool_calls: list[ToolCall] | None
    is_tool_call_error: bool | None
    extra: dict
    
    .text -> str | None (concatenates parts)
    .parts -> list[MessagePart|str]
    .function_call -> FunctionCall | None (compat)
    @classmethod system/user/assistant/function(...) -> ChatMessage
    .copy_with(**new_values) -> ChatMessage (handles text/parts/content and tool_calls/function_call)
```

#### `kani.parts.ReasoningPart` — Hidden reasoning (`kani/parts/reasoning.py:4`)
```python
class ReasoningPart(MessagePart):
    content: str
    def __str__(self) -> str: return ""  # hidden by default
```
OpenAI-specific: `kani.engines.openai.parts.OpenAIReasoningPart` adds `id: str`, `encrypted_content: str` (`kani/engines/openai/parts.py:17`).

#### `kani.streaming.StreamManager` — Stream consumer (`kani/streaming.py:9`)
```python
class StreamManager:
    def __init__(self, stream_iter: AsyncIterable[str|BaseCompletion], role: ChatRole, *, after=None, lock: asyncio.Lock=None):
    role: ChatRole  # available immediately
    def __aiter__(self) -> AsyncIterable[str]: ...  # yields tokens
    async def completion(self) -> BaseCompletion: ...  # await final completion
    async def message(self) -> ChatMessage: ...  # await final message
    def __await__(self): return self.message().__await__()  # await stream = await message
```

#### `kani.streaming.DummyStream` — Tool result stream (`kani/streaming.py:152`)
```python
class DummyStream(StreamManager):
    def __init__(self, message: ChatMessage): ...
    async def message(self) -> ChatMessage: return self._message
```
Yielded by `full_round_stream` for FUNCTION messages (tool results).

---

### 1.2 Streaming Protocol

`full_round_stream` yields **alternating**:
1. `StreamManager` (role=ASSISTANT) — model token stream
2. `DummyStream` (role=FUNCTION) — tool result (already executed)

**Correct consumption pattern** (`kani/kani.py:346-360`):
```python
async for stream in ai.full_round_stream(query):
    # stream.role tells you ASSISTANT vs FUNCTION before iterating
    async for token in stream:
        print(token, end="")
    msg = await stream.message()  # or await stream
```

**Key behavior** (`kani/streaming.py:104-108`): If engine stream ends without yielding `BaseCompletion`, `StreamManager` constructs one from concatenated tokens.

---

### 1.3 Token Accounting

- `BaseCompletion.prompt_tokens` / `completion_tokens` — from engine (may be `None`)
- `Kani.prompt_token_len(messages, functions)` — preferred way to count (`kani/kani.py:363`)
- `OpenAIEngine.tokenizer` — lazy-loaded tiktoken (`kani/engines/openai/engine.py:120-133`)
- `OpenAIEngine.message_len()` — per-message counting with multimodal support (`kani/engines/openai/engine.py:135-169`)
- `OpenAIEngine.function_token_reserve()` — function schema token estimate (`kani/engines/openai/engine.py:171-180`)
- `OpenAIEngine.prompt_len()` — uses Responses API `input_tokens.count` if available, else sums `message_len` + `function_token_reserve` (`kani/engines/openai/engine.py:422-439`)

---

### 1.4 Reasoning/Thinking Support

- **Responses API**: `include=["reasoning.encrypted_content"]` auto-added (`engine.py:265-267`)
- **Streaming**: `response.output_text.delta` events yield text; reasoning captured via `ThoughtTap` (app's `reasoning.py`)
- **kani-native**: `ReasoningPart` in message content; `OpenAIReasoningPart` includes `encrypted_content` for multi-turn
- **No `reasoning_effort` param in kani** — passed as hyperparam to engine (`run_turn` passes via `**kwargs`)

---

## 2. App vs kani API — Gap Analysis

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 1 | critical | `kani_backend.py:484-493` | `kani/kani.py:67-76` | `CollabShellKani` passes `retry_attempts=1` but `Kani.__init__` default is 1. The comment says "one attempt only" but this is already the default. No bug, but misleading comment. | Remove comment or clarify: default is 1, setting explicitly is fine. |
| 2 | high | `kani_backend.py:504-518` | `kani/kani.py:289-312` | `full_round_stream` called with `max_tokens=max_tokens` but kani's `full_round_stream` does NOT accept `max_tokens` — it's passed as `**kwargs` to engine. Works only because `OpenAIEngine.predict/stream` accept `max_tokens` in hyperparams. | Document that `max_tokens` is engine-specific hyperparam, not kani API. |
| 3 | high | `kani_backend.py:514-517` | `kani/engines/openai/engine.py:51-59` | `reasoning_effort` passed as kwarg but only works for Responses API models. For Chat Completions API it's ignored silently. No validation that model supports it. | Check `engine.openai_api_type == "responses"` before passing, or let engine ignore unknown params. |
| 4 | high | `kani_backend.py:547` | `kani/kani.py:115-140` | `kani.functions = {}` to strip tools mid-stream. Direct dict mutation bypasses `get_enabled_functions()` and function registration logic. | Use `kani.functions.clear()` or rebuild Kani without functions. Better: pass `include_functions=False` in kwargs (but that's per-call, not persistent). |
| 5 | high | `kani_backend.py:556-582` | `kani/streaming.py:117-149` | Manual `manager.__aiter__()` + `wait_for` on first token. Bypasses `StreamManager.__aiter__` lock and `_awaited` check. If stream already iterated, `__aiter__` raises `RuntimeError`. | Use `async for token in manager:` directly. For TTFB timeout, wrap the outer `async for manager in ...` loop. |
| 6 | high | `kani_backend.py:589` | `kani/streaming.py:146-149` | `await manager.message()` after manual iteration. If stream was abandoned mid-iteration (`break`), `_finished` event never set → `message()` hangs forever. The code detects this with `stopped_mid_stream` flag and breaks before `message()` — correct but fragile. | Use `async for token in manager:` pattern; `manager.message()` only after loop completes naturally. |
| 7 | medium | `kani_backend.py:446` | `kani/kani.py:109` | `history_msgs = list(base_history)` copies history for each candidate. But `Kani.__init__` stores reference: `self.chat_history = chat_history or []`. If caller mutates `base_history` later, all candidates see changes. | Copy explicitly: `chat_history=list(base_history)` (already done). OK. |
| 8 | medium | `kani_backend.py:609-611` | `kani/kani.py:109` | `history_msgs = list(kani.chat_history)` carries forward tool results to next candidate. Correct pattern. | No change needed. |
| 9 | medium | `kani_backend.py:484-493` | `kani/kani.py:67-76` | `CollabShellKani` created per-candidate with same `system_prompt` and `chat_history`. Each gets own `lock` — correct isolation. | No change needed. |
| 10 | medium | `ai_tools.py:772-805` | `kani/ai_function.py:79-124` | `tool_specs` derives JSON schema from function signatures using `inspect.signature(fn, eval_str=True)` and custom `_param_schema`. This **duplicates** kani's `AIFunction.create_json_schema()` which uses `pydantic.validate_call` + `typing.get_type_hints`. Two schema generators can drift. | Use `@ai_function` decorator on tool functions and let kani generate schemas. Or pass `json_schema=spec.parameters` to `AIFunction` (current `build_functions` does this at line 229) but derive schema FROM kani's generator, not hand-rolled. |
| 11 | medium | `ai_tools.py:754-770` | `kani/ai_function.py:114-124` | `_param_schema` handles `Annotated` + `AIParam` but kani's `get_aiparam` does the same (`ai_function.py:196-204`). Duplicate logic. | Use kani's `AIFunction.create_json_schema()` as single source of truth. |
| 12 | low | `kani_backend.py:90-115` | `kani/engines/openai/engine.py:120-133` | `_CountingTokenizer` replaces tiktoken with word-split heuristic. Under-counts code (BPE splits below word boundaries). kani falls back to `o200k_base` if model tokenizer missing (`engine.py:128-132`). | Use real tiktoken; if cold-cache download stalls, pre-warm at startup: `tiktoken.encoding_for_model(model)` in background. |
| 13 | low | `kani_backend.py:335-342` | `kani/engines/openai/engine.py:110-116` | `_build_engine` creates new `openai.AsyncOpenAI` + `httpx.AsyncClient` per candidate. No connection pooling across candidates. | Share single `httpx.AsyncClient` with `limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)` across all candidates. Pass `http_client=shared_client` to `AsyncOpenAI`. |
| 14 | low | `kani_backend.py:333-334` | `kani/engines/openai/engine.py:56-60` | `timeout = httpx.Timeout(CANDIDATE_READ_S, connect=4.0)` but `OpenAIEngine` has its own `retry=5` (line 59). App sets `max_retries=0` on client (line 338) to let candidate walk handle retries. Dual retry config: SDK retry disabled, but engine's `retry=5` still in effect? | `OpenAIEngine.__init__` `retry` param controls `AsyncOpenAI(max_retries=retry)`. App passes `client` with `max_retries=0`, so engine's `retry` is ignored. OK but confusing. |
| 15 | info | `ai_service.py:136-234` | `kani/kani.py:289-312` | `run_turn` wrapper duplicates `max_rounds` default (`MAX_TOOL_ROUNDS=6`) which matches kani's `max_function_rounds` default (unlimited). App's default is more restrictive. | Document the difference; kani default is unlimited, app caps at 6. |
| 16 | info | `ai_credits.py:156-160` | `kani/streaming.py:117-149` | `_model_step_started`/`_model_step_finished` callbacks track model steps for billing. `on_model_step` called per `StreamManager` yield (ASSISTANT role only). Correct: tool rounds (FUNCTION role) not billed. | No change needed. |
| 17 | info | `reasoning.py:123-165` | `kani/engines/openai/engine.py:308-373` | `ThoughtTapTransport` tees SSE bytes to extract reasoning. Works for both Chat Completions and Responses API streams. kani's `OpenAIEngine._stream_chat_completions` yields `delta.content` only (`engine.py:342-344`); reasoning deltas discarded. App's tap captures them from raw bytes. | Correct workaround for kani limitation. |

---

## 3. openai / httpx / tiktoken Usage Verification

### 3.1 openai SDK Usage

| Location | Usage | Assessment |
|----------|-------|------------|
| `kani_backend.py:335-342` | `openai.AsyncOpenAI(api_key="any", base_url=base, max_retries=0, timeout=timeout, http_client=custom_client)` | ✅ Correct. `api_key="any"` accepted by router. `max_retries=0` delegates to candidate walk. Custom `http_client` for reasoning tap. |
| `kani_backend.py:333-334` | `httpx.Timeout(CANDIDATE_READ_S, connect=4.0)` | ✅ Correct per-candidate timeout. Connect timeout 4s, read timeout 20s. |
| `reasoning.py:220-224` | `httpx.AsyncClient(transport=ThoughtTapTransport(tap), timeout=timeout, headers={"User-Agent": USER_AGENT})` | ✅ Custom transport tees SSE. `max_retries` not forwarded (httpx doesn't support it). |
| `model_catalog.py:334-335` | `_http_client(timeout=timeout)` from `components.model_picker` | Need to verify `_http_client` implementation. |
| `router_engine.py` | `httpx.AsyncClient` for engine download | Separate concern (router binary fetch). |

**Base URL handling**: App resolves router URL once per turn (`ai_service.py:179`), passes to `kani_backend.run_turn`, which passes to `_build_engine`. `OpenAIEngine` receives `base_url` as `api_base` param (line 60 in engine.py). **Correct** — single resolution per turn.

**Streaming SSE parsing**: kani's `OpenAIEngine._stream_chat_completions` uses `stream=True, stream_options={"include_usage": True}` (engine.py:319-320). Iterates `async for chunk in stream:` (line 330). Parses `delta.content` and `delta.tool_calls` (lines 342-356). **Correct** per OpenAI SDK.

**Reasoning capture**: App's `ThoughtTapTransport` intercepts raw SSE frames (`text/event-stream`), decodes JSON, extracts `reasoning_content`/`reasoning`/`reasoning_details` from `delta` or `message` (reasoning.py:70-96). Passes original bytes through unchanged. **Correct** — kani sees unmodified stream.

### 3.2 tiktoken Usage

| Location | Usage | Assessment |
|----------|-------|------------|
| `kani_backend.py:90-115` | `_CountingTokenizer` — word-split heuristic, **replaces** tiktoken | ⚠️ Intentional workaround for cold-cache download stall. Under-counts code tokens. kani's `OpenAIEngine.tokenizer` property (engine.py:120-133) loads `tiktoken.encoding_for_model(model)` lazily on first `message_len`. |
| kani internal | `tiktoken.encoding_for_model(model)` → falls back to `o200k_base` (engine.py:126-132) | ✅ Correct fallback. |
| kani internal | `tiktoken.get_encoding("o200k_base")` for unknown models | ✅ Correct. |

**Encoding names**: kani uses model-specific encodings via `encoding_for_model`. For `gpt-4.1-nano` (default), uses `o200k_base`. App's `_CountingTokenizer` doesn't use tiktoken at all.

**Recommendation**: Pre-warm tiktoken at app startup for known models to avoid cold-cache stall:
```python
import tiktoken
for model in KNOWN_MODELS:
    try:
        tiktoken.encoding_for_model(model)
    except KeyError:
        tiktoken.get_encoding("o200k_base")
```

---

## 4. kani Options Not Exposed by App

The following kani/public API options are **not exposed** to users or configurable via Settings:

| kani Feature | Location | App Status |
|--------------|----------|------------|
| `Kani.desired_response_tokens` | `kani/kani.py:72` | Hardcoded to engine default (min(context//10, 8192)). Not tunable. |
| `Kani.always_included_messages` | `kani/kani.py:71` | Not used. Could inject few-shot examples or persistent context. |
| `Kani.retry_attempts` | `kani/kani.py:75` | Fixed at 1 in `CollabShellKani` init. Not user-configurable. |
| `AIFunction.auto_retry` | `kani/ai_function.py:35` | Default `True`. Not exposed per-tool. |
| `AIFunction.auto_truncate` | `kani/ai_function.py:39` | Set globally via `TOOL_OUTPUT_CAP=12000` in `build_functions`. Not per-tool. |
| `AIFunction.enabled` | `kani/ai_function.py:46` | Not used. Could dynamically disable tools. |
| `AIFunction.after` (next actor) | `kani/ai_function.py:31` | Default `ASSISTANT`. Not exposed. |
| `AIFunction.json_schema` override | `kani/ai_function.py:37` | App passes hand-rolled schema via `build_functions`. Could override kani's auto-generated. |
| `OpenAIEngine.api_type` | `kani/engines/openai/engine.py:57` | Hardcoded to `"chat_completions"` in `_build_engine` (line 347). Responses API not selectable. |
| `OpenAIEngine.organization` | `kani/engines/openai/engine.py:58` | Not used. |
| `OpenAIEngine.headers` | `kani/engines/openai/engine.py:61` | Only `User-Agent` set via custom httpx client. |
| `OpenAIEngine.tokenizer` injection | `kani/engines/openai/engine.py:63` | App injects `_CountingTokenizer`. Real tiktoken not used. |
| `OpenAIEngine.hyperparams` | `kani/engines/openai/engine.py:86` | Only `max_tokens`, `reasoning_effort` passed per-turn. `temperature`, `top_p`, `stop`, `presence_penalty`, `frequency_penalty`, `logit_bias`, `response_format`, `seed`, `logprobs`, `top_logprobs` not exposed. |
| `BaseEngine.disable_function_calling_kwargs` | `kani/engines/base.py:138` | Default `{"include_functions": False}`. OpenAIEngine overrides to `{"tool_choice": "none"}`. Not customizable. |
| `Kani.save()` / `Kani.load()` | `kani/kani.py:675-698` | Not used. App has own `conversation_service`. |
| `PromptPipeline` customization | `kani/prompts/pipeline.py` | Not used. Could customize message formatting/token counting. |
| `MessagePart` subclasses | `kani/parts/__init__.py` | Only `ReasoningPart` used via OpenAI engine. Custom parts not supported. |
| `Kani.get_prompt()` override | `kani/kani.py:424` | Not overridden. Custom context management not possible. |

---

## 5. Additional Findings

### 5.1 Tool Schema Generation — Hand-Maintained Duplication

`ai_tools.py:754-805` reimplements JSON schema generation from Python signatures:
- `_param_schema` handles `Annotated[..., AIParam]`, arrays, nested types
- `_json_type` maps Python types to JSON schema types
- `_unwrap` strips `Annotated` wrapper

**kani's built-in** (`ai_function.py:79-124`):
- Uses `pydantic.validate_call` + `typing.get_type_hints(include_extras=True)`
- `get_aiparam` extracts `AIParam` from `Annotated`
- `create_json_schema` builds full schema with descriptions

**Risk**: Two implementations can drift. Example: `write_cells` parameter `cells: Annotated[list[dict], AIParam(...)]` — app's `_param_schema` must correctly handle `list[dict]` → `array` with `items: {type: object}`. kani's does this automatically via pydantic.

**Evidence of past drift**: `ai_tools.py:723-724` comment: "A missing `items` raises KeyError, which took down the first turn that offered `write_cells` — it crashed while sizing the prompt."

### 5.2 Streaming Handled Incorrectly in `run_turn`

`kani_backend.py:556-588` manually drives `StreamManager`:
```python
stream = manager.__aiter__()
while True:
    chunk = await stream.__anext__()  # or wait_for first token
    if isinstance(chunk, BaseCompletion): continue
    ...
```
**Problems**:
1. Bypasses `StreamManager.__aiter__` lock (`kani/streaming.py:127`)
2. Bypasses `_awaited` check — if code ever iterates twice, `RuntimeError`
3. Manual `wait_for` on first token duplicates kani's internal streaming
4. `BaseCompletion` chunks filtered but `message()` still awaited after break — hang risk

**Correct pattern** (per `kani/kani.py:346-360`):
```python
async for manager in kani.full_round_stream(...):
    async for token in manager:  # uses __aiter__ correctly
        on_token(token)
    msg = await manager.message()
```

### 5.3 Reasoning/Thinking Depth — Not Actually Supported

`kani_backend.py:514-517` passes `reasoning_effort`:
```python
**({"reasoning_effort": _thinking_depth()} if _thinking_depth() else {})
```

But:
1. Only works for **Responses API** models (`api_type="responses"`)
2. `_build_engine` hardcodes `api_type="chat_completions"` (line 347)
3. Router's catalog may return models supporting Responses API, but engine forces Chat Completions
4. `reasoning_effort` silently ignored by Chat Completions API

**Fix**: Detect model's API type from catalog (`endpoint_type` or model prefix per `model_constants.py:44-60`) and set `api_type` accordingly.

### 5.4 Token/Credit Accounting — Model Steps vs Tool Rounds

`ai_credits.py:85-92` floor rule:
```python
def charged_steps(model_steps: int, text: str) -> int:
    delivered = bool((text or "").strip())
    return max(model_steps, 1) if delivered else model_steps
```

`kani_backend.py:552` increments `model_steps` **only for ASSISTANT role streams**:
```python
if manager.role is not ChatRole.ASSISTANT:
    continue  # tool result, not billed
model_steps += 1
```

**Correct**: kani yields `StreamManager` (ASSISTANT) and `DummyStream` (FUNCTION). Only ASSISTANT rounds billed. Tool execution happens inside kani's `asyncio.gather` (kani/kani.py:206) — no separate model call.

### 5.5 Timeouts/Retries — Dual Configuration

| Layer | Config | Value |
|-------|--------|-------|
| `httpx.Timeout` | `kani_backend.py:333` | `Timeout(20.0, connect=4.0)` |
| `openai.AsyncOpenAI` | `kani_backend.py:338` | `max_retries=0` |
| `OpenAIEngine` | `engine.py:59` | `retry=5` (ignored when `client` passed) |
| Candidate TTFB | `kani_backend.py:63` | `CANDIDATE_TTFB_S = 12.0` |
| Candidate read | `kani_backend.py:64` | `CANDIDATE_READ_S = 20.0` |
| Turn wall-clock | `ai_service.py:22` | `TURN_TIMEOUT_SEC = 240.0` |

**Issue**: `OpenAIEngine.retry=5` is ignored because app passes custom `client` with `max_retries=0`. But if `client` not passed, engine would retry 5x with exponential backoff (OpenAI SDK default). App's candidate walk IS the retry logic — correct to disable SDK retries.

### 5.6 Model Selection — Hardcoded Defaults

- `OpenAIEngine` default model: `"gpt-4.1-nano"` (engine.py:54)
- `_build_engine` receives `model` from candidate list (catalog-driven)
- `api_type` hardcoded to `"chat_completions"` (line 347)
- `max_context_size` hardcoded to `DEFAULT_CONTEXT = 131072` (line 57, 348)

**Not exposed**: User cannot choose Responses API models (o1, o3, gpt-5) which require `api_type="responses"`. Model catalog has this info (`endpoint_type` field) but `_build_engine` ignores it.

---

## 6. Summary: Critical/High Priority Fixes

| # | Fix | Files |
|---|-----|-------|
| 1 | Replace manual `StreamManager` iteration with `async for token in manager:` | `kani_backend.py:556-588` |
| 2 | Derive tool schemas from kani's `AIFunction.create_json_schema()` instead of hand-rolled | `ai_tools.py:754-805`, `kani_backend.py:229` |
| 3 | Set `api_type` per-model based on catalog (`endpoint_type` or prefix match) | `kani_backend.py:347`, `model_catalog.py` |
| 4 | Pre-warm tiktoken at startup to avoid cold-cache stall; remove `_CountingTokenizer` | `kani_backend.py:90-115`, app startup |
| 5 | Share `httpx.AsyncClient` across candidates for connection pooling | `kani_backend.py:335-342` |
| 6 | Expose `temperature`, `top_p`, `max_tokens` (already), `reasoning_effort` (Responses only) via Settings | `ai_service.py`, `kani_backend.py` |
| 7 | Validate `reasoning_effort` only passed for Responses API models | `kani_backend.py:514-517` |

---

## 7. Files with No Issues Found

- `conversation_service.py` — Pure persistence, no AI library usage
- `ai_quick.py` / `cell_ai.py` — Thin wrappers over `ai_credits`/`ai_service`
- `model_catalog.py` — Router catalog logic, no direct kani/openai usage
- `ai_credits.py` — Metering logic, correct floor rule implementation

---

*Generated by audit of `.venv/lib/python3.14/site-packages/kani/` (v1.10.0) and app source at HEAD `76a9d4b`.*
