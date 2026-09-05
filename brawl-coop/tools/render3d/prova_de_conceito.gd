extends SceneTree
# PROVA: a Godot renderiza 3D nas 8 direcoes e monta a folha no MESMO formato
# que o jogo ja usa (128x128, 8 linhas = 8 direcoes)? Sem Blender, sem PixelLab.
const LADO := 128
const DIRECOES := 8
const QUADROS := 6
const ESPERA := 3          # quadros de folga para o render ficar pronto

var _vp: SubViewport
var _pivo: Node3D
var _capturas := []
var _i := 0                # indice da pose atual
var _espera := 0

func _initialize() -> void:
	_vp = SubViewport.new()
	_vp.size = Vector2i(LADO, LADO)
	_vp.transparent_bg = true      # sem fundo: o sprite entra por cima do chao
	_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(_vp)

	var mundo := Node3D.new()
	_vp.add_child(mundo)

	# Boneco de teste de primitivas (corpo, cabeca e uma "arma" no lado direito)
	# so para provar o mecanismo -- no lugar dele entra o KayKit.
	_pivo = Node3D.new()
	mundo.add_child(_pivo)
	_poe_caixa(_pivo, Vector3(0, 0.55, 0), Vector3(0.45, 1.1, 0.28), Color(0.35, 0.45, 0.85))
	_poe_caixa(_pivo, Vector3(0, 1.32, 0), Vector3(0.36, 0.36, 0.36), Color(0.95, 0.78, 0.60))
	_poe_caixa(_pivo, Vector3(0.42, 0.85, 0.15), Vector3(0.10, 0.9, 0.10), Color(0.9, 0.9, 0.95))

	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = 2.6
	# look_at() exige o no na arvore; Transform3D.looking_at() e matematica pura.
	cam.transform = Transform3D(Basis(), Vector3(0, 2.4, 3.0)) \
		.looking_at(Vector3(0, 0.8, 0), Vector3.UP)
	mundo.add_child(cam)

	var luz := DirectionalLight3D.new()
	luz.rotation_degrees = Vector3(-50, -40, 0)
	mundo.add_child(luz)
	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.62, 0.64, 0.72)
	env.ambient_light_energy = 0.9
	we.environment = env
	mundo.add_child(we)

func _poe_caixa(pai: Node3D, onde: Vector3, tam: Vector3, cor: Color) -> void:
	var m := MeshInstance3D.new()
	var caixa := BoxMesh.new()
	caixa.size = tam
	m.mesh = caixa
	var mat := StandardMaterial3D.new()
	mat.albedo_color = cor
	m.material_override = mat
	m.position = onde
	pai.add_child(m)

func _process(_d: float) -> bool:
	var total := DIRECOES * QUADROS
	if _i >= total:
		_monta_folha()
		return true
	if _espera == 0:
		# Posiciona a pose: a linha gira o pivo, a coluna avanca a animacao.
		var linha := _i / QUADROS
		var coluna := _i % QUADROS
		_pivo.rotation_degrees.y = 180.0 - linha * 45.0
		_pivo.get_child(2).rotation_degrees.x = -40.0 + coluna * 16.0
	_espera += 1
	if _espera > ESPERA:
		_capturas.append(_vp.get_texture().get_image())
		_espera = 0
		_i += 1
	return false

func _monta_folha() -> void:
	var folha := Image.create(LADO * QUADROS, LADO * DIRECOES, false, Image.FORMAT_RGBA8)
	folha.fill(Color(0, 0, 0, 0))
	for k in _capturas.size():
		folha.blit_rect(_capturas[k], Rect2i(0, 0, LADO, LADO),
			Vector2i((k % QUADROS) * LADO, (k / QUADROS) * LADO))
	var saida := ProjectSettings.globalize_path("res://tools/render3d/prova.png")
	folha.save_png(saida)

	var cheios := 0
	var iguais := 0
	for k in _capturas.size():
		if _tem_pixel(_capturas[k]):
			cheios += 1
		if k > 0 and _capturas[k].get_data() == _capturas[k - 1].get_data():
			iguais += 1
	print("folha %dx%d | quadros com desenho: %d/%d | quadros repetidos: %d"
		% [folha.get_width(), folha.get_height(), cheios, _capturas.size(), iguais])
	print("salvo: %s" % saida)

func _tem_pixel(img: Image) -> bool:
	for y in range(0, img.get_height(), 3):
		for x in range(0, img.get_width(), 3):
			if img.get_pixel(x, y).a > 0.1:
				return true
	return false
