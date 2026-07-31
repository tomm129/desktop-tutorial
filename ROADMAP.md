# 🚀 ROADMAP CRYPTO BOT — Versão Produtiva
## Documento de Trabalho | Última atualização: 30/07/2026

---

## 📌 VISÃO GERAL

> **O que temos de valioso:** Arquitetura plugável com ensemble + recalibração aprendida.  
> **O que nos mata:** Dados insuficientes, voters clichês, ausência de pipeline 24/7.  
> **Objetivo deste roadmap:** Transformar o framework arquitetural em um sistema de trading com edge mensurável, fase por fase, sem ilusões.

---

## 🎯 PRINCÍPIOS NÃO NEGOCIÁVEIS

1. **Sem dados, não há decisão.** 5.000+ candles é o mínimo para qualquer otimização.
2. **Baseline antes de inovação.** Só substitui voter clichê depois de medir seu desempenho real.
3. **Testnet antes de real.** Nenhuma ordem com dinheiro vivo sem 2 semanas de execução limpa em testnet.
4. **Edge pequeno e persistente > Edge grande e imaginário.**
5. **Logs são ativos.** Tudo que não é medido não existe.

---

## 📊 FASES DO ROADMAP

---

### 🔷 FASE 0 — FUNDAÇÃO (Semana 1-2)
**Objetivo:** Subir infraestrutura de coleta contínua. Zero execução de ordens.

| # | Tarefa | Status | Entregável |
|---|--------|--------|------------|
| 0.1 | Implementar `cryptobot_loop.py` | ⬜ TODO | Script Python rodando em loop infinito |
| 0.2 | Coletar candles 15m (OHLCV) de BTC, ETH, SOL | ⬜ TODO | SQLite/Parquet com schema padronizado |
| 0.3 | Logar sinais do ensemble a cada 15min (sem executar) | ⬜ TODO | Arquivo de logs com timestamp + sinal + confiança |
| 0.4 | Subir em VPS ou rodar local com `nohup`/`systemd` | ⬜ TODO | Processo estável 24/7 |
| 0.5 | Implementar health check + alerta (Telegram/Discord) se o loop morrer | ⬜ TODO | Notificação em caso de falha |
| 0.6 | Criar dashboard simples (HTML/JS) lendo o SQLite | ⬜ TODO | Página web mostrando candles + sinais históricos |

**Métrica de sucesso:**  
- [ ] 2 semanas de coleta ininterrupta  
- [ ] Zero gaps de candles  
- [ ] Logs com pelo menos 1.344 entradas (96 candles/dia × 14 dias)

**O que REMOVE:** Launcher one-shot atual.  
**O que MELHORA:** Separar coletor / analisador / executor em módulos independentes.

---

### 🔷 FASE 1 — PIPELINE DE DADOS ROBUSTO (Semana 3-4)
**Objetivo:** Garantir qualidade, integridade e acessibilidade dos dados.

| # | Tarefa | Status | Entregável |
|---|--------|--------|------------|
| 1.1 | Migrar de SQLite para TimescaleDB ou DuckDB (melhor para time-series) | ⬜ TODO | Banco otimizado para queries temporais |
| 1.2 | Implementar validação de candles (checar gaps, OHLCV inconsistente, volume zero) | ⬜ TODO | Script de sanity check rodando diariamente |
| 1.3 | Adicionar retries com backoff exponencial na coleta da API | ⬜ TODO | Resiliência contra rate limits e instabilidade |
| 1.4 | Versionar schema dos dados (migrations) | ⬜ TODO | Controle de versão do banco |
| 1.5 | Backup automático diário dos dados | ⬜ TODO | Snapshot diário em cloud/local secundário |
| 1.6 | Documentar schema e APIs utilizadas | ⬜ TODO | README técnico atualizado |

**Métrica de sucesso:**  
- [ ] 100% de uptime na coleta  
- [ ] Zero candles corrompidos  
- [ ] Tempo de recuperação após falha < 5 minutos

**O que REMOVE:** Dependência de arquivos JSON soltos (`pesos_par.json` gerado à mão).  
**O que MELHORA:** Pipeline de dados torna-se um produto independente e testável.

---

