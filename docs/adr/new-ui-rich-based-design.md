# Aegis SWR — New Terminal UI Design

**Status:** Design proposal  
**Scope:** `src/aegis_swr/views/rich_view.py` — replaces `RichView` with `WarRoomView`  
**Rich version required:** 15.x (already a dependency; uses `rich.layout.Layout`)

---

## 1. Screen Layout

The live investigation occupies the full terminal. Rich's `Layout` divides it into three named regions, held inside a `Live` block that refreshes at 12 fps:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  AEGIS SWR  Synthetic War Room          CrashUi.dmp  crash_dump      0:01:42  R2   │
├─────────────────────────────────────────┬───────────────────────────────────────────┤
│                                         │  FORENSIC AGENTS                Round 2  │
│  EVIDENCE STREAM                        │ ┌────────────────────────────────────────┐│
│                                         │ │⠼ OS Kernel Agent  ANALYZING            ││
│  00:00  CDB extraction started…         │ │  ████████████████████░░░░  82%         ││
│  00:01  fault_class   ACCESS_VIOLATION  │ │  UAF on freed heap page — 0xC0000005   ││
│  00:01  module        ImageScope.exe    │ ├────────────────────────────────────────┤│
│  00:01  function      CImage::Load      │ │✔ Code Analyst     DONE                 ││
│  00:01  sym_coverage  92%               │ │  ███████████████████░░░░░  78%         ││
│  00:01  stack[0]  CImage::Load+0x3f     │ │  CImage::Load lacks a lifetime guard   ││
│  00:01  stack[1]  CImageView::OnPaint   │ ├────────────────────────────────────────┤│
│  00:01  stack[2]  RenderThread::Run     │ │✔ Log Historian    DONE                 ││
│  00:32  OS Kernel » UAF on freed heap   │ │  ██████████████████░░░░░░  74%         ││
│  00:51  Code Analyst » lacks guard      │ │  2 similar incidents last 30 days      ││
│  01:10  Log Historian » 2 incidents     │ ├────────────────────────────────────────┤│
│  01:29  Skeptic » timing mismatch       │ │✔ Skeptic          DONE                 ││
│  01:30  consensus R1  61%  MEDIUM       │ │  ████████████████████░░░░  85%         ││
│  01:30  threshold not reached; R2…      │ │  Confirmed timing matches render thd   ││
│  01:48  OS Kernel » confirmed UAF       │ └────────────────────────────────────────┘│
│  ▌                                      ├───────────────────────────────────────────┤
│                                         │  INVESTIGATION PROCESS                    │
│                                         │  ⠼ Skeptic Agent is stress-testing…      │
│                                         │  ████████████████████░░░  9/12   0:01:48 │
│                                         │                                           │
│                                         │  Consensus history                        │
│                                         │  R1  ████████████░░░░  61%  MEDIUM  ✗   │
│                                         │  R2  ░░░░░░░░░░░░░░░░  ──%  ──────  …   │
└─────────────────────────────────────────┴───────────────────────────────────────────┘
```

```
Layout tree
───────────
root (vertical)
  header_bar           height=1  (single line — title + incident + clock + round)
  body (horizontal, ratio fills remaining height)
    evidence            ratio=1   left half
    right (vertical)
      agents            ratio=1   top-right quarter
      process           ratio=1   bottom-right quarter
```

After conclusion the `Live` block stops. The terminal scrolls normally as the verdict panel is printed below the frozen live block.

---

## 2. Widgets

### 2.1 Header Bar

Single line, rendered by `Layout` with `size=1`.

```
  AEGIS SWR  Synthetic War Room          CrashUi.dmp  crash_dump      0:01:42  R2
