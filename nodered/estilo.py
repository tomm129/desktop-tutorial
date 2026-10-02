"""Linguagem visual do painel — a mesma do simulador do PowerFlex.

Duas peças, e nenhuma mexe em logica:

1. PALETA: os tons neutros (fundos, tinta, bordas) e o azul de destaque do
   simulador (tools/simuladores/painel_powerflex.html). O gerador troca os
   tons antigos por estes em TODO o fluxo -- templates, funcoes e tema --,
   entao nenhum template precisa ser reescrito para mudar de cor.
   As cores de STATUS (ok/atencao/critico) e das SERIES dos graficos nao
   entram aqui: foram validadas para daltonismo e contraste e continuam.

2. CSS_SITE: um ui-template de escopo 'site:style', que veste os
   componentes NATIVOS do Dashboard 2.0 (cabecalho, menu, grupos, tabelas,
   botoes, campos). Eram eles que destoavam: os templates proprios ja
   seguiam o estilo, os nativos tinham cara de Material Design.

Reverter: apagar o no 'estilo_site' e esvaziar MAPA.

CUIDADO ao atualizar o @flowfuse/node-red-dashboard: os seletores abaixo
sao classes internas do Vuetify (v-card, v-data-table...). Se uma versao
nova as renomear, o painel continua funcionando, so perde o acabamento --
a auditoria de tela (estilo aplicado?) acusa.
"""

# Tons do simulador. Nomes como no painel_powerflex.html.
FUNDO = "#0e1116"        # --bg
SUPERFICIE = "#161b22"   # --surface   (cartoes, grupos)
SUPERFICIE_2 = "#1c232c" # --surface-2 (hover, campos)
BORDA = "#2a323c"        # --border
LINHA = "#222a33"        # grade e divisorias, um passo abaixo da borda
TINTA = "#e6edf3"        # --text
TINTA_2 = "#8b98a5"      # --muted
TINTA_3 = "#6e7a87"      # entre muted e faint: eixos, rotulos
TINTA_4 = "#5c6773"      # --faint
DESTAQUE = "#2f81f7"     # --accent

# Tom antigo -> tom novo. Aplicado a toda string do fluxo gerado.
MAPA = {
    "#0b0b0c": FUNDO,
    "#151518": SUPERFICIE,
    "#1e1e22": SUPERFICIE_2,
    "#3f3f46": BORDA,
    "#27272a": LINHA,
    "#f4f4f5": TINTA,
    "#a1a1aa": TINTA_2,
    "#71717a": TINTA_3,
    "#52525b": TINTA_4,
    "#3b82f6": DESTAQUE,
}


def aplicar_paleta(valor):
    """Troca os tons antigos pelos novos em qualquer estrutura (str/list/dict)."""
    if isinstance(valor, str):
        for velho, novo in MAPA.items():
            valor = valor.replace(velho, novo).replace(velho.upper(), novo)
        return valor
    if isinstance(valor, list):
        return [aplicar_paleta(v) for v in valor]
    if isinstance(valor, dict):
        return {k: aplicar_paleta(v) for k, v in valor.items()}
    return valor


CSS_SITE = f"""
/* InsightX -- linguagem visual do simulador. Gerado por nodered/estilo.py */
:root {{
  --ix-fundo: {FUNDO}; --ix-sup: {SUPERFICIE}; --ix-sup-2: {SUPERFICIE_2};
  --ix-borda: {BORDA}; --ix-linha: {LINHA};
  --ix-tinta: {TINTA}; --ix-tinta-2: {TINTA_2}; --ix-tinta-4: {TINTA_4};
  --ix-destaque: {DESTAQUE}; --ix-destaque-suave: rgba(47,129,247,.14);
  --ix-raio: 10px;
  --ix-fonte: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}}

/* Fonte: a do sistema, como no simulador (o padrao era Helvetica). */
body, .v-application, .v-application .text-body-1, .v-application .text-h6,
.v-btn, .v-field, .v-list-item-title, .v-toolbar-title, .v-card-title {{
  font-family: var(--ix-fonte) !important;
}}
body, .v-application {{ background: var(--ix-fundo) !important; }}
.nrdb-ui-widget {{ font-variant-numeric: tabular-nums; }}

/* Cabecalho: sem sombra, uma linha fina embaixo -- como o do simulador. */
.v-app-bar {{
  background: var(--ix-fundo) !important;
  border-bottom: 1px solid var(--ix-borda) !important;
  box-shadow: none !important;
}}
.v-app-bar .v-toolbar__content {{ font-weight: 650; letter-spacing: -.01em; }}

/* Menu lateral */
.v-navigation-drawer {{
  background: var(--ix-sup) !important;
  border-right: 1px solid var(--ix-borda) !important;
}}
.v-navigation-drawer .v-list-item {{ border-radius: 8px !important; }}
.v-navigation-drawer .v-list-item--active {{ color: var(--ix-destaque) !important; }}
.v-navigation-drawer .v-list-item--active > .v-list-item__overlay {{
  background: var(--ix-destaque) !important; opacity: .14 !important;
}}

/* Grupos = os cartoes do simulador: superficie, borda fina, titulo discreto */
.nrdb-ui-group > .v-card {{
  background: var(--ix-sup) !important;
  border: 1px solid var(--ix-borda) !important;
  border-radius: var(--ix-raio) !important;
  box-shadow: none !important;
}}
.nrdb-ui-group > .v-card > .v-card-item .v-card-title {{
  font-size: 13px !important; font-weight: 600 !important;
  color: var(--ix-tinta-2) !important; letter-spacing: .01em;
}}

/* Tabelas no estilo do registro do simulador: cabecalho apagado, linhas
   finas, numeros alinhados. */
.v-table.nrdb-table, .nrdb-ui-table .v-table {{ background: transparent !important; }}
.v-data-table th, .v-data-table .v-data-table__th {{
  color: var(--ix-tinta-4) !important; font-weight: 500 !important;
  font-size: 12px !important; text-transform: none !important;
  border-bottom: 1px solid var(--ix-borda) !important;
}}
.v-data-table tbody td {{
  font-size: 13px !important; color: var(--ix-tinta) !important;
  border-bottom: 1px solid var(--ix-linha) !important;
}}
.v-data-table tbody tr:hover td {{ background: var(--ix-sup-2) !important; }}

/* Botoes e campos */
.nrdb-ui-button .v-btn, .nrdb-ui-group .v-btn--variant-flat {{
  text-transform: none !important; letter-spacing: 0 !important;
  border-radius: 8px !important; font-weight: 600 !important;
}}
.v-field {{ border-radius: 8px !important; }}
.v-field--variant-outlined .v-field__outline {{ color: var(--ix-borda) !important; --v-field-border-opacity: 1; }}
.v-field--focused .v-field__outline {{ color: var(--ix-destaque) !important; }}

/* Barra de rolagem discreta */
* {{ scrollbar-width: thin; scrollbar-color: var(--ix-borda) transparent; }}
"""
