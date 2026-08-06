-- =====================================================================
--  InsightX — esquema do historico  (PostgreSQL + TimescaleDB)
--
--  Rode uma vez, como o usuario dono do banco:
--      psql -U postgres -d insightx -f sql/01-esquema.sql
--
--  O setup_orangepi.sh faz isso sozinho.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ---------------------------------------------------------------------
--  Cadastro de ativos
--
--  Espelha o dados/ativos.json. Existe aqui para o Grafana e o Power BI
--  poderem juntar a TAG e a descricao sem ler arquivo, e para o dia em
--  que o cadastro migrar de vez para o banco.
--
--  A chave e o device_id -- a identidade do HARDWARE. Ativo e parte sao
--  atributos que mudam: trocar um sensor de motor e um UPDATE aqui, sem
--  tocar no historico.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ativos (
    device_id      TEXT PRIMARY KEY,
    tipo           TEXT,              -- 'esp32' | 'inversor'
    ativo          TEXT,              -- 'Caldeira 01'
    parte          TEXT,              -- 'Bomba de alimentacao'
    tag_inversor   TEXT,              -- 'U11'
    local          TEXT,
    corrente_nominal_a  DOUBLE PRECISION,   -- a In da placa
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
--  Medicoes — serie temporal AGREGADA
--
--  POR QUE AGREGADA, E NAO CRUA:
--
--  O campo publica a cada 2s. Com 8 dispositivos isso da 345 mil linhas
--  por dia, 126 milhoes por ano -- gravadas no eMMC de um Orange Pi, que
--  tem ciclos de escrita contados. E ninguem consulta resolucao de 2
--  segundos em cima de meses: consulta tendencia.
--
--  Entao gravamos UMA linha por dispositivo por minuto. Corta o volume
--  por 30 e o dado de tendencia fica igual.
--
--  MAS guardamos MIN e MAX junto da media, e isso nao e detalhe: a media
--  de um minuto ESCONDE o pico de vibracao, que e exatamente o que se
--  esta procurando. Media diz como estava; maximo diz o que aconteceu.
--
--  O campo 'amostras' permite reponderar medias ao reagregar depois --
--  media de medias so e correta quando todas tem o mesmo n.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS medicoes (
    ts             TIMESTAMPTZ NOT NULL,
    device_id      TEXT        NOT NULL,

    -- Denormalizado de proposito: guarda a que ativo o dispositivo
    -- pertencia NAQUELE momento. Se amanha ele for remanejado, a
    -- historia antiga continua contando a verdade do que era entao.
    ativo          TEXT,
    parte          TEXT,

    amostras       INTEGER     NOT NULL DEFAULT 1,

    temperatura_c      DOUBLE PRECISION,
    temperatura_min_c  DOUBLE PRECISION,
    temperatura_max_c  DOUBLE PRECISION,

    vibracao_rms_g     DOUBLE PRECISION,
    vibracao_min_g     DOUBLE PRECISION,
    vibracao_max_g     DOUBLE PRECISION,

    corrente_a         DOUBLE PRECISION,
    corrente_min_a     DOUBLE PRECISION,
    corrente_max_a     DOUBLE PRECISION,

    tensao_v           DOUBLE PRECISION,
    dc_bus_v           DOUBLE PRECISION,
    frequencia_hz      DOUBLE PRECISION,
    rodando            BOOLEAN,

    estado         TEXT        -- normal | atencao | critico | sem_dados
);

SELECT create_hypertable('medicoes', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS medicoes_device_ts   ON medicoes (device_id, ts DESC);
CREATE INDEX IF NOT EXISTS medicoes_ativo_ts    ON medicoes (ativo, ts DESC);

-- ---------------------------------------------------------------------
--  Eventos — transicoes de estado
--
--  Tabela SEPARADA das medicoes de proposito. Um evento nao e uma
--  amostra: tem inicio, fim e duracao, e e consultado por outra pergunta
--  ("quantas paradas neste mes?") do que a serie ("qual a tendencia?").
--
--  Misturar os dois numa tabela so forcaria varrer milhoes de linhas de
--  medicao para achar algumas dezenas de eventos.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eventos (
    id             BIGSERIAL,
    inicio         TIMESTAMPTZ NOT NULL,
    fim            TIMESTAMPTZ,              -- NULL = ainda aberto
    device_id      TEXT,
    ativo          TEXT,
    parte          TEXT,
    estado         TEXT        NOT NULL,     -- atencao | critico | sem_dados
    motivo         TEXT,
    PRIMARY KEY (id, inicio)
);

SELECT create_hypertable('eventos', 'inicio', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS eventos_ativo    ON eventos (ativo, inicio DESC);
CREATE INDEX IF NOT EXISTS eventos_abertos  ON eventos (inicio DESC) WHERE fim IS NULL;

-- ---------------------------------------------------------------------
--  Retencao e compressao
--
--  O detalhe de minuto interessa por algumas semanas; a tendencia longa
--  vive nos agregados continuos abaixo. Sem isso o banco cresce para
--  sempre num equipamento com armazenamento limitado.
-- ---------------------------------------------------------------------
ALTER TABLE medicoes SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id'
);

SELECT add_compression_policy('medicoes', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('medicoes',  INTERVAL '180 days', if_not_exists => TRUE);

-- ---------------------------------------------------------------------
--  Agregado continuo por hora
--
--  E o que o Grafana e o Power BI devem consultar para janelas longas:
--  o TimescaleDB mantem isso atualizado sozinho, e uma consulta de um ano
--  le milhares de linhas em vez de milhoes.
--
--  Note o MAX do maximo, e nao o maximo da media: reagregar preservando
--  o pico e o ponto todo de ter guardado min/max.
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS medicoes_hora
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', ts) AS hora,
    device_id,
    ativo,
    parte,
    sum(amostras)                    AS amostras,
    avg(temperatura_c)               AS temperatura_c,
    min(temperatura_min_c)           AS temperatura_min_c,
    max(temperatura_max_c)           AS temperatura_max_c,
    avg(vibracao_rms_g)              AS vibracao_rms_g,
    max(vibracao_max_g)              AS vibracao_max_g,
    avg(corrente_a)                  AS corrente_a,
    max(corrente_max_a)              AS corrente_max_a,
    avg(tensao_v)                    AS tensao_v,
    avg(frequencia_hz)               AS frequencia_hz
FROM medicoes
GROUP BY hora, device_id, ativo, parte
WITH NO DATA;

SELECT add_continuous_aggregate_policy('medicoes_hora',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE);

-- ---------------------------------------------------------------------
--  Visao pronta para BI
--
--  Junta a TAG e a descricao atuais. O Power BI aponta para ca.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_medicoes AS
SELECT m.ts,
       m.device_id,
       COALESCE(a.ativo, m.ativo)  AS ativo,
       COALESCE(a.parte, m.parte)  AS parte,
       a.tag_inversor,
       a.local,
       m.temperatura_c, m.temperatura_max_c,
       m.vibracao_rms_g, m.vibracao_max_g,
       m.corrente_a, m.corrente_max_a,
       a.corrente_nominal_a,
       -- Corrente em % da nominal: e assim que se compara motores de
       -- porte diferente no mesmo grafico.
       CASE WHEN a.corrente_nominal_a > 0
            THEN 100.0 * m.corrente_a / a.corrente_nominal_a END AS carga_pct,
       m.tensao_v, m.frequencia_hz, m.rodando, m.estado
FROM medicoes m
LEFT JOIN ativos a USING (device_id);
