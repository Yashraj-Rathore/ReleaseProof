"""Hard graph, tool, provider, time, cancellation, and loop guards."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

from packages.agent_core.contracts import (
    AgentLimits,
    AgentNode,
    AgentUsage,
    NodeProviderUsage,
    TerminationReason,
)


class AgentStopError(RuntimeError):
    """A safe, expected graph stop with no arbitrary provider details."""

    def __init__(self, reason: TerminationReason, error_code: str) -> None:
        super().__init__(error_code)
        self.reason = reason
        self.error_code = error_code


class BudgetGuard:
    def __init__(
        self,
        limits: AgentLimits,
        *,
        cancellation_check: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = limits
        self._cancellation_check = cancellation_check or (lambda: False)
        self._clock = clock
        self._started = clock()
        self._usage = AgentUsage()
        self._visited: set[tuple[AgentNode, str]] = set()

    @property
    def usage(self) -> AgentUsage:
        return self._usage

    def _common_check(self) -> None:
        if self._cancellation_check():
            raise AgentStopError(TerminationReason.CANCELLED, "agent_cancelled")
        if self._clock() - self._started > self.limits.max_wall_time_seconds:
            raise AgentStopError(TerminationReason.WALL_TIME_EXCEEDED, "agent_wall_time_exceeded")

    def enter_node(self, node: AgentNode, *, state_signature: str) -> float:
        self._common_check()
        if self._usage.steps >= self.limits.max_steps:
            raise AgentStopError(
                TerminationReason.STEP_BUDGET_EXCEEDED, "agent_step_budget_exceeded"
            )
        visit = (node, state_signature)
        if visit in self._visited:
            raise AgentStopError(TerminationReason.LOOP_DETECTED, "agent_loop_detected")
        self._visited.add(visit)
        self._usage = replace(self._usage, steps=self._usage.steps + 1)
        return self._clock()

    def finish_node(self, started: float) -> float:
        elapsed = self._clock() - started
        if elapsed > self.limits.per_node_timeout_seconds:
            raise AgentStopError(TerminationReason.NODE_TIMEOUT, "agent_node_timeout")
        self._common_check()
        return max(0.0, elapsed * 1_000.0)

    def reserve_tool(self) -> None:
        self._common_check()
        if self._usage.tool_calls >= self.limits.max_tool_calls:
            raise AgentStopError(
                TerminationReason.TOOL_BUDGET_EXCEEDED, "agent_tool_budget_exceeded"
            )
        self._usage = replace(self._usage, tool_calls=self._usage.tool_calls + 1)

    def record_tool_error(self) -> None:
        self._usage = replace(self._usage, tool_errors=self._usage.tool_errors + 1)

    def reserve_llm(self) -> tuple[int, int, int]:
        self._common_check()
        if self._usage.llm_calls >= self.limits.max_llm_calls:
            raise AgentStopError(
                TerminationReason.LLM_BUDGET_EXCEEDED,
                "agent_llm_call_budget_exceeded",
            )
        remaining_input = self.limits.max_input_tokens - self._usage.input_tokens
        remaining_output = self.limits.max_output_tokens - self._usage.output_tokens
        remaining_cost = self.limits.max_cost_microusd - self._usage.cost_microusd
        if min(remaining_input, remaining_output, remaining_cost) <= 0:
            raise AgentStopError(TerminationReason.LLM_BUDGET_EXCEEDED, "agent_llm_budget_exceeded")
        self._usage = replace(self._usage, llm_calls=self._usage.llm_calls + 1)
        return remaining_input, remaining_output, remaining_cost

    def record_llm(self, usage: NodeProviderUsage) -> None:
        updated = replace(
            self._usage,
            input_tokens=self._usage.input_tokens + usage.input_tokens,
            output_tokens=self._usage.output_tokens + usage.output_tokens,
            cost_microusd=self._usage.cost_microusd + usage.cost_microusd,
        )
        if (
            updated.input_tokens > self.limits.max_input_tokens
            or updated.output_tokens > self.limits.max_output_tokens
            or updated.cost_microusd > self.limits.max_cost_microusd
        ):
            self._usage = updated
            raise AgentStopError(TerminationReason.LLM_BUDGET_EXCEEDED, "agent_llm_budget_exceeded")
        self._usage = updated
