extends SceneTree
# Renderiza modelos 3D (KayKit, CC0) nas folhas de sprite 2D que o jogo usa.
#
# POR QUE: e a tecnica do Diablo 1 e 2 -- modelar e animar em 3D, guardar o
# resultado como sprite. Resolve de uma vez o que nos travou com arte 2D:
#   - quantos quadros quisermos, sem cota de servico nenhum
#   - as 8 direcoes SEMPRE saem, porque a camera e nossa
#   - a arma fica na mao, porque o modelo e riggado
#   - da para tirar quadros de dano e de morte, que nunca tivemos
#
# COMO USAR
#   1. Baixe o KayKit Adventurers (CC0) e ponha os .gltf/.glb em arte/3d/
#   2. A Godot precisa IMPORTAR os modelos antes de um script conseguir abrir:
#        Godot.exe --headless --editor --path . --quit
#   3. Renderize:
#        Godot.exe --path . --script res://tools/render3d/Renderizador.gd -- <classe>
#      sem argumento, faz todas as classes que tiverem modelo em arte/3d/.
#
# A saida vai para arte/classes/<classe>/{parado,andar,atacar}.png, no formato
# de sempre: 128x128 por quadro, 8 linhas = 8 direcoes. Depois e so rodar
# tools/gerar_animacoes.py, que nem precisa saber que a arte virou 3D.

const LADO := 128
const DIRECOES := 8
const ESPERA := 3       # quadros de folga para o render 3D ficar pronto

# Qual modelo, e qual animacao dele vira cada estado do jogo. Cada pacote
# nomeia do seu jeito, entao aceitamos varios nomes; se nenhum existir, o
# script LISTA no fim as animacoes que o modelo realmente tem.
const MODELOS := {
	"guerreiro": {"arquivo": "barbarian", "estados": {
		"parado": {"anim": ["Idle"], "quadros": 4},
		"andar": {"anim": ["Walking_A", "Walk"], "quadros": 6},
		"atacar": {"anim": ["1H_Melee_Attack_Chop", "2H_Melee_Attack_Chop", "Attack"], "quadros": 6},
	}},
	"paladino": {"arquivo": "knight", "estados": {
		"parado": {"anim": ["Idle"], "quadros": 4},
		"andar": {"anim": ["Walking_A", "Walk"], "quadros": 6},
		"atacar": {"anim": ["1H_Melee_Attack_Chop", "Attack"], "quadros": 6},
	}},
	"assassino": {"arquivo": "rogue", "estados": {
		"parado": {"anim": ["Idle"], "quadros": 4},
		"andar": {"anim": ["Walking_A", "Walk"], "quadros": 6},
		"atacar": {"anim": ["1H_Melee_Attack_Slice_Diagonal", "1H_Melee_Attack_Chop"], "quadros": 6},
	}},
	"mago": {"arquivo": "mage", "estados": {
		"parado": {"anim": ["Idle"], "quadros": 4},
		"andar": {"anim": ["Walking_A", "Walk"], "quadros": 6},
		"atacar": {"anim": ["Spellcast_Shoot", "Spellcasting", "Attack"], "quadros": 6},
	}},
	"arqueiro": {"arquivo": "ranger", "estados": {
		"parado": {"anim": ["Idle"], "quadros": 4},
		"andar": {"anim": ["Walking_A", "Walk"], "quadros": 6},
		"atacar": {"anim": ["1H_Ranged_Shoot", "Shoot", "Attack"], "quadros": 6},
	}},
}

# --- Camera -----------------------------------------------------------------
# Angulo 3/4 de cima, parecido com o da arte 2D atual, para o chao e as sombras
# continuarem batendo com o resto do jogo.
const ALTURA_DA_CAMERA := 2.5
const DISTANCIA_DA_CAMERA := 3.1
const ALVO_DA_CAMERA := Vector3(0, 0.85, 0)
const TAMANHO_ORTO := 2.45
# Giro para a LINHA 0 ficar de frente para a camera (baixo), que e a convencao
# das nossas folhas. Se sair torto, o conserto e este numero.
const GIRO_INICIAL := 180.0

