---
name: insightx-config-pela-interface
description: InsightX — usuário quer toda configuração feita pela interface do painel (menus/submenus), edição manual de arquivo "quase zero"
metadata:
  type: feedback
---

No InsightX (repo iot-monitoramento), tudo que hoje exige editar arquivo ou terminal no gateway deve migrar para a interface do painel, com menus e submenus. O usuário disse (2026-09-23): "quero muito automatizar tudo que dependa de edição manual ... se caso tiver alguma config que precise de adição em arquivos temos que deixar quase 0".

**Why:** tornar o produto profissional e fácil de comissionar; ele não tinha percebido o volume de edição manual até ver o inventário.

**How to apply:** ao criar qualquer config nova, projetar primeiro como ela é feita pela tela (com validação à prova de erro — ele elogiou a recusa de IP/endereço repetido). Arquivo de config só como destino escrito pelo painel ou gerado pelo setup, nunca como passo manual. Plano em 5 fases iniciado em 2026-09-23: fase 1 (serviço único + catalogo.json) feita; faltam menu Inversores, senha única nas telas de configuração, "testar conexão", e automatizar credenciais MQTT/banco no Node-RED via setup. Siemens fora por ora; PowerFlex da fábrica são só 525 (inclusive encadeados em Multi-Drive).
