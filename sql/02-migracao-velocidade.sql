-- =====================================================================
--  Migracao: velocidade (mm/s), fator de crista e marca de recuperacao
--
--  Rode SOMENTE se o banco ja existia antes destas colunas. Em banco novo
--  o 01-esquema.sql ja cria tudo e este arquivo nao e necessario.
--
--      psql -U postgres -d insightx -f sql/02-migracao-velocidade.sql
--
--  As colunas em si o 01-esquema.sql acrescenta sozinho (ALTER TABLE ...
--  ADD COLUMN IF NOT EXISTS). O que ele NAO consegue e mexer no agregado
--  continuo: no TimescaleDB um continuous aggregate nao aceita ALTER para
--  ganhar coluna -- so recriando.
--
--  O QUE SE PERDE: nada de dado bruto. O agregado e derivado da tabela
--  'medicoes', entao ele se reconstroi sozinho a partir dela. O limite e a
--  politica de retencao: horas cujas linhas brutas ja foram descartadas
--  (180 dias, no padrao) nao voltam. Se o seu banco ja passou disso e o
--  historico antigo importa, copie medicoes_hora para uma tabela comum
--  antes de rodar:
--
--      CREATE TABLE medicoes_hora_backup AS SELECT * FROM medicoes_hora;
-- =====================================================================

BEGIN;

ALTER TABLE medicoes ADD COLUMN IF NOT EXISTS vibracao_vel_mm_s     DOUBLE PRECISION;
ALTER TABLE medicoes ADD COLUMN IF NOT EXISTS vibracao_vel_max_mm_s DOUBLE PRECISION;
ALTER TABLE medicoes ADD COLUMN IF NOT EXISTS vibracao_crista       DOUBLE PRECISION;
ALTER TABLE medicoes ADD COLUMN IF NOT EXISTS vibracao_crista_max   DOUBLE PRECISION;
ALTER TABLE medicoes ADD COLUMN IF NOT EXISTS recuperada BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;

-- O DROP do agregado tem de ficar fora da transacao acima: o TimescaleDB
-- recusa dropar um continuous aggregate dentro de um bloco que ja mexeu na
-- hypertable de origem.
DROP MATERIALIZED VIEW IF EXISTS medicoes_hora CASCADE;

CREATE MATERIALIZED VIEW medicoes_hora
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
    avg(vibracao_vel_mm_s)           AS vibracao_vel_mm_s,
    max(vibracao_vel_max_mm_s)       AS vibracao_vel_max_mm_s,
    avg(vibracao_crista)             AS vibracao_crista,
    max(vibracao_crista_max)         AS vibracao_crista_max,
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

-- Preenche o agregado com o historico que ainda existe na tabela bruta.
-- Sem isto ele so passaria a valer para o dado NOVO, e os graficos de
-- janela longa ficariam vazios ate acumular semanas.
CALL refresh_continuous_aggregate('medicoes_hora', NULL, NULL);

-- A view e derivada; recriar e barato e garante as colunas novas.
DROP VIEW IF EXISTS vw_medicoes;
CREATE VIEW vw_medicoes AS
SELECT m.ts,
       m.device_id,
       COALESCE(a.ativo, m.ativo)  AS ativo,
       COALESCE(a.parte, m.parte)  AS parte,
       a.tag_inversor,
       a.local,
       m.temperatura_c, m.temperatura_max_c,
       m.vibracao_rms_g, m.vibracao_max_g,
       m.vibracao_vel_mm_s, m.vibracao_vel_max_mm_s,
       m.vibracao_crista, m.vibracao_crista_max,
       m.recuperada,
       m.corrente_a, m.corrente_max_a,
       a.corrente_nominal_a,
       CASE WHEN a.corrente_nominal_a > 0
            THEN 100.0 * m.corrente_a / a.corrente_nominal_a END AS carga_pct,
       m.tensao_v, m.frequencia_hz, m.rodando, m.estado
FROM medicoes m
LEFT JOIN ativos a USING (device_id);