```

| Field                           | Source                                          | Style                             |
|---------------------------------|-------------------------------------------------|-----------------------------------|
| `AEGIS SWR  Synthetic War Room` | static                                          | `bold cyan`                       |
| incident file name              | `InvestigationStarted.source.dump_path`         | `bold white`                      |
| mode                            | `InvestigationStarted.source.mode.value`        | `dim`                             |
| elapsed                         | `time.monotonic()` updated on every render tick | `dim`                             |
| `R2`                            | current round number                            | `bold yellow` when >1, else `dim` |

### 2.2 Evidence Stream (left half)

A scrolling chronological log. Every data point that arrives from the core gets a timestamped line appended to an internal list. On each render tick the last `max_visible` lines are shown, where `max_visible = panel_inner_height`. Because `Layout` constrains height, old lines naturally disappear off the top — a simulated scroll.

**Cursor animation:** a blinking block `▌` (alternates `▌` / ` ` at 1 Hz using `time.monotonic()`) is appended as the last line while the investigation is live. It disappears on completion.

**Line categories and styles:**

| Category       | Trigger                                                  | Example line                            | Style                               |
|----------------|----------------------------------------------------------|-----------------------------------------|-------------------------------------|
| Stage marker   | `InvestigationStarted`                                   | `00:00  CDB extraction started…`        | `dim`                               |
| Fault data     | `EvidenceExtracted` fields                               | `00:01  fault_class   ACCESS_VIOLATION` | label `dim`, value `bold magenta`   |
| Stack frame    | `EvidenceExtracted.brief["stack_frames"]`                | `00:01  stack[0]  CImage::Load+0x3f`    | `blue`                              |
| Symbol warning | `EvidenceExtracted.brief["low_symbol_coverage_warning"]` | `00:01  ⚠ low symbol coverage`          | `bold yellow`                       |
| Agent finding  | `AgentSpoke`                                             | `00:32  OS Kernel » UAF on freed heap`  | agent name `bold`, finding `italic` |
| Consensus      | `ConsensusEvaluated`                                     | `01:30  consensus R1  61%  MEDIUM`      | color from confidence level         |
| Status note    | internal                                                 | `01:30  threshold not reached; R2…`     | `dim italic`                        |

Each line is prefixed with `MM:SS` elapsed time (from investigation start).

### 2.3 Forensic Agents (right top quarter)

One sub-panel per agent, stacked vertically inside a `Panel`. Each sub-panel is separated by a thin rule. Four agents = four sub-panels of equal height.

**Per-agent row layout (3 lines per agent):**

```
⠼ OS Kernel Agent  ANALYZING                   ← line 1: spinner + name + status badge
  ████████████████████░░░░  82%                 ← line 2: confidence bar
  UAF on freed heap page — 0xC0000005           ← line 3: latest finding (truncated)
```

**Status badge states:**

| State       | Badge text  | Style         | Spinner                |
|-------------|-------------|---------------|------------------------|
| `STANDBY`   | `STANDBY`   | `dim`         | none                   |
| `ANALYZING` | `ANALYZING` | `bold cyan`   | `dots` spinner cycling |
| `DONE`      | `DONE`      | `bold green`  | `✔`                    |
| `REVIEWING` | `REVIEWING` | `bold yellow` | `dots2` spinner        |

Agent lifecycle per round:
- Start of round → all four agents set to `STANDBY`
- When the graph emits `AgentSpoke(node="os_kernel_node")` → that agent flips to `ANALYZING` at the start of their node, `DONE` on receipt (the node completes before the event arrives, so `DONE` is correct on `AgentSpoke`)
- Between events the *next* agent is inferred from `_NEXT_STATUS` and set to `ANALYZING` to keep something animated

Actually, because we only receive an event *after* an agent finishes (the LangGraph node has returned), the spinner for the *current* agent is shown between the previous `AgentSpoke` and the current one. Implementation:
- On `AgentSpoke(node=N)`: mark agent for `N` as `DONE`; set the *next* agent in sequence to `ANALYZING`
- On `ConsensusEvaluated`: set all agents back to `STANDBY` (next round will reassign)

### 2.4 Investigation Process (right bottom quarter)

Three sections stacked vertically:

**Section 1 — Waiting animation (spinner + stage bar)**

```
⠼ Skeptic Agent is stress-testing the hypothesis…
████████████████████░░░  9/12   0:01:48
```

Uses a `rich.progress.Progress` instance (same as current `RichView`) with:
- `SpinnerColumn("dots", style="cyan")`
- `TextColumn("[cyan]{task.description}")`
- `BarColumn(bar_width=26, complete_style="cyan", pulse_style="cyan")`
- `TextColumn("[dim]{task.completed}/{task.total}")`
- `TimeElapsedColumn()`

When the investigation finishes the task is advanced to `completed=total` and the bar fills solid.

**Section 2 — Consensus history**

One compact row per completed round:

```
Consensus history
R1  ████████████░░░░  61%  MEDIUM  ✗  (did not converge)
R2  ████████████████████░░  87%  HIGH  ✔  (converged)
```

`✗` in red for rounds that didn't converge; `✔` in green for the convergence round.  
Bar color follows `_conf_color`: green ≥80%, yellow ≥50%, red below.

**Section 3 — Stage log (overflow area)**

Any remaining height below sections 1 and 2 shows the last few status transitions in dim text:

```
01:30  threshold not reached — continuing to round 2
01:48  OS Kernel Agent responding…
```

---

## 3. Animation Elements

| Element                        | Mechanism                                                                                 | Location                           |
|--------------------------------|-------------------------------------------------------------------------------------------|------------------------------------|
| Spinning cursor (active agent) | `itertools.cycle(["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"])` advanced on each render tick | Forensic Agents — active agent row |
| Stage progress bar pulse       | `BarColumn(pulse_style="cyan")` — pulses while `completed < total`                        | Investigation Process section 1    |
| Blinking evidence cursor       | `▌` vs ` ` toggled by `int(elapsed) % 2`                                                  | Evidence Stream last line          |
| Elapsed clock                  | `TimeElapsedColumn()` inside `Progress`                                                   | Investigation Process section 1    |
| Header clock                   | `f"{int(elapsed)//60:02d}:{int(elapsed)%60:02d}"` formatted in `_render()`                | Header bar                         |

All animations run purely from the 12 fps `Live` refresh — no `threading.Timer`, no `asyncio.sleep` in the view.

---

## 4. Post-Conclusion Transition

When `InvestigationCompleted` or `HumanInputRequired` arrives:

1. **Fill the progress bar:** `progress.update(task_id, completed=total)` — bar goes solid.
2. **Stop the blinking cursor** in Evidence Stream — replace `▌` with a final `✔  investigation complete` line.
3. **One final render tick** to show the filled state.
4. **`live.stop()`** — the live block freezes in place. The terminal cursor drops below it.
5. **`render_verdict(report, console=console)`** is called — the verdict panel is printed below the frozen live block and scrolls the terminal upward naturally.

The result is the war-room stays visible above the verdict, giving the audience the sense that the process and its conclusion are both on screen simultaneously (until they scroll).

For HITL (deadlock): same transition but the verdict panel is printed with a red border and the `Human Input Required` notice.

---

## 5. Verdict Panel (post-conclusion)

Printed immediately after `Live` stops. Unchanged from the current `render_verdict` function, reproduced here for completeness:

```
──────────── ✔  CONSENSUS REACHED — VERDICT APPROVED BY THE PANEL ─────────────

