"""AlbertState: LangGraph state for the Albert Thought Agent FSM."""
import operator
from typing import Annotated, TypedDict, Literal, Optional


def _take_last(_a, b):
    return b


GENERATORS = ["winning", "first_principle", "timing",
              "competitor", "owner_business", "convergence_redteam"]
CHALLENGE_STATUSES = [
    "answered", "partially_answered", "needs_external_research", "needs_internal_data",
    "needs_bu_judgment", "needs_albert_decision", "needs_source_validation", "blocked"]
DECISIONS = ["continue_research", "branch", "rerank", "pull_human",
             "push_human", "synthesize", "pause", "terminal_stop"]
AUDIT_VERDICTS = ["continue", "exhausted", "rework"]
RISK_LEVELS = ["low", "medium", "high"]


class AlbertState(TypedDict, total=False):
    # Input (the albert_input contract, normalized)
    albert_input: dict
    mode: Literal["cockpit", "standalone"]
    current_answer: str
    original_objective: str
    meeting_context: str
    output_purpose: str
    issue_map: list[dict]
    challenge_map: list[dict]
    evidence: list[dict]
    skeptic_output: list[str]
    source_critic_output: list[str]
    readiness_scores: dict
    recent_research_actions: list[str]
    research_state: dict
    proposal: dict
    run_id: str
    run_dir: str
    user_email: Optional[str]

    # Visibility accumulators
    screen_summary: Annotated[Optional[str], _take_last]
    stage_summaries: Annotated[list[dict], operator.add]
    stage_summaries_path: Annotated[Optional[str], _take_last]
    visibility_receipt: Annotated[dict, _take_last]

    # Phase 0
    phase_0_complete: bool
    phase_0_status: Optional[Literal["passed", "failed"]]
    research: list[dict]
    meta_question: dict

    # Phase 1
    phase_1_complete: bool
    phase_1_status: Optional[Literal["passed", "failed"]]
    top_ambiguities: list[dict]

    # Phase 2
    phase_2_complete: bool
    phase_2_status: Optional[Literal["passed", "failed"]]
    albert_challenges: list[dict]
    weak_points: list[str]
    missing_business_context: list[str]
    would_survive_leadership: Optional[bool]

    # Phase 3 (exhaustion loop with phase 2)
    phase_3_complete: bool
    phase_3_status: Optional[Literal["passed", "failed"]]
    phase_3_rounds: list[dict]
    phase_3_verdict: Optional[Literal["EXHAUSTED", "REWORK"]]
    phase_3_attempt_count: int

    # Phase 4
    phase_4_complete: bool
    phase_4_status: Optional[Literal["passed", "failed"]]
    missing_evidence: list[dict]
    questions_albert_would_ask: list[str]
    premature_end_risk: dict
    research_drift_risk: dict
    recommended_next_probe: list[dict]
    recommended_next_action: Optional[str]
    rationale: str
    decision_gate: dict
    reproducible_judgment: str

    # Phase 5
    phase_5_complete: bool
    verdict: Optional[str]                 # AuditVerdict: continue|exhausted|rework
    degraded: bool
    run_status: Optional[Literal["passed", "failed"]]
    readiness_score_delta: int
    verdict_standalone: Optional[str]      # 可推進|要補證據|方向錯|產品定義不完整
    light: Optional[Literal["green", "yellow", "red"]]
    report_path: Optional[str]
    challenge_json_path: Optional[str]
    email_delivery_result: Optional[str]
    email_delivery_error: Optional[str]

    start_time: str
    end_time: Optional[str]
