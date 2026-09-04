extends CharacterBody2D
# Jogador controlável.
#   Movimento: teclas W A S D
#   Mira:      posição do mouse
#   Atirar:    botão esquerdo do mouse (segurar dispara em rajada)

const VELOCIDADE := 300.0        # pixels por segundo
const RAIO := 24.0               # tamanho do corpo (círculo)
const COOLDOWN_TIRO := 0.20      # segundos entre um tiro e outro

var _tempo_ate_proximo_tiro := 0.0
var cor := Color(0.25, 0.6, 1.0) # azul

func _ready() -> void:
	# Cria a área de colisão do corpo (um círculo).
	var forma := CircleShape2D.new()
	forma.radius = RAIO
	var col := CollisionShape2D.new()
	col.shape = forma
	add_child(col)

func _physics_process(delta: float) -> void:
	# --- Movimento ---
	var direcao := Vector2.ZERO
	if Input.is_physical_key_pressed(KEY_W): direcao.y -= 1
	if Input.is_physical_key_pressed(KEY_S): direcao.y += 1
	if Input.is_physical_key_pressed(KEY_A): direcao.x -= 1
	if Input.is_physical_key_pressed(KEY_D): direcao.x += 1
	velocity = direcao.normalized() * VELOCIDADE
	move_and_slide()

	# --- Tiro ---
	_tempo_ate_proximo_tiro -= delta
	if Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT) and _tempo_ate_proximo_tiro <= 0.0:
		_atirar()
		_tempo_ate_proximo_tiro = COOLDOWN_TIRO

	queue_redraw()  # redesenha para o "canhão" acompanhar o mouse

func _atirar() -> void:
	var alvo := get_global_mouse_position()
	var dir := (alvo - global_position).normalized()
	var bala: Area2D = load("res://Bala.gd").new()
	bala.global_position = global_position + dir * (RAIO + 6.0)
	bala.direcao = dir
	get_parent().add_child(bala)

func _draw() -> void:
	# Corpo do jogador
	draw_circle(Vector2.ZERO, RAIO, cor)
	# "Canhão" apontando para o mouse
	var dir := (get_global_mouse_position() - global_position).normalized()
	draw_line(Vector2.ZERO, dir * (RAIO + 14.0), Color.WHITE, 5.0)
