```
ID:        0262-event-ids-are-pooled-per-hardevent-type-with-eight-slots-and-fetcheventid-can-return-the-same-id-twice
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — two upstream skills state it, both `upstream/skills-dev-main`, therefore ONE
           origin (RULES.md Art. 3). Nothing was compiled and no event was allocated.
BOARD:     950PR, 950DT
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/sync-and-consistency.md:90-93
           — "- Ascend950（arch 3510）上 `QUE_MAX_EVENT = 8`，即每种 HardEvent 类型有独立的 8 个 eventID
           slot / - eventID 池按 HardEvent 类型独立分配 … / - `FetchEventID` 返回该类型池中第一个空闲
           slot（0–7），同类型只用 1 个时每次返回同一个值 / - 不同类型事件各自独立池，不会冲突"
SOURCE:    ops/ascendc-sync-check/references/sync-mechanism.md:167-174 — "多数产品（Atlas A2/A3 训练推理、
           Ascend 950PR/950DT、Atlas 推理 AI Core）event ID 范围 0-7（8 个）" and the FetchEventID row:
           "查询可用 ID，不申请不占用 | 单组 Set/Wait 配对 | 同流水内连续两组用 FetchEventID 可能返回
           相同 ID，触发"重复 Set 同一 ID"未定义行为"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 board on which two consecutive `FetchEventID(HardEvent::MTE2_V)` calls, with no
           intervening release, return different IDs — the "query, do not reserve" semantics would
           then be wrong and the trap is empty.
```

# 0262 · Event IDs are pooled per HardEvent type with eight slots, and `FetchEventID` can return the same ID twice

## 1 · Claim
Upstream asserts that on Ascend950 (arch 3510) `QUE_MAX_EVENT = 8`: each `HardEvent` type has its own
independent pool of eight event-ID slots numbered 0-7, pools for different types do not collide, and
`FetchEventID(HardEvent::X)` returns the first free slot in type X's pool. Upstream asserts the
consequence that makes this a trap: `FetchEventID` **queries** without reserving, so two consecutive
calls for the same HardEvent type with no intervening use return the same ID, and setting the same ID
twice is undefined behaviour. Upstream asserts the alternative for concurrent groups — `AllocEventID`,
which reserves and must be released with `ReleaseEventID` or the pool exhausts. Upstream asserts the
practice that avoids the trap: fetch all event IDs once in `Init()` or at the top of `Process()`, never
repeatedly at run time. Not established here: nothing was compiled and no event was allocated.

## 2 · The wrong branch this removes
`FetchEventID` reads like an allocator. It is named like one, it returns an ID, and the ID it returns is
free. Every instinct says "call it when you need one" — and doing that inside a loop, or twice for two
concurrent synchronisation groups on the same pipe pair, returns the same ID both times because nothing
was taken.

What follows is not a compile error and not a wrong number. Two `SetFlag<HardEvent::MTE2_V>(id)` calls
on one ID with two different `WaitFlag`s is undefined behaviour: the second Set may be swallowed, the
first Wait may satisfy on the second Set, or the pair may deadlock. The observable is intermittent —
correct output most of the time, a hang or a corrupted tile occasionally, moving with shape and
occupancy. The regbase pitfall material names this diagnosis loop exactly: "Treating non-determinism as
harmless noise … identical input produces different mismatches … synchronization or branch-selection
problems are masquerading as precision drift" (`common_traps.md` §8). An author will chase a precision
bug that is not there.

Two secondary branches follow from the pool structure and are easy to get backwards.

The pools are **per HardEvent type**, so `FetchEventID(MTE2_V)` and `FetchEventID(V_MTE3)` may both
return 0 and that is correct — they are different pools and do not conflict. An agent that "fixes" a
duplicate-ID sighting by forcing distinct IDs across types has misdiagnosed and has burned pool slots.

The budget is eight **per type**, not eight total. An agent that treats it as a global eight will
over-conserve; one that forgets it exists will exhaust a type's pool with `AllocEventID` and no
`ReleaseEventID`, which upstream names as the failure mode of the reserving API. So the two APIs have
opposite failure modes — `FetchEventID` collides, `AllocEventID` leaks — and choosing between them is a
decision about whether the groups are concurrent.

## 3 · Ground / Source
`sync-and-consistency.md:88-95`, the Event ID 管理 block in full:

> **Event ID 管理**：
> - Ascend950（arch 3510）上 `QUE_MAX_EVENT = 8`，即每种 HardEvent 类型有独立的 8 个 eventID slot
> - eventID 池按 HardEvent 类型独立分配：`FetchEventID(HardEvent::MTE2_V)` 在 `MTE2_V` 类型的池中分配，
>   `FetchEventID(HardEvent::V_MTE3)` 在 `V_MTE3` 类型的池中独立分配
> - `FetchEventID` 返回该类型池中第一个空闲 slot（0–7），同类型只用 1 个时每次返回同一个值
> - 不同类型事件各自独立池，不会冲突
> - 通过 `FetchEventID()` 获取，在 `Init()` 或 `Process()` 开头统一获取，避免运行时重复调用