┌──────────────────────────── Root Cause Analysis ────────────────────────────┐
│                                                                             │
│  Use-after-free: CImage::Load dereferences a bitmap buffer released by     │
│  the render thread.                                                         │
│                                                                             │
│  Confidence  █████████████████████░░░ 87%  HIGH                             │
│  Module      ImageScope.exe                                                 │
│  Function    CImage::Load                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

                          Panel Verdict
┌────────────────────────┬────────────────────────────────┬──────────────┐
│ Agent                  │ Confidence                     │ Verdict      │
├────────────────────────┼────────────────────────────────┼──────────────┤
│ OS Kernel Agent        │ ████████████████████░░░░ 82%   │ ✔ Approved   │
│ Code Analyst Agent     │ ███████████████████░░░░░ 78%   │ ✔ Approved   │
│ Log Historian Agent    │ ██████████████████░░░░░░ 74%   │ ✔ Approved   │
│ Skeptic Agent          │ ████████████████████░░░░ 85%   │ ✔ Approved   │
└────────────────────────┴────────────────────────────────┴──────────────┘

┌─────────────────────────────── Key Evidence ────────────────────────────────┐
│   • Exception 0xC0000005 (ACCESS_VIOLATION) reading freed heap block        │
│   • Stack frame 02 shows CImage::Load with stale this pointer               │
│   • Render thread freed the buffer 3ms before the fault                     │
└─────────────────────────────────────────────────────────────────────────────┘

        incident a3f21c89  ·  2 debate rounds  ·  22,354 tokens  ·  sym 92%
```

---

## 6. Event → Widget Mapping

```
DomainEvent               Evidence Stream          Forensic Agents          Investigation Process
──────────────────────────────────────────────────────────────────────────────────────────────
InvestigationStarted      append "CDB started"     all → STANDBY            spinner starts
                          stamp start time          round = 1                stage 0/7

EvidenceExtracted         append fault lines        first agent → ANALYZING  advance to stage 1
                          append stack frames       (OS Kernel)              status: "OS Kernel…"
                          append sym warning?

AgentSpoke(os_kernel)     append "OS Kernel »…"    os_kernel → DONE         advance stage
                                                   code_analyst → ANALYZING  status: "Code Analyst…"

AgentSpoke(code_analyst)  append "Code Analyst »…" code_analyst → DONE      advance stage
                                                   log_historian → ANALYZING status: "Log Historian…"

AgentSpoke(log_historian) append "Log Historian »…"log_historian → DONE     advance stage
                                                   skeptic → ANALYZING       status: "Skeptic…"

AgentSpoke(skeptic)       append "Skeptic »…"      skeptic → DONE           advance stage
                                                                             status: "Weighing…"

ConsensusEvaluated        append "consensus Rn …"  all → STANDBY            advance stage
                          append "threshold …"     round += 1               add consensus row
                          (if not converged)       (if not converged)       if not converged:
                                                   first → ANALYZING         extend total stages

