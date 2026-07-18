"""Análise de jogos com IA usando saída estruturada.

Provedor padrão: Google Gemini (defina GEMINI_API_KEY).
Alternativa: Claude/Anthropic (defina BETBOT_PROVIDER=claude e ANTHROPIC_API_KEY).

A IA devolve probabilidades por seleção validadas contra o schema `AnaliseJogo`.
O cálculo de valor esperado (EV) é feito aqui no cliente, nunca pela IA.
"""

from __future__ import annotations

import os

from ..models import AnaliseJogo, Jogo, ValueBet

GEMINI_MODEL = "gemini-2.5-flash"
CLAUDE_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """Você é um analista quantitativo de apostas esportivas profissional.

Sua função é estimar probabilidades reais para os mercados de uma partida de futebol,
com base nos dados fornecidos (forma recente, desfalques, estatísticas, contexto e odds).

Regras:
- Estime probabilidades calibradas, não otimistas. Odds de mercado já embutem margem
  da casa; use-as como referência de consenso, mas não as copie.
- Para o mercado 1X2, as probabilidades de casa/empate/fora devem somar aproximadamente 1.
- Se os dados forem insuficientes para um mercado, reduza o campo `confianca` e registre
  o motivo em `alertas` em vez de inventar precisão.
- Justificativas curtas e objetivas: cite o fator decisivo, não escreva ensaios.
- Nunca recomende aposta diretamente; sua saída são probabilidades. A decisão de apostar
  é do sistema de gestão de banca."""


def _prompt_jogo(jogo: Jogo) -> str:
    linhas = [
        f"Partida: {jogo.time_casa} (casa) x {jogo.time_fora} (fora)",
        f"Campeonato: {jogo.campeonato}",
        f"ID do jogo: {jogo.id}",
    ]
    if jogo.data_hora:
        linhas.append(f"Data/hora: {jogo.data_hora}")
    if jogo.contexto:
        linhas.append(f"\nContexto e estatísticas:\n{jogo.contexto}")
    if jogo.odds:
        linhas.append("\nOdds atuais do mercado:")
        for o in jogo.odds:
            linhas.append(f"- {o.mercado.value} / {o.selecao}: {o.odd:.2f}")
    linhas.append(
        "\nEstime as probabilidades para cada seleção listada nas odds acima "
        "(e apenas para elas), preenchendo o schema pedido. Use exatamente os mesmos "
        "valores de `mercado` e `selecao` das odds."
    )
    return "\n".join(linhas)


class Analisador:
    """Fachada única de análise; escolhe o provedor via BETBOT_PROVIDER."""

    def __init__(self, provider: str | None = None):
        self.provider = (provider or os.environ.get("BETBOT_PROVIDER", "gemini")).lower()

    def analisar(self, jogo: Jogo) -> AnaliseJogo:
        if self.provider == "claude":
            analise = self._analisar_claude(jogo)
        else:
            analise = self._analisar_gemini(jogo)
        analise.jogo_id = jogo.id
        return analise

    # ------------------------------------------------------------------
    # Gemini (padrão)
    # ------------------------------------------------------------------

    def _analisar_gemini(self, jogo: Jogo) -> AnaliseJogo:
        from google import genai

        client = genai.Client()  # usa GEMINI_API_KEY do ambiente
        response = client.models.generate_content(
            model=os.environ.get("BETBOT_GEMINI_MODEL", GEMINI_MODEL),
            contents=_prompt_jogo(jogo),
            config={
                "system_instruction": SYSTEM_PROMPT,
                "response_mime_type": "application/json",
                "response_schema": AnaliseJogo,
            },
        )
        analise = response.parsed
        if analise is None:
            raise RuntimeError(
                f"Análise do jogo {jogo.id} não retornou saída estruturada válida (Gemini)"
            )
        return analise

    # ------------------------------------------------------------------
    # Claude (opcional: BETBOT_PROVIDER=claude)
    # ------------------------------------------------------------------

    def _analisar_claude(self, jogo: Jogo) -> AnaliseJogo:
        import anthropic

        client = anthropic.Anthropic()  # usa ANTHROPIC_API_KEY do ambiente
        response = client.messages.parse(
            model=os.environ.get("BETBOT_CLAUDE_MODEL", CLAUDE_MODEL),
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _prompt_jogo(jogo)}],
            output_format=AnaliseJogo,
        )
        analise = response.parsed_output
        if analise is None:
            raise RuntimeError(
                f"Análise do jogo {jogo.id} não retornou saída estruturada válida (Claude)"
            )
        return analise


def encontrar_value_bets(
    jogo: Jogo,
    analise: AnaliseJogo,
    ev_minimo: float = 0.05,
    confianca_minima: float = 0.5,
) -> list[ValueBet]:
    """Cruza probabilidades da IA com as odds e retorna apostas com EV positivo.

    EV por unidade apostada: p * odd - 1. Só passa o corte quem tem
    EV >= ev_minimo E a análise tem confiança >= confianca_minima.
    """
    if analise.confianca < confianca_minima:
        return []

    odds_por_chave = {(o.mercado, o.selecao): o.odd for o in jogo.odds}
    value_bets: list[ValueBet] = []
    for prob in analise.probabilidades:
        odd = odds_por_chave.get((prob.mercado, prob.selecao))
        if odd is None:
            continue
        ev = prob.probabilidade * odd - 1.0
        if ev >= ev_minimo:
            value_bets.append(
                ValueBet(
                    jogo_id=jogo.id,
                    descricao=f"{jogo.time_casa} x {jogo.time_fora} — {prob.mercado.value}/{prob.selecao}",
                    mercado=prob.mercado,
                    selecao=prob.selecao,
                    odd=odd,
                    probabilidade=prob.probabilidade,
                    ev=round(ev, 4),
                    confianca=analise.confianca,
                )
            )
    value_bets.sort(key=lambda v: v.ev, reverse=True)
    return value_bets