var _vp: SubViewport
var _pivo: Node3D
var _modelo: Node3D
var _tocador: AnimationPlayer

var _fila := []
var _tarefa := {}
var _capturas := []
var _i := 0
var _espera := 0
var _erros := []
var _desistiu := false

func _initialize() -> void:
	_monta_estudio()
	var pedido := _classe_pedida()
	for classe in MODELOS:
		if pedido != "" and classe != pedido:
			continue
		var caminho := _acha_modelo(MODELOS[classe]["arquivo"])
		if caminho == "":
			_erros.append("%s: nao achei um modelo com %s no nome, dentro de arte/3d/"
				% [classe, MODELOS[classe]["arquivo"]])
			continue
		_fila.append({"classe": classe, "caminho": caminho,
			"estados": MODELOS[classe]["estados"].duplicate(true)})
	if _fila.is_empty():
		print("Nada para renderizar.")
		for e in _erros:
			print("  ", e)
		print("")
		print("Ponha os .gltf/.glb do KayKit em arte/3d/ e rode de novo.")
		print("Basta o nome CONTER: barbarian, knight, rogue, mage ou ranger")
		# quit() ainda deixa passar um _process; sem esta marca a lista de
		# problemas sairia duas vezes.
		_desistiu = true
		quit()

func _classe_pedida() -> String:
	var args := OS.get_cmdline_user_args()
	return args[0] if args.size() > 0 else ""

# Aceita qualquer arquivo que CONTENHA a palavra: os pacotes vem com nomes do
# tipo Rogue_Hooded.gltf ou character_knight.glb.
func _acha_modelo(palavra: String) -> String:
	var dir := DirAccess.open("res://arte/3d")
	if dir == null:
		return ""
	for nome in dir.get_files():
		var n := nome.to_lower()
		if n.ends_with(".import"):
			continue
		if (n.ends_with(".gltf") or n.ends_with(".glb")) and palavra.to_lower() in n:
			return "res://arte/3d/" + nome
	return ""

func _monta_estudio() -> void:
	_vp = SubViewport.new()
	_vp.size = Vector2i(LADO, LADO)
	_vp.transparent_bg = true      # o sprite tem que entrar por cima do chao
	_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(_vp)

	var mundo := Node3D.new()
	_vp.add_child(mundo)
	_pivo = Node3D.new()
	mundo.add_child(_pivo)

	var cam := Camera3D.new()
	# Ortografica: sem perspectiva, os 8 lados saem do mesmo tamanho. Com
	# perspectiva o boneco pareceria crescer nas diagonais.
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = TAMANHO_ORTO
	# look_at() exige o no ja na arvore; Transform3D.looking_at() e so
	# matematica e funciona aqui no _initialize().
	cam.transform = Transform3D(Basis(),
		Vector3(0, ALTURA_DA_CAMERA, DISTANCIA_DA_CAMERA)).looking_at(ALVO_DA_CAMERA, Vector3.UP)
	mundo.add_child(cam)

	var sol := DirectionalLight3D.new()
	sol.rotation_degrees = Vector3(-50, -35, 0)
	sol.light_energy = 1.15
	mundo.add_child(sol)

	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.62, 0.65, 0.74)
	env.ambient_light_energy = 1.0
	we.environment = env
	mundo.add_child(we)

func _process(_d: float) -> bool:
	if _desistiu:
		return true
	if _tarefa.is_empty():
		if not _proxima_tarefa():
			_encerra()
			return true
	if _espera == 0:
		_poe_a_pose()
	_espera += 1
	if _espera > ESPERA:
		_capturas.append(_vp.get_texture().get_image())
		_espera = 0
		_i += 1
		if _i >= DIRECOES * int(_tarefa["quadros"]):
			_salva_folha()
			_tarefa = {}
	return false

func _poe_a_pose() -> void:
	var quadros := int(_tarefa["quadros"])
	var linha := _i / quadros
	var coluna := _i % quadros
	_pivo.rotation_degrees.y = GIRO_INICIAL - linha * 45.0
	# Divide por quadros, e nao por quadros-1, de proposito: assim o ultimo
	# quadro nao repete o primeiro e a animacao em loop nao trava a cada volta.
	var t: float = _tocador.current_animation_length * (float(coluna) / float(quadros))
	_tocador.seek(t, true)