InvestigationCompleted    append "✔ complete"      all remain DONE          bar → full
                                                                            live.stop()
                                                                            render_verdict()

HumanInputRequired        append "⚠ HITL required" all remain as-is         bar → full
                                                                            live.stop()
                                                                            render_verdict()
```

---

## 7. Implementation Plan

### 7.1 New class: `WarRoomView`

Lives in `src/aegis_swr/views/rich_view.py`, replaces `RichView`.

```python
class WarRoomView:
    """Full-screen three-pane war room view driven by the EventBus."""

    # ── state ──
    _start_time: float
    _round: int
    _evidence_lines: list[Text]          # timestamped; last N shown
    _agent_state: dict[str, AgentState]  # name → {status, conf, finding}
    _consensus_history: list[tuple[int, float]]   # [(round, score)]
    _stage_started: float
    _spinner_frame: int                  # incremented on each render tick

    def attach(self, bus: EventBus) -> Callable[[], None]: ...
    def _build_layout(self) -> Layout: ...
    def _render_header(self) -> Text: ...
    def _render_evidence(self) -> Panel: ...
    def _render_agents(self) -> Panel: ...
    def _render_process(self) -> Panel: ...
    def _refresh(self) -> None: ...
```

### 7.2 `AgentState` dataclass

```python
@dataclass
class AgentState:
    status: Literal["STANDBY", "ANALYZING", "REVIEWING", "DONE"] = "STANDBY"
    confidence: float = 0.0
    finding: str = ""      # truncated to panel width
```

### 7.3 Spinner advancement

`_spinner_frame` is incremented on each `_refresh()` call (12/s). Active agent rows use `SPINNER_FRAMES[_spinner_frame % len(SPINNER_FRAMES)]`.

```python
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
```

### 7.4 Layout height budget

```python
def _render_evidence(self) -> Panel:
    inner_h = (console.height - 3) // 1   # header=1, borders=2
    lines = self._evidence_lines[-(inner_h):]
    ...
```

Because `Layout` clips its children to the allocated region, any overflow is cut automatically. We just need to avoid an unbounded `_evidence_lines` list growing forever — cap at 500 entries.

### 7.5 `_render_agents` sub-panel height

Each agent block needs exactly 3 lines + 1 separator rule = 4 rows, × 4 agents = 16 rows + panel borders (2) = 18 minimum. If terminal is shorter than 36 rows (header + both right panes), collapse each agent to 2 lines (drop the finding line).

### 7.6 Attachment point

`stream_and_display` in `_formatters.py` swaps `RichView` → `WarRoomView`:

```python
async def stream_and_display(orch, source, console) -> RCAReport | None:
    from aegis_swr.views.rich_view import WarRoomView
    view = WarRoomView(console)
    detach = view.attach(orch.events)
    ...
```

`RichView` is kept as a simpler fallback for narrow terminals (< 80 columns) or `--output simple` (future flag).

### 7.7 Narrow terminal fallback

At `attach()` time, check `console.width`:
- `< 80` → fall back to existing `RichView` (single-column trail)
- `>= 80` → use `WarRoomView`

```python
def make_view(console: Console) -> RichView | WarRoomView:
    return WarRoomView(console) if console.width >= 80 else RichView(console)
```

---

## 8. Files Changed

| File                               | Change                                                                                                                      |
|------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| `src/aegis_swr/views/rich_view.py` | Add `AgentState`, `WarRoomView`, `make_view`; keep `RichView`, `render_verdict`, `make_console`                             |
| `src/aegis_swr/cli/_formatters.py` | `stream_and_display` calls `make_view(console)` instead of `RichView(console)`                                              |
| `tests/unit/test_views.py`         | New: unit tests for `AgentState` transitions and `WarRoomView` event handling (no screen rendering — test state not pixels) |

No changes to `core/`, `backends/`, or `cli/commands.py`.

---

## 9. Rich APIs Used

| Rich class                                 | Use                                                            |
|--------------------------------------------|----------------------------------------------------------------|
| `Layout`                                   | Three-pane split; `split_column`, `split_row`, `ratio`, `size` |
| `Live`                                     | Full-screen refresh at 12 fps                                  |
| `Panel`                                    | Borders around each pane and the verdict                       |
| `Progress` / `SpinnerColumn` / `BarColumn` | Stage progress in Investigation Process                        |
| `Text`                                     | Inline styled text segments everywhere                         |
| `Rule`                                     | Separator between agent sub-panels and round markers           |
| `Table`                                    | Panel Verdict table in the final verdict                       |
| `Syntax`                                   | Probabilistic fix in the final verdict                         |

All in Rich 15, no new dependencies needed.