The last bullet is the operative one and it is stated as practice rather than as a rule — 避免运行时
重复调用. Read against the third bullet ("同类型只用 1 个时每次返回同一个值") it is not a style
preference: repeated run-time calls are exactly what produces the duplicate.

The interface and the four Vector events, from the same file `:66-84`:

> **接口**：
> ```cpp
> template <HardEvent event> __aicore__ inline void SetFlag(int32_t eventID);
> template <HardEvent event> __aicore__ inline void WaitFlag(int32_t eventID);
> ```
> - `event`：模板参数，HardEvent 枚举值，命名规则 `源流水_目标流水`（如 `MTE2_V` = MTE2 是源，V 是目标
>   ——V 等 MTE2）
> - `eventID`：事件 ID。通过 `GetTPipePtr()->FetchEventID(HardEvent::XXX)` 获取，不可硬编码
> - **SetFlag/WaitFlag 必须成对出现**
>
> | HardEvent | 含义 | 场景 |
> | `MTE2_V` | MTE2→V，V 等 MTE2 | MTE2 写完 UB → V 要读该 UB |
> | `V_MTE2` | V→MTE2，MTE2 等 V | V 正在读 UB → MTE2 要覆盖该 UB |
> | `V_MTE3` | V→MTE3，MTE3 等 V | V 写完 UB → MTE3 要读该 UB |
> | `MTE3_MTE2` | MTE3→MTE2，MTE2 等 MTE3 | 上轮 MTE3 读 UB → 下轮 MTE2 要覆盖该 UB |

`不可硬编码` on the eventID is the same discipline as 0207 and 0252 applied to a different resource:
there is an accessor, and the literal that agrees with it today will not agree tomorrow.

The recommended acquisition shape, `:98-107`, is the artefact worth cloning — all IDs fetched once,
before the loop:

```cpp
int32_t evMTE2toV    = static_cast<int32_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE2_V));
int32_t evVtoMTE3    = static_cast<int32_t>(GetTPipePtr()->FetchEventID(HardEvent::V_MTE3));
int32_t evMTE3toMTE2 = static_cast<int32_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE3_MTE2));
```

Three fetches, three different types, hoisted out of the loop. Note that all three may legitimately
return 0.

The second skill states the range and the trap independently of the pool description.
`sync-mechanism.md:167-174`:

> ### 5.1 数量
> 多数产品（Atlas A2/A3 训练推理、Ascend 950PR/950DT、Atlas 推理 AI Core）event ID 范围 0-7（8 个）；
> Atlas 训练系列产品 0-3（4 个）。
>
> ### 5.2 FetchEventID vs AllocEventID
> | API | 语义 | 适用 | 风险 |
> | FetchEventID | 查询可用 ID，不申请不占用 | 单组 Set/Wait 配对 | 同流水内连续两组用 FetchEventID 可能
>   返回相同 ID，触发"重复 Set 同一 ID"未定义行为 |
> | AllocEventID | 申请并占用，需 ReleaseEventID 释放 | 多组同步并发 | 占用后须释放，否则 TEventID 耗尽 |

查询可用 ID，**不申请不占用** — query, do not request, do not occupy. That is the sentence the API's
name contradicts, and it is why this is filed as a trap.

Both files are `upstream/skills-dev-main`, so this is **one origin** (RULES.md Art. 3) despite appearing in
two skills. The two accounts are consistent and mutually reinforcing on the range (0-7) and on the
duplicate-ID hazard; the pool-per-type structure is stated only in the first.

One note upstream's second file adds that the first does not: the 0-7 range is stated as 多数产品 —
most products — with Atlas 训练系列 at 0-3. So the eight is a per-product figure, and 950PR/950DT are
named in the eight-slot group. Nothing here transfers to a product not on that list.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.

Arm A — the duplicate, observed directly. In one kernel, call `FetchEventID(HardEvent::MTE2_V)` twice
with no intervening Set/Wait and store both returned IDs to GM. Upstream predicts equality. Then call
`FetchEventID(HardEvent::MTE2_V)` and `FetchEventID(HardEvent::V_MTE3)` and store both — upstream
predicts these may also be equal and that this is harmless, being different pools. Recording both pairs
in one probe is what separates "the pools are per type" from "the allocator is broken".

Arm B — the pool depth, per type. Call `AllocEventID(HardEvent::MTE2_V)` repeatedly without releasing,
recording each returned ID, until it fails or repeats. Upstream predicts eight distinct IDs 0-7 then
exhaustion. Repeat for a second HardEvent type *while the first pool is exhausted* — if the pools are
independent, the second type still yields eight. That interleaving is the arm that actually tests
independence; two sequential exhaustion tests would not.