### 🔷 FASE 2 — MULTI-TIMEFRAME + BASELINE (Semana 5-8)
**Objetivo:** Adicionar confluência temporal e estabelecer baseline dos voters atuais.

| # | Tarefa | Status | Entregável |
|---|--------|--------|------------|
| 2.1 | Coletar candles 1h em paralelo ao 15m | ⬜ TODO | Dados dual-timeframe no banco |
| 2.2 | Implementar lógica de confluência: sinal só válido se 15m E 1h concordam | ⬜ TODO | Novo módulo de confluência |
| 2.3 | Rodar voters clichês (Anticipation, RSI, Bollinger, MA Cross) por 4 semanas | ⬜ TODO | Baseline de hit rate, Sharpe, drawdown por voter |
| 2.4 | Implementar métricas de backtest em tempo real (walk-forward) | ⬜ TODO | Dashboard com métricas ao vivo |
| 2.5 | Calcular ATR (Average True Range) para cada par | ⬜ TODO | Volatilidade histórica por ativo |

**Métrica de sucesso:**  
- [ ] 5.000+ candles acumulados por par  
- [ ] Hit rate baseline medido com significância estatística  
- [ ] Redução de ~30% no número de sinais (filtro de confluência funcionando)  
- [ ] ATR calculado para BTC, ETH, SOL

**O que REMOVE:** Decisões baseadas apenas em 15m.  
**O que MELHORA:** Position sizing ingênuo de 1% fixo → preparação para sizing por ATR.

---

### 🔷 FASE 3 — NOVOS VOTERS COM EDGE REAL (Semana 9-14)
**Objetivo:** Substituir 2 voters clichês por estratégias com edge não arbitrado.

| # | Tarefa | Status | Entregável |
|---|--------|--------|------------|
| 3.1 | **Voter 1: Funding Rate Spread** | ⬜ TODO | Módulo que lê funding rate da Binance, sinaliza quando funding > 2σ |
| 3.2 | **Voter 2: Order Book Imbalance** | ⬜ TODO | Lê depth API, calcula bid/ask ratio, identifica paredes |
| 3.3 | **Voter 3 (opcional): On-Chain Whale Flow** | ⬜ TODO | Integração com Etherscan/Arkham para grandes movimentos |
| 3.4 | Remover RSI e MA Cross do ensemble | ⬜ TODO | Ensemble com 4 voters: Anticipation + Bollinger + Funding + OB Imbalance |
| 3.5 | Rodar A/B test: ensemble novo vs. baseline por 2 semanas | ⬜ TODO | Relatório comparativo de hit rate e P&L simulado |
| 3.6 | Recalibrar pesos do ensemble com grid search nos novos voters | ⬜ TODO | `pesos_par.json` gerado automaticamente com dados reais |

**Métrica de sucesso:**  
- [ ] Hit rate do ensemble novo > hit rate baseline (com significância estatística)  
- [ ] P&L simulado positivo em pelo menos 1 par  
- [ ] Grid search rodando em 5.000+ candles sem overfitting óbvio

**O que REMOVE:** RSI e MA Cross (voters de 1998, edge arbitrado).  
**O que MELHORA:** Ensemble agora explora ineficiências reais do mercado crypto.

---

### 🔷 FASE 4 — MULTI-PAR + GESTÃO DE PORTFÓLIO (Semana 15-18)
**Objetivo:** Escalar para 3 pares com gestão de risco integrada.

| # | Tarefa | Status | Entregável |
|---|--------|--------|------------|
| 4.1 | Ativar BTC/USDT + ETH/USDT + SOL/USDT simultaneamente | ⬜ TODO | 3 pares coletando e sinalizando |
| 4.2 | Implementar position sizing por ATR: stake menor para pares mais voláteis | ⬜ TODO | Fórmula: `stake = (risco_total × capital) / (ATR × multiplicador)` |
| 4.3 | Implementar gestão de portfólio: limite de exposição total (ex: max 2 posições simultâneas) | ⬜ TODO | Regra de não sobreposição em dumps macro |
| 4.4 | Implementar correlação entre pares: se BTC e ETH > 0.85 de correlação, não abrir ambos long | ⬜ TODO | Matriz de correlação rolling 7 dias |
| 4.5 | Adicionar "wild card": 4º par com convicção (LINK, AVAX, etc.) | ⬜ TODO | 4º par ativo com dados mínimos de 2 semanas |

