extends Node2D
# Cena principal: monta a arena e cria o jogador.
# Por enquanto é tudo local (um jogador). O online vem numa próxima etapa.

func _ready() -> void:
	# --- Fundo da arena ---
	var fundo := ColorRect.new()
	fundo.color = Color(0.12, 0.14, 0.18)   # cinza-azulado escuro
	fundo.size = Vector2(1152, 648)
	add_child(fundo)                          # adicionado primeiro = fica atrás de tudo

	# --- Cria o jogador no centro da tela ---
	var Player := load("res://Player.gd")
	var jogador: CharacterBody2D = Player.new()
	jogador.global_position = Vector2(576, 324)
	add_child(jogador)
