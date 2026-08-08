# Teste de escala do painel — 2026-08-08

O painel foi desenvolvido e demonstrado com **8 dispositivos**. Este teste
respondeu, antes de um cliente responder por nós, o que quebra quando a
planta cresce.

## Como reproduzir

```bash
python tools/gera_planta_teste.py 24            # gera o cadastro grande
python tools/simulador_campo.py --do-cadastro --intervalo 3
# ... olhar todas as telas ...
python tools/gera_planta_teste.py --restaurar   # devolve o cadastro anterior
```

O gerador faz backup do `dados/ativos.json` antes de sobrescrever, e usa
nomes de equipamento de comprimentos diferentes de propósito — é a variação
de largura de texto que quebra layout, não a quantidade.

**Planta usada:** 24 ativos, 45 partes, 45 ESP32 + 32 inversores = **77
dispositivos** (3× o que a demo tinha). Cerca de 1/3 das partes sem
inversor, porque o drive é opcional e a tela precisa aguentar a mistura.

---

## O que quebrou

### Tendências — colapso total ❌ → corrigido

**45 séries no mesmo gráfico.** A legenda tomava três linhas e metade da
altura do plot; as linhas eram indistinguíveis; e como a paleta categórica
tem ~10 matizes, as cores **repetiam** — havia quatro "verdes" diferentes.

Isso viola a regra de que cor categórica se atribui em ordem fixa e **nunca
se cicla**: acima de 8 séries a saída é agrupar, filtrar ou usar small
multiples, jamais gerar mais cores. Mais séries não era mais informação; era
menos.

**Correção:** o painel elege até **8 séries por gráfico**, as de pior estado
primeiro, e o título diz isso (`— até 8 séries, as de pior estado`). Quem
está em crítico é o que interessa acompanhar; o resto tem card e tabela.

Três armadilhas apareceram ao consertar, e valem mais que o conserto:

1. **Desempate instável.** A primeira versão ordenava por "visto por
   último". O `ui-chart` **acumula** séries — uma série que entra fica na
   legenda para sempre. Com 45 dispositivos se revezando a cada ciclo, a
   legenda voltava a crescer sem limite. Desempate por ID resolve: o
   conjunto só muda quando um **estado** muda.

2. **Lista única para dois tipos.** ESP32 e inversores no mesmo ranking
   faria as oito vagas do gráfico de temperatura serem ocupadas por drives,
   que não publicam temperatura — o gráfico ficaria com três linhas sem que
   nada indicasse o porquê. A eleição é separada por tipo.

3. **Tolerância na inicialização.** A guarda original deixava tudo passar
   enquanto a lista de eleitos não existia (os ~2 s até o primeiro ciclo).
   Parece inofensivo, mas os 45 dispositivos que passaram nesse instante
   ficavam na legenda **para sempre**. A guarda é estrita: melhor o gráfico
   vazio por dois segundos.

---

## O que aguentou

| Tela | Com 77 dispositivos |
|---|---|
| **Visão geral** | ✅ 5 cards por linha, alturas casadas, rola sem cortar |
| **Ativos** | ✅ 69 linhas, busca funcionando, hierarquia legível |
| **Detalhe** | ✅ ativo de 3 partes renderiza inteiro |
| **Alarmes** | ✅ 13 eventos, faixa de KPI correta |
| **Cadastro** | ✅ lista longa, rola bem |
| **KPIs** | ✅ 11 normais / 3 atenção / 10 críticos / 32 de 32 inversores |

A parede de cards se comportou melhor do que eu esperava — o `auto-fit` do
grid absorveu o crescimento sem ajuste nenhum.

---

## O que NÃO foi testado

- **Mais de 24 ativos.** Não sei onde está o teto real; 50 ou 100 podem
  revelar outra coisa.
- **Carga no gateway.** 77 dispositivos a cada 3 s são ~26 mensagens/s. O
  Node-RED é laço de eventos de thread única, e a função "montar painel"
  roda a cada 2 s sobre a planta inteira. Não medi CPU nem latência no
  Orange Pi — e é lá que isso pesa, não neste PC.
- **Escrita no banco.** Com 77 dispositivos o `INSERT` por minuto passa a
  ter 77 linhas. Não testado contra PostgreSQL real.
- **Linha do tempo com muitos eventos simultâneos.** O teto de 6 faixas foi
  posto antes deste teste e não foi exercitado a fundo.

O item do gateway é o que eu investigaria primeiro: é o único que degrada
**silenciosamente** — não quebra a tela, só fica lento, e o sintoma aparece
como "o painel está travando" sem apontar a causa.