**Métrica de sucesso:**  
- [ ] Drawdown máximo < 5% em simulação  
- [ ] Exposição correlacionada < 30% do tempo  
- [ ] Position sizing ajusta corretamente: SOL recebe stake menor que BTC

**O que REMOVE:** Risco 1% fixo por par.  
**O que MELHORA:** O ensemble vira um sistema de portfólio, não 3 bots isolados.

---

### 🔷 FASE 5 — EXECUÇÃO EM TESTNET (Semana 19-22)
**Objetivo:** Testar execução real de ordens sem risco de capital.

| # | Tarefa | Status | Entregável |
|---|--------|--------|------------|
| 5.1 | Implementar executor com retry + backoff exponencial | ⬜ TODO | `create_market_buy_order` tolera falhas de rede |
| 5.2 | Implementar slippage tracking: logar preço esperado vs. executado | ⬜ TODO | Métrica de slippage por par e horário |
| 5.3 | Rodar em testnet da Binance por 2 semanas | ⬜ TODO | Ordens reais em ambiente de sandbox |
| 5.4 | Implementar circuit breaker: pausa automática após 3 erros consecutivos | ⬜ TODO | Proteção contra loops de falha |
| 5.5 | Implementar logging de execução: preenchimento, latência, rejeições | ⬜ TODO | Audit trail completo de cada ordem |
| 5.6 | Simular P&L real considerando taxas (maker/taker) e slippage | ⬜ TODO | P&L "líquido" vs. P&L teórico |

**Métrica de sucesso:**  
- [ ] 100% das ordens executadas ou rejeitadas com motivo claro  
- [ ] Latência média < 2s entre sinal e ordem  
- [ ] Slippage médio < 0.1% em condições normais  
- [ ] Zero ordens "perdidas" por falha de rede

**O que REMOVE:** Executor ingênuo sem retry.  
**O que MELHORA:** Sistema de execução robusto, pronto para produção.

---

### 🔷 FASE 6 — PRODUÇÃO (Semana 23+)
**Objetivo:** Trading com capital real. **SÓ APÓS TODAS AS FASES ANTERIORES.**

| # | Tarefa | Status | Entregável |
|---|--------|--------|------------|
| 6.1 | Capital inicial pequeno (ex: R$ 500-1000) | ⬜ TODO | Conta real com risco limitado |
| 6.2 | Limitador diário: stop de perda máxima (ex: -2% do capital) | ⬜ TODO | Circuit breaker de capital |
| 6.3 | Relatório semanal automatizado: P&L, hit rate, drawdown, métricas de execução | ⬜ TODO | Email/relatório gerado automaticamente |
| 6.4 | Revisão mensal: analisar trades, ajustar voters, recalibrar pesos | ⬜ TODO | Processo contínuo de melhoria |
| 6.5 | Escalar capital gradualmente (só aumenta se 2 meses consecutivos no verde) | ⬜ TODO | Regra de escalada disciplinada |

**Métrica de sucesso:**  
- [ ] 2 meses consecutivos de P&L positivo em testnet antes de tocar em real  
- [ ] Drawdown máximo respeitado  
- [ ] Processo de revisão mensal documentado e seguido

**O que REMOVE:** Expectativa de "botar pra fazer dinheiro" imediatamente.  
**O que MELHORA:** Sistema maduro, data-driven, com edge mensurável.

---

## 🗑️ O QUE SERÁ REMOVIDO

| Item | Motivo | Fase de remoção |
|------|--------|-----------------|
| Launcher one-shot | Não coleta dados continuamente | Fase 0 |
| Voters RSI e MA Cross | Edge arbitrado há décadas | Fase 3 |
| Position sizing 1% fixo | Ignora volatilidade do par | Fase 4 |
| Executor sem retry | Perde ordens em falha de rede | Fase 5 |
| Decisões em timeframe único (15m) | Cego a movimentos macro | Fase 2 |
| `pesos_par.json` manual | Overfitting em 200 candles | Fase 3 |
| Expectativa de lucro imediato | Não há edge validado ainda | Fase 6 |

