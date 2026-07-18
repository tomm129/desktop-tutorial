# BetBot — Bot de apostas esportivas com IA

Bot que usa IA (Google **Gemini** por padrão, Claude opcional) para analisar jogos de
futebol, estimar probabilidades reais, identificar **value bets** e:

1. Gerar um **cartão de apostas** (bilhete em JSON + texto formatado); ou
2. **Apostar direto na conta** via **Betfair Exchange API** (uma das poucas casas
   com API oficial de apostas);

com **gestão de banca** integrada: staking por Kelly fracionado, stop-loss/stop-win
diários, limite de exposição e histórico completo em SQLite.

> ⚠️ **Aviso**: aposta esportiva envolve risco real de perda. Este bot é uma
> ferramenta de apoio — nenhuma IA garante lucro. Aposte apenas o que pode perder,
> respeite os limites da gestão de banca e a legislação do seu país (no Brasil,
> apenas casas licenciadas pelo Ministério da Fazenda).

## Como funciona

```
jogos.json ──▶ IA (Gemini) ──▶ probabilidades por mercado
                                    │
                     EV = prob × odd − 1  (calculado no código, não pela IA)
                                    │
                        value bets (EV ≥ 5%, confiança ≥ 50%)
                                    │
                 gestão de banca (Kelly ¼, tetos, stop-loss)
                                    │
              ┌─────────────────────┴──────────────────────┐
        cartao.json                              Betfair API (dry-run
        (cartão de apostas)                      por padrão; --real p/ valer)
```

A IA **não decide** quanto apostar — ela só estima probabilidades. Stake e
bloqueios são responsabilidade do gestor de banca, no código.

## Instalação (rodar na sua máquina)

Requisitos: [Python 3.10+](https://www.python.org/downloads/) e Git.

```bash
# 1. clonar o repositório neste branch
git clone -b claude/sports-betting-ai-bot-oqmzle https://github.com/tomm129/desktop-tutorial.git betbot
cd betbot

# 2. instalar as dependências
pip install -r requirements.txt

# 3. configurar as chaves
cp .env.example .env     # no Windows: copy .env.example .env
# edite o .env e preencha:
#   GEMINI_API_KEY  -> grátis em https://aistudio.google.com/apikey
#   ODDS_API_KEY    -> grátis em https://the-odds-api.com (p/ modo teste)
```

O bot carrega o `.env` automaticamente ao rodar — basta preencher e usar.

## Uso

```bash
# 1. registrar sua banca inicial
python betbot.py banca --depositar 500

# 2. analisar os jogos e gerar o cartão
python betbot.py analisar exemplos/jogos.json

# 3. ver o cartão
python betbot.py cartao cartao.json

# 4a. simular envio para a Betfair (não toca na conta)
python betbot.py apostar cartao.json

# 4b. apostar DE VERDADE (pede confirmação digitada)
python betbot.py apostar cartao.json --real

# 5. gestão de banca
python betbot.py banca                              # status
python betbot.py banca --historico                  # últimas apostas
python betbot.py banca --liquidar 3 --resultado ganha
```

## Modo teste (medir a acertividade sem apostar)

O modo teste busca os jogos do dia automaticamente, registra as previsões da IA
(**sem apostar nada**) e depois confere os resultados reais:

```bash
# 1. registrar as previsões dos jogos de hoje (ex.: Série B)
python betbot.py teste --liga serie-b

# 2. depois que os jogos terminarem (ou no dia seguinte):
python betbot.py teste --liga serie-b --conferir

# ver o relatório a qualquer momento
python betbot.py teste --relatorio
```

O relatório mostra a taxa de acerto do palpite principal (1X2), a taxa de acerto
das value bets e o **ROI simulado** com stake fixa — rode por 2–4 semanas antes de
considerar apostar dinheiro real. Ligas disponíveis: `serie-a`, `serie-b`,
`premier-league`, `la-liga`, `libertadores`.

Requer `ODDS_API_KEY` no `.env` — chave **gratuita** (500 requisições/mês) em
<https://the-odds-api.com>.

> Nota: no plano gratuito da The Odds API os jogos vêm com as odds, mas **sem
> estatísticas da temporada** — a IA usa o conhecimento que tem dos times e sinaliza
> confiança menor quando estiver desatualizada. A acertividade real tende a melhorar
> se você enriquecer o campo `contexto` com dados atuais.

### Formato do `jogos.json`

Veja `exemplos/jogos.json`. Cada jogo leva times, campeonato, um campo livre
`contexto` (forma recente, desfalques, estatísticas — quanto mais, melhor a análise)
e as `odds` que a casa está oferecendo. Mercados suportados: `1X2`, `BTTS`,
`OVER_UNDER`, `DUPLA_CHANCE`.

## Gestão de banca (padrões conservadores)

| Regra | Valor padrão |
|---|---|
| Staking | Kelly fracionado (¼ do Kelly) |
| Teto por aposta | 5% da banca |
| Stop-loss diário | −10% da banca |
| Stop-win diário | +20% da banca |
| Exposição máxima em apostas abertas | 15% da banca |

Os valores ficam em `ConfigBanca` (`src/betbot/bankroll/manager.py`).

## Apostar por API — Betfair

A Betfair Exchange tem API oficial e documentada (API-NG). Você precisa de:

1. Conta Betfair verificada;
2. Uma **Application Key** (criada em <https://developer.betfair.com>);
3. Usuário/senha no `.env` — ou, melhor para bots, **login por certificado**
   (`BETFAIR_CERT_FILE`/`BETFAIR_KEY_FILE`).

Por segurança o comando `apostar` roda **sempre em simulação (dry-run)**, mostrando
exatamente o que seria enviado. Só com `--real` + confirmação digitada as ordens
vão para a exchange. A maioria das outras casas **não** oferece API pública de
apostas — para elas, use o cartão gerado e faça a aposta manualmente.

## Trocar o provedor de IA

- Padrão: **Gemini** (`GEMINI_API_KEY`), modelo `gemini-2.5-flash` (rápido e barato).
- Claude: `BETBOT_PROVIDER=claude` + `ANTHROPIC_API_KEY` + `pip install anthropic`.
