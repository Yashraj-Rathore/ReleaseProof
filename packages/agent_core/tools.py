"""Bounded read-only tools over already-authorized evidence references."""

from __future__ import annotations

from dataclasses import dataclass

from packages.agent_core.contracts import (
    AgentLimits,
    EvidenceCategory,
    EvidenceReference,
    ToolName,
    ToolStatus,
)

TOOL_CATEGORY = {
    ToolName.GET_FEATURES: EvidenceCategory.FEATURE,
    ToolName.GET_GRAPH: EvidenceCategory.GRAPH,
    ToolName.SEARCH_HISTORY: EvidenceCategory.RETRIEVAL,
    ToolName.GET_RISK: EvidenceCategory.RISK,
    ToolName.GET_TEST_RESULTS: EvidenceCategory.TEST_RESULT,
    ToolName.GET_EXECUTION_EVIDENCE: EvidenceCategory.EXECUTION,
}
READ_ONLY_TOOL_ALLOWLIST = frozenset(TOOL_CATEGORY)


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool: ToolName
    status: ToolStatus
    evidence: tuple[EvidenceReference, ...]
    truncated: bool
    summary: str
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status is ToolStatus.FAILED and not self.error_code:
            raise ValueError("failed tools require a safe error code")
        if self.status is not ToolStatus.FAILED and self.error_code is not None:
            raise ValueError("successful/missing tools cannot carry an error")


class BoundedInvestigationTools:
    """There are deliberately no merge, deploy, repository-write, or execution methods."""

    def __init__(
        self,
        evidence: tuple[EvidenceReference, ...],
        limits: AgentLimits,
        *,
        failed_tools: tuple[ToolName, ...] = (),
    ) -> None:
        if not set(failed_tools).issubset(READ_ONLY_TOOL_ALLOWLIST):
            raise ValueError("failed tool fixture is outside the read-only allowlist")
        self._evidence = evidence
        self._limit = limits.max_evidence_per_tool
        self._failed_tools = frozenset(failed_tools)

    def read(self, tool: ToolName) -> ToolResult:
        if not isinstance(tool, ToolName) or tool not in READ_ONLY_TOOL_ALLOWLIST:
            raise ValueError("tool is outside the read-only investigation allowlist")
        if tool in self._failed_tools:
            return ToolResult(
                tool=tool,
                status=ToolStatus.FAILED,
                evidence=(),
                truncated=False,
                summary=f"{tool.value} failed with a safe provider-neutral status.",
                error_code=f"{tool.value}_failed",
            )
        matching = tuple(item for item in self._evidence if item.category is TOOL_CATEGORY[tool])
        selected = matching[: self._limit]
        if not selected:
            return ToolResult(
                tool=tool,
                status=ToolStatus.MISSING,
                evidence=(),
                truncated=False,
                summary=f"{tool.value} returned no authorized evidence.",
            )
        return ToolResult(
            tool=tool,
            status=ToolStatus.COMPLETED,
            evidence=selected,
            truncated=len(matching) > len(selected),
            summary=(
                f"{tool.value} returned {len(selected)} authorized reference(s)"
                f"; truncated={str(len(matching) > len(selected)).lower()}."
            ),
        )