func _proxima_tarefa() -> bool:
	while not _fila.is_empty():
		var trabalho = _fila[0]
		var estados = trabalho["estados"]
		if estados.is_empty():
			_fila.pop_front()
			if _modelo != null:
				_modelo.queue_free()
				_modelo = null
				_tocador = null
			continue
		if _modelo == null and not _carrega(trabalho["caminho"], trabalho["classe"]):
			_fila.pop_front()
			continue
		var estado: String = estados.keys()[0]
		var pedido = estados[estado]
		estados.erase(estado)
		var anim := _acha_animacao(pedido["anim"])
		if anim == "":
			_erros.append("%s/%s: o modelo nao tem nenhuma destas: %s"
				% [trabalho["classe"], estado, str(pedido["anim"])])
			continue
		_tocador.play(anim)
		_tarefa = {"classe": trabalho["classe"], "estado": estado,
			"quadros": pedido["quadros"], "anim": anim}
		_capturas.clear()
		_i = 0
		_espera = 0
		return true
	return false

func _carrega(caminho: String, classe: String) -> bool:
	var cena = load(caminho)
	if cena == null:
		_erros.append("%s: a Godot ainda nao importou %s (rode --headless --editor --quit antes)"
			% [classe, caminho])
		return false
	_modelo = cena.instantiate()
	_pivo.add_child(_modelo)
	_tocador = _acha_tocador(_modelo)
	if _tocador == null:
		_erros.append("%s: este modelo nao tem AnimationPlayer" % classe)
		return false
	return true

func _acha_tocador(no: Node) -> AnimationPlayer:
	if no is AnimationPlayer:
		return no
	for f in no.get_children():
		var achado := _acha_tocador(f)
		if achado != null:
			return achado
	return null

func _acha_animacao(candidatas: Array) -> String:
	var lista := _tocador.get_animation_list()
	for c in candidatas:
		for tem in lista:
			if tem == c:
				return tem
	# Nao achou o nome exato: tenta por pedaco do nome.
	for c in candidatas:
		for tem in lista:
			if String(c).to_lower() in String(tem).to_lower():
				return tem
	return ""

func _salva_folha() -> void:
	var quadros := int(_tarefa["quadros"])
	var folha := Image.create(LADO * quadros, LADO * DIRECOES, false, Image.FORMAT_RGBA8)
	folha.fill(Color(0, 0, 0, 0))
	var vazios := 0
	for k in _capturas.size():
		folha.blit_rect(_capturas[k], Rect2i(0, 0, LADO, LADO),
			Vector2i((k % quadros) * LADO, (k / quadros) * LADO))
		if not _tem_pixel(_capturas[k]):
			vazios += 1
	var pasta := "res://arte/classes/%s" % _tarefa["classe"]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(pasta))
	var saida := "%s/%s.png" % [pasta, _tarefa["estado"]]
	folha.save_png(ProjectSettings.globalize_path(saida))
	var alerta := ""
	if vazios > 0:
		alerta = "   <<< %d QUADROS VAZIOS" % vazios
	print("  %-10s %-7s <- %-32s %dx%d%s"
		% [_tarefa["classe"], _tarefa["estado"], _tarefa["anim"],
		   folha.get_width(), folha.get_height(), alerta])

func _tem_pixel(img: Image) -> bool:
	for y in range(0, img.get_height(), 3):
		for x in range(0, img.get_width(), 3):
			if img.get_pixel(x, y).a > 0.1:
				return true
	return false

func _encerra() -> void:
	if not _erros.is_empty():
		print("")
		print("PROBLEMAS:")
		for e in _erros:
			print("  ", e)
		if _tocador != null:
			print("")
			print("Animacoes que o ultimo modelo carregado tem:")
			for a in _tocador.get_animation_list():
				print("   ", a)
	print("")
	print("Agora rode:  python tools/gerar_animacoes.py")