---

## 🆕 O QUE SERÁ IMPLEMENTADO

| Item | Valor | Fase |
|------|-------|------|
| `cryptobot_loop.py` 24/7 | Dados contínuos, baseline real | Fase 0 |
| Multi-timeframe (15m + 1h) | Filtro de ruído, melhora hit rate | Fase 2 |
| Funding Rate Spread | Edge não arbitrado em crypto | Fase 3 |
| Order Book Imbalance | Sinal localizado, difícil de arbitrar | Fase 3 |
| Position sizing por ATR | Risco real igual entre pares | Fase 4 |
| Gestão de portfólio | Proteção em dumps macro | Fase 4 |
| Executor com retry | Confiabilidade na execução | Fase 5 |
| Dashboard de monitoramento | Visibilidade total do sistema | Fase 0-1 |

---

## 🛠️ STACK TECNOLÓGICO SUGERIDO

| Camada | Tecnologia | Justificativa |
|--------|-----------|---------------|
| Coleta | Python + CCXT + asyncio | API unificada, async para múltiplos pares |
| Banco | DuckDB (local) → TimescaleDB (cloud) | Time-series otimizado, SQL familiar |
| Orquestração | `systemd` (VPS) ou Docker | Resiliência, fácil deploy |
| Dashboard | Streamlit ou Dash | Rápido, Python-native, bom para protótipos |
| Alertas | Telegram Bot API | Gratuito, confiável, fácil integração |
| Versionamento | Git + GitHub | Código, dados (DVC), e configs |
| Testnet | Binance Testnet | Sandbox realista, gratuito |

---

## ⚠️ RISCOS E MITIGAÇÕES

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| API da exchange cai durante coleta | Média | Alto | Retry + backoff + alerta imediato |
| Overfitting no grid search | Alta | Alto | Walk-forward validation, nunca otimizar no mesmo set |
| Slippage em alta volatilidade | Média | Médio | Sizing por ATR, evitar horários de baixa liquidez |
| Correlação alta entre pares em crash | Alta | Alto | Gestão de portfólio com limite de exposição |
| Vazamento de API key | Baixa | Crítico | Secrets management, nunca commitar keys |
| Burnout / abandono do projeto | Média | Alto | Fases curtas (2-4 semanas), milestones claros, celebrar pequenas vitórias |

---

## 📈 MÉTRICAS NORTE-ESTRELAS

| Métrica | Alvo Fase 2 | Alvo Fase 5 | Alvo Fase 6 |
|---------|-------------|-------------|-------------|
| Candles acumulados | 5.000+ | 10.000+ | Contínuo |
| Hit rate (baseline) | ~45-50% | — | — |
| Hit rate (ensemble novo) | — | > 55% | > 55% |
| Sharpe ratio | — | > 1.0 | > 1.2 |
| Max drawdown | — | < 5% | < 5% |
| Uptime da coleta | 99% | 99.5% | 99.9% |
| Latência sinal → ordem | — | < 2s | < 1s |

---

## ✅ CHECKLIST DE READINESS POR FASE

### Fase 0 está PRONTA quando:
- [ ] Loop rodando 24/7 há 14 dias sem interrupção
- [ ] SQLite com schema válido e dados limpos
- [ ] Dashboard mostrando candles + sinais em tempo real
- [ ] Alerta funciona se o loop morrer

### Fase 3 está PRONTA quando:
- [ ] 5.000+ candles por par
- [ ] Funding Rate e OB Imbalance votando
- [ ] A/B test mostra melhora estatística vs. baseline
- [ ] Grid search automático funciona

### Fase 6 está AUTORIZADA quando:
- [ ] 2 meses de testnet com P&L positivo
- [ ] Executor com retry testado em 100+ ordens
- [ ] Gestão de portfólio funcionando em simulação
- [ ] Revisão mensal documentada e aprovada

---

## 🎯 PRÓXIMO PASSO IMEDIATO

> **Implementar Fase 0.1: `cryptobot_loop.py`**  
> Subir o loop de coleta 24/7. Tudo o resto depende disso.

---

*Roadmap construído com honestidade. Sem atalhos. Sem ilusões. Só dados, edge e execução.*
