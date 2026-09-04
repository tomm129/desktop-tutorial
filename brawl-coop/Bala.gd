extends Area2D
# Projétil disparado pelo jogador. Voa em linha reta e some depois de um tempo.

const VELOCIDADE := 750.0
const TEMPO_DE_VIDA := 1.5   # segundos até desaparecer

var direcao := Vector2.RIGHT
var _tempo := 0.0

func _ready() -> void:
	var forma := CircleShape2D.new()
	forma.radius = 6.0
	var col := CollisionShape2D.new()
	col.shape = forma
	add_child(col)

func _process(delta: float) -> void:
	global_position += direcao * VELOCIDADE * delta
	_tempo += delta
	if _tempo >= TEMPO_DE_VIDA:
		queue_free()   # remove a bala da cena

func _draw() -> void:
	draw_circle(Vector2.ZERO, 6.0, Color(1.0, 0.85, 0.2))  # amarelo
