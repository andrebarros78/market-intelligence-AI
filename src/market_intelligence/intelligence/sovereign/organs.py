from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from market_intelligence.intelligence.sovereign.models import (
    ActionIntent,
    AutonomyLevel,
    CognitiveAudit,
    CorrelationFinding,
    ExperimentPlan,
    ExposureAssessment,
    Hypothesis,
    IntelligenceAssessment,
    KnowledgeState,
    Prediction,
    ProbePlan,
    Severity,
    SignalEnvelope,
    ValidationVerdict,
)

_PLATFORM_OUTPUT_MARKERS = (
    "price_suggestion",
    "item_competition",
    "catalog_suggestion",
    "public_candidate",
    "public_offer",
)

_BEHAVIORAL_MARKERS = (
    "question",
    "order",
    "message",
    "claim",
    "shipment",
    "payment",
    "stock",
    "visit",
    "quotation",
)

_SENSITIVE_ACTION_MARKERS = (
    "price",
    "stock",
    "publish",
    "pause",
    "close",
    "delete",
    "message",
    "refund",
    "campaign",
    "budget",
)


def _normalized(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _numeric(payload: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, value in payload.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            values[str(key)] = float(value)
    return values


class SovereignProbe:
    version = "sovereign-probe@1.0.0"

    def plan(self, signal: SignalEnvelope, history: Iterable[SignalEnvelope]) -> ProbePlan:
        history = tuple(history)
        kind = _normalized(signal.kind)
        source_kinds = {_normalized(item.kind) for item in history}
        missing: list[str] = []
        questions: list[str] = []
        observations: list[str] = []

        if any(marker in kind for marker in _PLATFORM_OUTPUT_MARKERS):
            questions.append("Qual mudanca observavel antecedeu esta saida produzida pela plataforma?")
            observations.extend(("comparar_estado_anterior", "buscar_eventos_antecedentes", "comparar_grupo_controle"))
        if not history:
            missing.append("historico_temporal")
            observations.append("coletar_nova_observacao_equivalente")
        if "price" in kind and not any("competition" in item for item in source_kinds):
            missing.append("competicao")
        if "competition" in kind and not any("price" in item for item in source_kinds):
            missing.append("preco")
        if any(marker in kind for marker in _BEHAVIORAL_MARKERS):
            questions.append("Este sinal antecede ou sucede uma mudanca de demanda, conversao ou qualidade?")
            observations.append("correlacionar_janelas_antes_durante_depois")
        if not questions:
            questions.append("Que evento anterior explica melhor este sinal e qual observacao o falsificaria?")
        if not observations:
            observations.append("repetir_observacao_em_janela_temporal")

        priority = Severity.HIGH if any(marker in kind for marker in _PLATFORM_OUTPUT_MARKERS) else Severity.MEDIUM
        return ProbePlan(
            questions=tuple(dict.fromkeys(questions)),
            missing_surfaces=tuple(dict.fromkeys(missing)),
            next_observations=tuple(dict.fromkeys(observations)),
            priority=priority,
        )


class SovereignCorrelator:
    version = "sovereign-correlator@1.0.0"

    def correlate(self, signal: SignalEnvelope, history: Iterable[SignalEnvelope]) -> CorrelationFinding:
        history = tuple(history)
        related = [
            item for item in history
            if item.marketplace == signal.marketplace
            and (item.entity_id == signal.entity_id or item.entity_type == signal.entity_type)
        ]
        current_numeric = _numeric(signal.payload)
        changes: dict[str, float] = {}
        shared: Counter[str] = Counter()
        comparable = 0

        for item in related[-16:]:
            previous = _numeric(item.payload)
            for key, current_value in current_numeric.items():
                if key in previous:
                    comparable += 1
                    changes[key] = current_value - previous[key]
                    shared[key] += 1

        if not related:
            strength = 0.0
            reason = "no_related_history"
        else:
            recency_factor = min(1.0, len(related) / 4.0)
            comparison_factor = min(1.0, comparable / max(1, len(current_numeric)))
            strength = round((0.45 * recency_factor) + (0.55 * comparison_factor), 4)
            reason = "temporal_entity_correlation" if comparable else "entity_context_correlation"

        return CorrelationFinding(
            related_signal_ids=tuple(item.signal_id for item in related[-16:]),
            shared_dimensions=tuple(key for key, _ in shared.most_common()),
            numeric_changes=changes,
            strength=strength,
            fact_eligible=bool(len(related) >= 2 and strength >= 0.65),
            reason=reason,
        )


class SovereignInstigator:
    version = "sovereign-instigator@1.0.0"

    def instigate(
        self,
        signal: SignalEnvelope,
        probe: ProbePlan,
        correlation: CorrelationFinding,
    ) -> tuple[Hypothesis, ...]:
        kind = _normalized(signal.kind)
        base_confidence = max(0.2, min(0.79, (signal.confidence + correlation.strength) / 2.0))
        hypotheses: list[Hypothesis] = []

        if any(marker in kind for marker in _PLATFORM_OUTPUT_MARKERS):
            hypotheses.append(
                Hypothesis(
                    statement="A saida da plataforma pode responder a uma mudanca observavel anterior no mercado ou na operacao.",
                    rationale="O sinal e produzido pela propria plataforma e pode carregar informacao derivada.",
                    falsifier="Nenhuma variavel antecedente repetivel diferencia casos com e sem a mudanca.",
                    confidence=base_confidence,
                    causal_claim=False,
                )
            )
        if correlation.related_signal_ids:
            hypotheses.append(
                Hypothesis(
                    statement="O sinal atual pode pertencer ao mesmo regime dos eventos correlacionados recentes.",
                    rationale=f"Foram encontrados {len(correlation.related_signal_ids)} sinais relacionados.",
                    falsifier="A relacao desaparece quando comparada em novas janelas e entidades de controle.",
                    confidence=max(0.2, min(0.79, correlation.strength)),
                    causal_claim=False,
                )
            )
        if not hypotheses:
            hypotheses.append(
                Hypothesis(
                    statement="O sinal representa uma mudanca real que requer repeticao antes de promocao a conhecimento.",
                    rationale=probe.questions[0],
                    falsifier="O sinal nao se repete e a fonte retorna ao estado anterior sem consequencia observavel.",
                    confidence=min(0.6, signal.confidence),
                    causal_claim=False,
                )
            )
        return tuple(hypotheses)

    def feedback(
        self,
        *,
        findings: list[dict[str, Any]],
        correlations: list[Any],
        hypotheses: list[Any],
        evidence: list[dict[str, Any]],
        contradictions: list[Any],
        counterintelligence_objections: list[str],
        predictions: list[Any],
        gaps: list[str],
    ) -> tuple[str, ...]:
        """Turn loop returns into new investigation questions.

        This is the feedback path of the existing sovereign Instigator. It emits
        questions only; the existing ProgressiveInvestigationEngine remains the
        authoritative investigator.
        """
        questions: list[str] = [
            "O que ainda nao foi explicado pelas evidencias atuais?",
            "Qual hipotese alternativa permanece plausivel?",
            "Que evidencia poderia derrubar a conclusao mais forte?",
            "Existe outra variavel observavel relacionada que ainda nao foi comparada?",
            "Que evidencia legitima ainda falta para aumentar ou reduzir a confianca?",
            "Existe algo relevante dentro das superficies autorizadas que ainda nao procuramos?",
            "Alguma descoberta atual gera uma nova pergunta operacional importante?",
            "Existe ameaca ou oportunidade que ainda nao foi investigada adequadamente?",
        ]
        if contradictions:
            questions.insert(0, "As contradicoes observadas invalidam total ou parcialmente a conclusao atual?")
        if gaps:
            questions.insert(0, "As lacunas de dados ou validacao explicam a incerteza restante?")
        if correlations:
            questions.append("A correlacao permanece quando confrontada com outra janela, entidade ou controle observavel?")
        if hypotheses:
            questions.append("Qual das hipoteses atuais tem melhor suporte e qual tem o falsificador mais forte?")
        if predictions:
            questions.append("As previsoes anteriores foram confirmadas, contrariadas ou continuam sem evidencia posterior suficiente?")
        if evidence:
            questions.append("As evidencias principais sao independentes entre si ou repetem a mesma fonte?")
        if findings:
            questions.append("Qual achado tem maior impacto potencial e ainda possui explicacao incompleta?")
        questions.extend(str(item) for item in counterintelligence_objections if str(item).strip())
        return tuple(dict.fromkeys(questions))[:16]


class SovereignExperimenter:
    version = "sovereign-experimenter@1.0.0"

    def design(self, signal: SignalEnvelope, hypotheses: tuple[Hypothesis, ...]) -> ExperimentPlan:
        kind = _normalized(signal.kind)
        write_sensitive = any(marker in kind for marker in _SENSITIVE_ACTION_MARKERS)
        if write_sensitive:
            return ExperimentPlan(
                experiment_type="controlled_observational_or_owned_reversible",
                objective=f"Testar a hipotese principal sem inferir causalidade indevida: {hypotheses[0].statement}",
                control="entidades comparaveis sem alteracao",
                treatment="uma unica variavel somente se posteriormente autorizada pelo Action Gateway",
                measures=("estado_antes", "estado_depois", "sinais_plataforma", "resultado_negocio"),
                marketplace_write_required=True,
                requires_action_gateway=True,
                executable_now=False,
                reason="sensitive_marketplace_change_never_executes_inside_intelligence_core",
            )
        return ExperimentPlan(
            experiment_type="read_only_observational",
            objective=f"Buscar repeticao e contraexemplo para: {hypotheses[0].statement}",
            control="historico e entidades comparaveis",
            treatment="nenhuma alteracao no marketplace",
            measures=("repeticao", "correlacao", "contraexemplo", "resultado_posterior"),
            marketplace_write_required=False,
            requires_action_gateway=False,
            executable_now=True,
            reason="read_only_observation_allowed",
        )


class SovereignIntelligenceEngine:
    version = "sovereign-intelligence@1.0.0"

    def assess(
        self,
        signal: SignalEnvelope,
        correlation: CorrelationFinding,
        hypotheses: tuple[Hypothesis, ...],
    ) -> IntelligenceAssessment:
        kind = _normalized(signal.kind)
        if signal.provenance.get("collector_generated_pattern"):
            return IntelligenceAssessment(
                classification="collector_telemetry",
                summary=f"Telemetria do coletor para {signal.kind}; nao interpretar como comportamento do marketplace.",
                severity=Severity.INFO,
                confidence=max(0.0, min(1.0, signal.confidence)),
                opportunity=False,
                threat=False,
                development_need="exclude_from_market_behavior_learning",
                evidence=(f"source:{signal.source}", "collector_generated_pattern:true"),
            )
        platform_output = any(marker in kind for marker in _PLATFORM_OUTPUT_MARKERS)
        negative_marker = any(marker in kind for marker in ("claim", "error", "failure", "loss", "drop"))
        opportunity_marker = any(marker in kind for marker in ("candidate", "offer", "suggestion", "lead"))

        if negative_marker:
            classification = "threat_or_degradation"
            severity = Severity.HIGH if correlation.strength >= 0.65 else Severity.MEDIUM
        elif platform_output:
            classification = "platform_behavior_signal"
            severity = Severity.HIGH
        elif opportunity_marker:
            classification = "opportunity"
            severity = Severity.MEDIUM
        else:
            classification = "market_observation"
            severity = Severity.MEDIUM

        confidence = max(signal.confidence, correlation.strength * 0.9)
        development_need = None
        if platform_output:
            development_need = f"manter_coleta_historica_e_modelagem_de_{kind}"

        return IntelligenceAssessment(
            classification=classification,
            summary=f"Sinal {signal.kind} em {signal.marketplace}/{signal.entity_type}:{signal.entity_id}.",
            severity=severity,
            confidence=max(0.0, min(1.0, confidence)),
            opportunity=opportunity_marker,
            threat=negative_marker,
            development_need=development_need,
            evidence=tuple(
                filter(
                    None,
                    (
                        f"source:{signal.source}",
                        f"correlation:{correlation.reason}" if correlation.related_signal_ids else "",
                        f"hypotheses:{len(hypotheses)}",
                    ),
                )
            ),
        )


class SovereignCounterIntelligence:
    version = "sovereign-counterintelligence@1.0.0"

    def assess(self, signal: SignalEnvelope) -> tuple[ExposureAssessment, ...]:
        kind = _normalized(signal.kind)
        assessments: list[ExposureAssessment] = []

        if any(marker in kind for marker in _BEHAVIORAL_MARKERS):
            assessments.append(
                ExposureAssessment(
                    data_point=signal.kind,
                    platform_observes="A plataforma observa este evento ou estado durante a operacao normal.",
                    possible_inferences=(
                        "ritmo_e_padrao_operacional",
                        "demanda_e_conversao_aproximadas",
                        "qualidade_ou_friccao_operacional",
                    ),
                    risk=Severity.MEDIUM,
                    mitigation="minimizar dados desnecessarios e manter operacao consistente; nao tentar ocultar eventos obrigatorios",
                    evidence=(f"source:{signal.source}",),
                )
            )
        if any(marker in kind for marker in _PLATFORM_OUTPUT_MARKERS):
            assessments.append(
                ExposureAssessment(
                    data_point=signal.kind,
                    platform_observes="A plataforma devolveu um sinal derivado de processamento interno.",
                    possible_inferences=(
                        "ha_criterios_internos_avaliando_o_item",
                        "mudancas_nas_entradas_podem_alterar_a_saida",
                    ),
                    risk=Severity.LOW,
                    mitigation="registrar serie temporal e comparar somente dados legitimamente observaveis",
                    evidence=(f"source:{signal.source}", "derived_platform_output"),
                )
            )
        if not assessments:
            assessments.append(
                ExposureAssessment(
                    data_point=signal.kind,
                    platform_observes="Exposicao especifica ainda nao comprovada.",
                    possible_inferences=("requer_mapeamento_de_exposicao",),
                    risk=Severity.INFO,
                    mitigation="manter como hipotese ate existir evidencia reproduzivel",
                    evidence=(f"source:{signal.source}",),
                )
            )
        return tuple(assessments)

    def challenge(
        self,
        *,
        findings: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        mode: str = "standard",
    ) -> tuple[str, ...]:
        """Attempt to falsify important conclusions without making new truth claims."""
        questions = [
            "Existe explicacao alternativa para a conclusao atual?",
            "Estamos confundindo correlacao com causa?",
            "O conjunto de dados esta incompleto ou enviesado pela cobertura disponivel?",
            "Uma mudanca de coleta, schema, canal ou instrumentacao pode explicar o sinal?",
            "O marketplace observa algum sinal operacional nosso relevante para esta interpretacao?",
            "Nossa interpretacao pode estar enviesada por selecao, recencia ou confirmacao?",
            "A conclusao permanece verdadeira quando confrontada com evidencia contraria?",
        ]
        if mode == "challenge":
            questions.insert(0, "Tente derrubar explicitamente a conclusao principal antes de aceita-la.")
        if any(str(item.get("knowledge_state") or "") == "validated" for item in findings):
            questions.append("O conhecimento validado continua sustentado por evidencia independente suficiente?")
        if not evidence:
            questions.insert(0, "Nao ha evidencia de missao suficiente; a conclusao deve permanecer inconclusiva?")
        return tuple(dict.fromkeys(questions))


class SovereignValidator:
    version = "sovereign-validator@1.0.0"

    def validate(
        self,
        signal: SignalEnvelope,
        correlation: CorrelationFinding,
        investigation: dict[str, Any] | None,
        experiment_evidence: dict[str, Any] | None = None,
    ) -> ValidationVerdict:
        investigation = investigation or {}
        experiment_evidence = experiment_evidence or {}
        status = str(investigation.get("status_after") or investigation.get("status") or "")
        observations = int(investigation.get("observation_count") or len(correlation.related_signal_ids) + 1)
        confidence = float(investigation.get("confidence_after") or signal.confidence)
        confidence = max(confidence, correlation.strength)
        provenance_complete = bool(signal.source and signal.provenance)
        repeated = observations >= 2
        causal_claim = bool(investigation.get("causal_claim", False))
        causal_validated = bool(
            experiment_evidence.get("independent_replication")
            and experiment_evidence.get("control_group")
            and experiment_evidence.get("reversible_or_read_only")
        )

        if causal_claim and not causal_validated:
            state = KnowledgeState.QUARANTINED
            sufficient = False
            reason = "causal_claim_requires_control_and_independent_replication"
        elif status in {"rejected", "inconclusive"}:
            state = KnowledgeState.REJECTED
            sufficient = False
            reason = "investigation_rejected_or_inconclusive"
        elif (
            signal.official_resource_fetched
            and provenance_complete
            and repeated
            and status == "confirmed"
            and confidence >= 0.80
        ):
            state = KnowledgeState.VALIDATED
            sufficient = True
            reason = "official_provenance_repetition_confirmed_investigation"
        elif correlation.fact_eligible and provenance_complete:
            state = KnowledgeState.CORRELATED
            sufficient = False
            reason = "correlation_requires_confirmed_investigation"
        elif repeated:
            state = KnowledgeState.OBSERVED
            sufficient = False
            reason = "repeated_observation_not_yet_confirmed"
        else:
            state = KnowledgeState.HYPOTHESIS
            sufficient = False
            reason = "insufficient_evidence"

        return ValidationVerdict(
            state=state,
            confidence=max(0.0, min(1.0, confidence)),
            evidence_sufficient=sufficient,
            provenance_complete=provenance_complete,
            repeated_observation=repeated,
            causal_validated=causal_validated,
            reason=reason,
        )


class SovereignPredictor:
    version = "sovereign-predictor@1.0.0"

    def predict(
        self,
        signal: SignalEnvelope,
        correlation: CorrelationFinding,
        validation: ValidationVerdict,
    ) -> Prediction:
        kind = _normalized(signal.kind)
        if validation.state is KnowledgeState.VALIDATED:
            statement = f"Se o padrao validado de {signal.kind} reaparecer, procurar os mesmos sinais antecedentes e posteriores."
            confidence = min(0.95, validation.confidence)
            state = KnowledgeState.TESTED
        elif validation.state in {KnowledgeState.REJECTED, KnowledgeState.QUARANTINED}:
            statement = f"Conhecimento {validation.state.value} para {signal.kind}; nao projetar consequencia ate revalidacao."
            confidence = min(0.20, validation.confidence)
            state = validation.state
        elif correlation.related_signal_ids:
            statement = f"O proximo evento relacionado a {signal.kind} pode repetir o regime observado; confirmar antes de agir."
            confidence = min(0.75, max(0.35, correlation.strength))
            state = KnowledgeState.HYPOTHESIS
        else:
            statement = f"Ainda nao ha base suficiente para prever consequencia de {signal.kind}; coletar repeticao."
            confidence = 0.2
            state = KnowledgeState.HYPOTHESIS

        leading = tuple(dict.fromkeys(("repeticao_do_sinal", *correlation.shared_dimensions[:4])))
        if any(marker in kind for marker in _PLATFORM_OUTPUT_MARKERS):
            leading = tuple(dict.fromkeys(("mudanca_em_entrada_observavel", "mudanca_em_saida_da_plataforma", *leading)))
        return Prediction(
            statement=statement,
            confidence=confidence,
            horizon="proxima_janela_observacional",
            leading_indicators=leading,
            falsifier="os indicadores antecedentes aparecem sem o resultado previsto em amostra repetida",
            state=state,
        )


class SovereignDecisionEngine:
    version = "sovereign-decision@1.0.0"

    def decide(
        self,
        signal: SignalEnvelope,
        intelligence: IntelligenceAssessment,
        validation: ValidationVerdict,
        prediction: Prediction,
    ) -> ActionIntent:
        kind = _normalized(signal.kind)
        sensitive = any(marker in kind for marker in _SENSITIVE_ACTION_MARKERS)

        if validation.state is KnowledgeState.VALIDATED and not sensitive:
            autonomy = AutonomyLevel.AUTOMATE_SAFE
            human = False
            recommendation = "automatizar somente processamento interno deterministico e continuar medindo resultado"
            risk = Severity.LOW
        elif validation.state is KnowledgeState.VALIDATED:
            autonomy = AutonomyLevel.HUMAN_REQUIRED
            human = True
            recommendation = "preparar proposta de acao; qualquer alteracao externa passa pelo Action Gateway"
            risk = intelligence.severity
        else:
            autonomy = AutonomyLevel.RECOMMEND
            human = True
            recommendation = "continuar investigacao e nao alterar marketplace"
            risk = intelligence.severity

        return ActionIntent(
            intent_type="intelligence_recommendation",
            target=f"{signal.marketplace}:{signal.entity_type}:{signal.entity_id}",
            recommendation=recommendation,
            autonomy_level=autonomy,
            risk=risk,
            reversible=True,
            direct_marketplace_write=False,
            requires_action_gateway=True,
            requires_human_approval=human,
            rationale=f"{validation.state.value}:{validation.reason}; prediction={prediction.confidence:.2f}",
        )


class SovereignCognitiveAuditor:
    version = "sovereign-cognitive-auditor@1.0.0"

    def audit(
        self,
        validation: ValidationVerdict,
        intelligence: IntelligenceAssessment,
        prediction: Prediction,
        action: ActionIntent,
    ) -> CognitiveAudit:
        issues: list[str] = []
        overconfidence = False
        contradiction = False
        unsafe = False

        if prediction.confidence > validation.confidence + 0.10:
            overconfidence = True
            issues.append("prediction_confidence_exceeds_evidence")
        if validation.state is KnowledgeState.REJECTED and prediction.confidence > 0.35:
            contradiction = True
            issues.append("prediction_based_on_rejected_knowledge")
        if action.direct_marketplace_write:
            unsafe = True
            issues.append("intelligence_core_attempted_direct_marketplace_write")
        if action.autonomy_level in {AutonomyLevel.AUTOMATE_SAFE, AutonomyLevel.LIMITED_AUTONOMY} and action.risk in {
            Severity.HIGH, Severity.CRITICAL
        }:
            unsafe = True
            issues.append("high_risk_autonomy_without_human_gate")
        if intelligence.confidence > 0.95 and validation.state is not KnowledgeState.VALIDATED:
            overconfidence = True
            issues.append("intelligence_overconfidence_without_validation")

        passed = not issues
        return CognitiveAudit(
            passed=passed,
            issues=tuple(issues),
            overconfidence_detected=overconfidence,
            contradiction_detected=contradiction,
            unsafe_authority_detected=unsafe,
            calibration_action=None if passed else "reduce_confidence_or_block_action_until_revalidated",
        )
