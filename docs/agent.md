# The agent

## Why CodeAct

A tender document can run to hundreds of pages. Pushing all of it into the LLM
context is expensive, often impossible, and mostly wasted — the answer usually
lives in two paragraphs somewhere in the middle.

So the document is never sent to the model. It sits as `document.md` in a
sandbox workspace, and the model gets a Python interpreter instead. It writes
code to find what it needs: read the file, grep for a heading, slice a range of
lines, count rows in a table. Only the printed output comes back into the
context.

The model sees, at the start of a turn:

- the system prompt (`api/app/core/agent/prompts.py`)
- a document description: filename, character count, and the **first 30 lines**
- the conversation history
- the current question

## The loop

`CodeActAgent.run()` in `api/app/core/agent/codeact.py`:

```
messages = [system, document_context, *history, question]

repeat up to max_steps:
    text = llm.complete(messages)
    code = extract_code(text)          # first ```python block

    if code is None:
        return text                    # this is the final answer

    result = executor(code)            # runs in the sandbox
    record the step
    messages += [assistant: text, user: observation(result)]

# fell out of the loop: max_steps reached
return last text, stripped of code blocks, with a "not finished" note appended
```

Two properties matter:

**The question is always the last message.** History comes before it, and the
question is appended once, by the agent. `ChatService` snapshots the history
*before* storing the new user message, precisely so it does not appear twice.
`api/tests/test_multi_turn.py` asserts `contents.count(question) == 1`.

**A failed code run is data, not an error.** A traceback in stderr goes into the
observation and the model fixes its own code on the next step. Only
infrastructure failures — the LLM being unreachable, the sandbox being down —
propagate as exceptions.

### Observation truncation

`build_observation` truncates stdout and stderr at `OBSERVATION_MAX_CHARS`
(6000). Without it, one careless `print(open('document.md').read())` puts the
whole document into the next prompt; the provider answers 400, the three
retries turn that into a 502, and the agent cannot recover because the failure
is not in its own stderr.

### Hitting the step limit

At `AGENT_MAX_STEPS` (default 8) the agent stops and answers with whatever it
has, with a note that the investigation is incomplete. It never raises.

## The sandbox session

### The rule

**A sandbox session is a cache. Postgres is the source of truth.**

Everything needed to rebuild a session — the markdown artifact and the full
conversation — lives in the database. The session on python-vm only holds
Python state: variables, imports, a loaded DataFrame.

This is what makes the lifecycle simple: there is no need to know when a
conversation "ends".

### Lifecycle

`SessionResolver` (`api/app/core/sandbox/resolver.py`):

| Situation | What happens |
|---|---|
| `conversation.sandbox_session_id` is null | Create a session, upload `document.md`, store the id |
| The id exists | Reuse it — variables from earlier turns are still there |
| `execute` returns 404 (python-vm reaped it) | Create a new session, re-upload, retry **exactly once** |
| Retry also fails | Raise; the route maps it to 503 |

python-vm reaps sessions idle for longer than
`PYTHON_VM_SESSION_IDLE_TIMEOUT_SECONDS` (default 1800) and caps concurrency at
`max_concurrent_sessions` (default 10). Neither number is configured from this
project — they belong to the sandbox.

The user only notices a re-attach as a slightly slower turn. Do note that
Python state is genuinely lost: the model may hit a `NameError` and rebuild
what it needs, which costs a step.

### Closing a session deliberately

Only two places do it, both via `SessionResolver.reset`:

- `POST /conversations/{id}/reset-sandbox` — the "Reset phiên phân tích" button
- `DELETE /conversations/{id}`

Delete treats a failure to close as non-fatal: the conversation is removed
regardless, and an orphaned session is collected by the reaper. Blocking a
delete because the sandbox is down would fail exactly when a user most wants to
clean up.

## Failure handling in a turn

`ChatService.answer` is written around one question: what survives if this
turn dies halfway?

| Failure | Outcome |
|---|---|
| Code raises in the sandbox | Not a failure — stderr becomes the observation |
| Code times out | Same, plus a note in the observation |
| Session was reaped | Recreated, retried once |
| Sandbox out of slots | 503 |
| Sandbox unreachable | 503 |
| LLM out of retries | 502 |
| Document has no markdown artifact | 409 |
| Step limit reached | 200, with the "not finished" note |

When the agent raises mid-turn, three things must still hold, and each has a
test:

1. **The user's question is already stored.** It is committed before the agent
   is called at all.
2. **The steps that ran are kept.** The agent appends to a caller-owned
   `steps_sink` as each step finishes, so `ChatService` can persist them even
   though `run()` never returned.
3. **No orphaned user message.** An assistant message recording the failure is
   written alongside. Otherwise `build_history()` would return two user
   messages in a row for every later turn — permanently, since nothing deletes
   messages.

There is also a `finally` block that commits the sandbox session id. Without
it, a session created on step 1 would be forgotten by Postgres when the request
rolled back, while still being alive on python-vm — an orphan holding a slot.

## Where to tune behaviour

| What | Where |
|---|---|
| The agent's instructions | `SYSTEM_PROMPT` in `prompts.py` |
| How much of the document is previewed | `DOCUMENT_HEAD_LINES` in `chat_service.py` |
| Observation size cap | `OBSERVATION_MAX_CHARS` in `prompts.py` |
| Maximum steps per turn | `AGENT_MAX_STEPS` env var |
| Per-execution timeout | `SANDBOX_TIMEOUT_SECONDS` env var |

The prompt text is Vietnamese on purpose: it is runtime data for a
Vietnamese-speaking audience, not source documentation.
