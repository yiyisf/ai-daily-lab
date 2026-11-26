#!/usr/bin/env python3
"""Offline simulator for AgentPRO-style workflow compiler optimizations.

Inspired by arXiv:2611.00628 ("AgentPRO: Coordinating Compiler Optimizations
for LLM Agent Workflows"): distinguishes execution dependencies from model
observation dependencies, performs redundant-read elimination + generation
region fusion, and attaches runtime state guards with safe fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Op:
    op_id: str
    kind: str  # "read" or "write"
    resource: str
    value: Optional[str] = None
    needs_llm_observation: bool = True
    payload_tokens: int = 400


@dataclass
class Region:
    region_id: str
    ops: List[Op]
    guard_versions: Dict[str, int] = field(default_factory=dict)


@dataclass
class RunStats:
    llm_calls: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
    guard_fallbacks: int = 0


class MockEnv:
    """Deterministic key-value workspace with monotonic version counters."""

    def __init__(self) -> None:
        self.data: Dict[str, str] = {
            "config.yaml": "env=staging;retry=3",
            "schema.json": "v2:strict",
            "components.md": "Button,Modal,Table",
            "routes.ts": "/orders,/users",
        }
        self.versions: Dict[str, int] = {k: 1 for k in self.data}

    def read(self, key: str) -> Tuple[str, int]:
        return self.data[key], self.versions[key]

    def write(self, key: str, value: str) -> None:
        self.data[key] = value
        self.versions[key] = self.versions.get(key, 0) + 1


def build_baseline_workflow() -> List[Op]:
    """A realistic 8-step coding/ops workflow with redundant reads & fusable writes."""
    return [
        Op("O1", "read", "config.yaml", needs_llm_observation=True, payload_tokens=600),
        Op("O2", "read", "components.md", needs_llm_observation=True, payload_tokens=900),
        Op("O3", "read", "config.yaml", needs_llm_observation=True, payload_tokens=600),  # redundant!
        Op("O4", "write", "routes.ts", value="/orders,/users,/health", needs_llm_observation=False, payload_tokens=300),
        Op("O5", "read", "components.md", needs_llm_observation=True, payload_tokens=900),  # redundant!
        Op("O6", "read", "schema.json", needs_llm_observation=True, payload_tokens=500),
        Op("O7", "write", "config.yaml", value="env=staging;retry=5", needs_llm_observation=False, payload_tokens=300),
        Op("O8", "write", "schema.json", value="v2:strict+health", needs_llm_observation=False, payload_tokens=300),
    ]


def execute_baseline(env: MockEnv, ops: List[Op]) -> Tuple[Dict[str, str], RunStats]:
    """Naive turn-by-turn agent loop: every op returns to LLM, accumulating context."""
    stats = RunStats()
    context_tokens = 1200  # base system prompt + task

    for op in ops:
        stats.llm_calls += 1
        stats.total_tokens += context_tokens  # prefill full history every turn
        stats.tool_calls += 1
        if op.kind == "read":
            env.read(op.resource)
            context_tokens += op.payload_tokens
        else:
            env.write(op.resource, op.value or "")
            context_tokens += op.payload_tokens
        stats.total_tokens += 180  # model action generation tokens

    return dict(env.data), stats


def compile_workflow(ops: List[Op], snapshot_versions: Dict[str, int]) -> List[Region]:
    """Pass 1: Eliminate redundant reads; Pass 2: Fuse adjacent non-observing ops."""
    seen_reads: Dict[str, bool] = {}
    pruned: List[Op] = []
    for op in ops:
        if op.kind == "read":
            if seen_reads.get(op.resource):
                continue  # redundant read eliminated
            seen_reads[op.resource] = True
            pruned.append(op)
        else:
            seen_reads[op.resource] = False  # invalidate after write
            pruned.append(op)

    # Pass 2: Group consecutive ops that don't require intermediate LLM re-observation
    regions: List[Region] = []
    cur_ops: List[Op] = []
    for op in pruned:
        cur_ops.append(op)
        # Flush a generation region only when a boundary requires fresh LLM observation
        if op.kind == "read" and op.needs_llm_observation:
            # Batch consecutive initial reads together before the first decision
            continue

    # Cleaner region partitioning:
    # Region 1: all pure reads before first write (batched in 1 LLM call)
    # Region 2: independent writes + remaining reads with runtime version guards
    regions = []
    buf: List[Op] = []
    cur_kind: Optional[str] = None
    idx = 1
    for op in pruned:
        if cur_kind is not None and op.kind != cur_kind and cur_kind == "read":
            guard = {o.resource: snapshot_versions[o.resource] for o in buf if o.resource in snapshot_versions}
            regions.append(Region(f"R{idx}", buf, guard))
            idx += 1
            buf = [op]
            cur_kind = op.kind
        elif cur_kind == "write" and op.kind == "read":
            guard = {o.resource: snapshot_versions[o.resource] for o in buf if o.resource in snapshot_versions}
            regions.append(Region(f"R{idx}", buf, guard))
            idx += 1
            buf = [op]
            cur_kind = op.kind
        else:
            buf.append(op)
            cur_kind = op.kind
    if buf:
        guard = {o.resource: snapshot_versions[o.resource] for o in buf if o.resource in snapshot_versions}
        regions.append(Region(f"R{idx}", buf, guard))

    return regions


def execute_compiled(
    env: MockEnv,
    ops: List[Op],
    regions: List[Region],
    inject_drift_before_region: Optional[str] = None,
) -> Tuple[Dict[str, str], RunStats]:
    """Run compiled regions with runtime version guards and baseline fallback."""
    stats = RunStats()
    context_tokens = 1200

    for reg in regions:
        if inject_drift_before_region and reg.region_id == inject_drift_before_region:
            # Simulate unexpected external state mutation on a guarded resource
            first_key = next(iter(reg.guard_versions))
            env.versions[first_key] += 99

        # Runtime guard check before executing a fused write region
        drifted = any(
            env.versions.get(res) != ver for res, ver in reg.guard_versions.items()
        )
        if drifted:
            stats.guard_fallbacks += 1
            # Safe fallback: execute remaining ops one-by-one like baseline
            for op in reg.ops:
                stats.llm_calls += 1
                stats.total_tokens += context_tokens + 180
                stats.tool_calls += 1
                if op.kind == "read":
                    env.read(op.resource)
                else:
                    env.write(op.resource, op.value or "")
                context_tokens += op.payload_tokens
            continue

        # Single fused LLM call for the entire region
        stats.llm_calls += 1
        stats.total_tokens += context_tokens + 180
        for op in reg.ops:
            stats.tool_calls += 1
            if op.kind == "read":
                env.read(op.resource)
                context_tokens += op.payload_tokens
            else:
                env.write(op.resource, op.value or "")
                # Non-observed writes don't need full payload echoed back to LLM
                context_tokens += 60

    return dict(env.data), stats


def main() -> int:
    ops = build_baseline_workflow()

    # 1. Baseline run
    env_base = MockEnv()
    state_base, st_base = execute_baseline(env_base, ops)

    # 2. Compiled normal run (no drift)
    env_opt = MockEnv()
    regions = compile_workflow(ops, dict(env_opt.versions))
    state_opt, st_opt = execute_compiled(env_opt, ops, regions)

    # 3. Compiled run with injected external state drift (guard must trigger!)
    env_drift = MockEnv()
    regions_drift = compile_workflow(ops, dict(env_drift.versions))
    target_reg = regions_drift[-1].region_id
    state_drift, st_drift = execute_compiled(
        env_drift, ops, regions_drift, inject_drift_before_region=target_reg
    )

    token_reduction = (st_base.total_tokens - st_opt.total_tokens) / st_base.total_tokens
    llm_call_reduction = (st_base.llm_calls - st_opt.llm_calls) / st_base.llm_calls

    print("=== AgentPRO Workflow Compiler Optimization Simulator ===")
    print(f"Baseline : llm_calls={st_base.llm_calls}, tool_calls={st_base.tool_calls}, tokens={st_base.total_tokens}")
    print(f"Compiled : llm_calls={st_opt.llm_calls}, tool_calls={st_opt.tool_calls}, tokens={st_opt.total_tokens}, regions={len(regions)}")
    print(f"DriftRun : llm_calls={st_drift.llm_calls}, guard_fallbacks={st_drift.guard_fallbacks}")

    print(f"METRIC: token_reduction_pct={token_reduction*100:.2f}")
    print(f"METRIC: llm_call_reduction_pct={llm_call_reduction*100:.2f}")
    print(f"METRIC: baseline_tokens={st_base.total_tokens}")
    print(f"METRIC: compiled_tokens={st_opt.total_tokens}")
    print(f"METRIC: drift_guard_fallbacks={st_drift.guard_fallbacks}")

    assert state_opt == state_base, "Compiled workflow state diverged from baseline!"
    assert state_drift == state_base, "Drift fallback state diverged from baseline!"
    assert st_drift.guard_fallbacks == 1, "Runtime guard failed to trigger on state drift!"
    assert token_reduction >= 0.35, f"Expected >= 35% token reduction, got {token_reduction:.2%}"
    assert llm_call_reduction >= 0.50, f"Expected >= 50% LLM call reduction, got {llm_call_reduction:.2%}"

    print("[PASS] Workflow compiler optimization and runtime drift guard verified.")
    print(
        f"RESULT: token_reduction={token_reduction*100:.1f}% "
        f"({st_base.total_tokens}->{st_opt.total_tokens}), "
        f"llm_calls={st_base.llm_calls}->{st_opt.llm_calls}, "
        f"guard_fallbacks={st_drift.guard_fallbacks}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
