"""Identidade visual do painel — InsightX.

Embutidas como data URI, e nao servidas como arquivo, de proposito: assim
a marca acompanha o flows.json sem depender de httpStatic configurado no
destino. Importar o fluxo num Node-RED limpo ja mostra a logo.

TRANSPARENCIA RECONSTRUIDA. O arquivo recebido era JPEG -- formato sem
canal alfa -- entao o xadrez de "fundo transparente" tinha virado pixel de
verdade. A versao com fundo PRETO CHAPADO resolveu: sobre preto,
observado = frente x alfa, entao o alfa e a propria luminancia e a cor de
frente se recupera dividindo por ele. Sem essa divisao as bordas ficam
escurecidas e aparece halo escuro em fundo claro.

Efeito colateral bom: sem o fundo, o PNG comprime muito melhor -- 30 KB
caiu para 6,7 KB no total.

Para trocar a logo: exporte PNG com alfa de verdade, ou sobre preto
chapado, e refaca os data URI.
"""

# Lockup horizontal completo, 243x88. Cabecalho da Visao Geral.
LOGO_LOCKUP = (
    "data:image/png;base64,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"
)

# So o simbolo (fabrica + X + rede), 80x80. App bar.
LOGO_ICONE = (
    "data:image/png;base64,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"
    "A4/gHu6Qn3oKlZQwAAAABJRU5ErkJggg=="
)
