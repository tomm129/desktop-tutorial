extends Node2D
# Bancada de inspeção da arte. NÃO faz parte do jogo — é uma ferramenta.
#
# Mostra um personagem nas 8 direções, com os estados (parado / andando /
# atacando) empilhados, todos animando ao mesmo tempo. É o jeito de julgar uma
# folha de sprite nova sem ter que jogar até o inimigo resolver atacar.
#
# Rodar:
#   Godot.exe --path . -- ver
#   Godot.exe --path . -- ver goblin        (já abre nesse personagem)
#
# Teclas: SETAS trocam de personagem · ESPAÇO liga/desliga o fundo escuro ·
#         G liga/desliga a grade · +/- mudam o zoom

const PERSONAGENS := ["goblin", "guerreiro", "paladino", "clerigo",
	"mago", "arqueiro", "druida", "assassino"]
const ESTADOS := ["parado", "andando", "atacando"]
const NOMES_DAS_DIRECOES := ["baixo", "baixo-esq", "esquerda", "cima-esq",
	"cima", "cima-dir", "direita", "baixo-dir"]

var _qual := 0
var _zoom := 1.6
var _fundo_escuro := true
var _com_grade := true

var _fundo: ColorRect
var _grade: Node2D
var _celulas: Node2D
var _titulo: Label
var _rodape: Label
var _avisos: Label

func _ready() -> void:
	var tela := get_viewport_rect().size

	_fundo = ColorRect.new()
	_fundo.size = tela
	add_child(_fundo)

	_grade = Node2D.new()
	add_child(_grade)

	_celulas = Node2D.new()
	add_child(_celulas)

	_titulo = _texto(Vector2(0, 8), 24, tela.x)
	_titulo.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_avisos = _texto(Vector2(0, tela.y - 74.0), 15, tela.x)
	_avisos.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_rodape = _texto(Vector2(0, tela.y - 30.0), 14, tela.x)
	_rodape.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_rodape.text = "SETAS trocam de personagem  ·  ESPAÇO muda o fundo  ·  G grade  ·  +/- zoom"
	_rodape.modulate = Color(0.7, 0.7, 0.75)

	var args := OS.get_cmdline_user_args()
	for i in PERSONAGENS.size():
		if args.has(PERSONAGENS[i]):
			_qual = i
			break

	_monta()

func _texto(pos: Vector2, tamanho: int, largura: float) -> Label:
	var l := Label.new()
	l.position = pos
	l.size = Vector2(largura, 30)
	l.add_theme_font_size_override("font_size", tamanho)
	add_child(l)
	return l

func _input(evento: InputEvent) -> void:
	if not (evento is InputEventKey) or not evento.pressed or evento.echo:
		return
	match evento.physical_keycode:
		KEY_RIGHT, KEY_DOWN:
			_qual = (_qual + 1) % PERSONAGENS.size()
			_monta()
		KEY_LEFT, KEY_UP:
			_qual = (_qual - 1 + PERSONAGENS.size()) % PERSONAGENS.size()
			_monta()
		KEY_SPACE:
			_fundo_escuro = not _fundo_escuro
			_monta()
		KEY_G:
			_com_grade = not _com_grade
			_monta()
		KEY_EQUAL, KEY_KP_ADD:
			_zoom = min(_zoom + 0.2, 3.0)
			_monta()
		KEY_MINUS, KEY_KP_SUBTRACT:
			_zoom = max(_zoom - 0.2, 0.6)
			_monta()
		KEY_ESCAPE:
			get_tree().quit()

func _monta() -> void:
	for n in _celulas.get_children():
		n.queue_free()
	for n in _grade.get_children():
		n.queue_free()

	# Fundo claro ou escuro: sprite escuro some no escuro e vice-versa, então
	# poder alternar é o que revela contorno perdido.
	_fundo.color = Color(0.09, 0.10, 0.13) if _fundo_escuro else Color(0.62, 0.66, 0.60)

	var classe: String = PERSONAGENS[_qual]
	var quadros: SpriteFrames = load("res://Animacoes_%s.tres" % classe)
	var tela := get_viewport_rect().size

	var estados_que_existem := []
	for estado in ESTADOS:
		if quadros.has_animation("%s_0" % estado):
			estados_que_existem.append(estado)

	var lado: float = 128.0 * _zoom * 0.62
	var vao_x: float = (tela.x - 60.0) / 8.0
	var y0 := 76.0
	var vao_y: float = min(lado + 34.0, (tela.y - y0 - 100.0) / max(estados_que_existem.size(), 1))

	for e in estados_que_existem.size():
		var estado: String = estados_que_existem[e]
		var y: float = y0 + e * vao_y

		var etiqueta := Label.new()
		etiqueta.position = Vector2(6, y + vao_y * 0.4)
		etiqueta.add_theme_font_size_override("font_size", 14)
		etiqueta.text = estado
		etiqueta.modulate = Color(1, 0.85, 0.4)
		_celulas.add_child(etiqueta)

		for d in 8:
			var x: float = 56.0 + d * vao_x + vao_x * 0.5

			if _com_grade:
				var caixa := ColorRect.new()
				caixa.color = Color(1, 1, 1, 0.05)
				caixa.size = Vector2(lado, lado)
				caixa.position = Vector2(x - lado / 2.0, y)
				_grade.add_child(caixa)

			var sprite := AnimatedSprite2D.new()
			sprite.sprite_frames = quadros
			sprite.scale = Vector2.ONE * _zoom * 0.62
			sprite.position = Vector2(x, y + lado * 0.55)
			sprite.play("%s_%d" % [estado, d])
			_celulas.add_child(sprite)

			if e == 0:
				var nome := Label.new()
				nome.position = Vector2(x - vao_x * 0.5, y - 20.0)
				nome.size = Vector2(vao_x, 18)
				nome.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
				nome.add_theme_font_size_override("font_size", 12)
				nome.text = NOMES_DAS_DIRECOES[d]
				nome.modulate = Color(0.75, 0.75, 0.8)
				_celulas.add_child(nome)

	_titulo.text = "%s   (%d de %d)" % [classe.to_upper(), _qual + 1, PERSONAGENS.size()]

	# O que FALTA neste personagem é a informação mais útil da tela.
	var faltando := []
	for estado in ESTADOS:
		if not estado in estados_que_existem:
			faltando.append(estado)
	if faltando.is_empty():
		_avisos.text = "tem os %d estados" % ESTADOS.size()
		_avisos.modulate = Color(0.5, 0.95, 0.6)
	else:
		_avisos.text = "SEM: " + ", ".join(faltando)
		_avisos.modulate = Color(1.0, 0.7, 0.4)