Arm C — the undefined behaviour, bounded rather than invoked blindly. Build a kernel with two
synchronisation groups on the same HardEvent type deliberately sharing one ID from `FetchEventID`, and
run it 50 times at each of five shapes (n ∈ {64, 512, 4096, 10752, 65536}). Record: output correctness
per run, and whether any run hangs. A watchdog with a declared timeout is mandatory — the failure mode
upstream names includes deadlock, and an un-timed arm on a shared machine would hold a die. Compare
against the same kernel using `AllocEventID` for the two groups.

Arm D — the leak, which is `AllocEventID`'s opposite failure. Call `AllocEventID` in a loop with no
`ReleaseEventID` across kernel invocations and record whether exhaustion persists across launches or
resets. Upstream says the pool exhausts; whether it survives a kernel boundary is unstated and is what
determines whether a leak is a per-kernel bug or a session-level one.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. Arm C's watchdog timeout is declared before the run and
the die is released on timeout.

## 5 · Checker — acceptance declared before the run
Four verdict variables, never aggregated — they test four independent assertions and one passing must
not cover another failing.

`fetch_repeats_same_type` (Arm A) — pass iff the two same-type fetches return equal IDs. Declared now:
**unequal IDs overturn this entry** — `FetchEventID` would then reserve, the trap would be empty, and the
"fetch once in Init" practice would be unnecessary rather than load-bearing.

`pools_are_independent` (Arm B) — pass iff a second type still yields eight distinct IDs while the first
type's pool is exhausted. Sequential (non-interleaved) exhaustion is reported as
`NOT ESTABLISHED`, never as a pass: two pools that happen to give the same sequence when tested one
after the other are indistinguishable from one shared pool that was reset.

`pool_depth[type]` (Arm B) — pass iff 8, per type. A depth of 4 would mean this board is in the
`Atlas 训练系列` group of the second source's table rather than the 950 group, which would be a finding
about the source's product grouping.

`shared_id_is_unsafe` (Arm C) — true iff **any** of the 250 runs produces wrong output or hits the
watchdog. One hit sets it true. A clean 250 does **not** establish that sharing an ID is safe — it is
reported as `undefined behaviour not provoked`, because "undefined" is exactly the thing a clean run
cannot refute, and declaring that now prevents a null result being read as permission.

Process exit code is not the verdict anywhere: a watchdog kill in Arm C exits non-zero and is the
informative outcome.

The positive fixture, declared before the run: Arm C must include a control build using `AllocEventID`
for the two groups, which **must** produce correct output in all 250 runs. If the control also fails, the
harness's two-group kernel is wrong independently of event IDs and every `shared_id_is_unsafe` verdict is
void. A second fixture for Arm A: fetch from a HardEvent type never used elsewhere in the kernel and
confirm it returns 0 — if it returns something else, slots are occupied by machinery the probe does not
control and the ID equalities it reports mean nothing. Without both, the checker reads only "two numbers
matched", which is the known blind species.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
`FetchEventID` was called, no pool was exhausted, and no device was contacted. `QUE_MAX_EVENT = 8` is
upstream's assertion; no installed header was read to confirm the constant exists under that spelling,
and that check is a file read that remains open.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish the pool depth, the per-type independence, or
the duplicate-ID behaviour — Arms A, B and D are all open, and Arm A alone would overturn the entry if it
came back unequal. It does not establish that sharing an ID *fails*: upstream calls it undefined
behaviour, §5 declares in advance that a clean 250-run arm cannot refute that, and no amount of passing
observation converts undefined into safe. There is **no second origin**: both quoted files are one repo,
and no installed header was consulted, unlike 0244 and 0246 where the toolkit answered. It says nothing
about whether the eight slots are a hardware or a framework limit, nor whether `QUE_MAX_EVENT` is
queryable at run time rather than hardcoded — which matters, since upstream forbids hardcoding the ID
while stating the pool size as a literal. It says nothing about `AllocEventID`'s behaviour across kernel
boundaries; Arm D exists because upstream states exhaustion without stating its lifetime. It covers the
four Vector `HardEvent` types upstream tabulates (`MTE2_V`, `V_MTE2`, `V_MTE3`, `MTE3_MTE2`) and says
nothing about Cube-side or cross-core event types, whose pools may differ. It says nothing about
`SyncAll` or cross-core synchronisation, which is a different mechanism with its own host-side
precondition. Nothing transfers to the other book (RULES.md Art. 1): the second source's product list includes
A2/A3 in the same eight-slot group, and that half of the sentence is carried here as quotation only —
this book claims eight slots for 950PR and 950DT and nothing else.
