extends Node2D
# Cena principal. Tem dois momentos:
#   1) ESCOLHA  — você escolhe a sua classe e a do aliado (teclas 1 a 7)
#   2) JOGO     — arena, ondas de inimigos, HUD, inventário e habilidade
#
# A party é de dois e sai toda do mesmo Personagem.gd: o que muda entre você e
# o aliado é só "por_ia", e o que muda entre as classes vem de Classes.gd.
# O online (dois PCs em rede) é outra etapa, ainda não feita.

const INIMIGOS_DA_PRIMEIRA_ONDA := 3
const INIMIGOS_A_MAIS_POR_ONDA := 2
const PAUSA_ENTRE_ONDAS := 2.5
const MARGEM_DE_SPAWN := 40.0
const LONGE_DA_PARTY := 200.0

# Começa com os inimigos neutros: dá para ver o jogo rodando sem morrer.
# A tecla N liga e desliga.
const COMECA_COM_INIMIGOS_NEUTROS := true

const LADO_DO_TILE := 32.0
const LADO_DO_QUADRO := 128       # quadro das folhas de sprite, para o retrato

# Os quatro slots do inventário, na ordem em que aparecem na tela.
# O último é vazio de propósito, para mostrar como fica um slot sem nada.
const ITENS := [
	{"tipo": "kit",     "nome": "Poção de cura (+40 de vida)"},
	{"tipo": "escudo",  "nome": "Escudo (4s sem levar dano)"},
	{"tipo": "turbo",   "nome": "Poção de fogo (6s atacando o dobro)"},
	{"tipo": "estouro", "nome": "Frasco explosivo (60 de dano em volta do alvo)"},
	{"tipo": "veloz",   "nome": "Asas (6s 50% mais rápido)"},
	{"tipo": "foco",    "nome": "Pergaminho (deixa a habilidade pronta na hora)"},
]

var _chao: Node2D          # tiles de grama, sem ordenação
var _arena: Node2D         # tudo que "pisa" no chão, ordenado por Y
var _barras: Node2D        # desenha as barras de vida por cima de tudo
var _jogador: CharacterBody2D
var _aliado: CharacterBody2D

var _estado := "menu"   # menu | entrar_ip | lobby | escolha_sua | escolha_aliado | jogando
var _classe_sua := ""
var _classe_aliado := ""

var _onda := 0
var _vivos := 0
var _tempo_ate_proxima_onda := PAUSA_ENTRE_ONDAS
var _fim_de_jogo := false
var _inimigos_neutros := COMECA_COM_INIMIGOS_NEUTROS
var _slot_escolhido := 0
var _mirando_no_aliado := false

var _camada_jogo: CanvasLayer
var _camada_escolha: CanvasLayer
var _camada_controles: CanvasLayer
var _camada_menu: CanvasLayer
var _camada_lobby: CanvasLayer
var _campo_ip: LineEdit
var _texto_menu: Label
var _lista_lobby: Label
var _dica_lobby: Label
var _sozinho := true   # true = partida local com aliado de IA
# Sincronia da partida em rede
const ENVIOS_DO_JOGADOR := 20.0     # pacotes por segundo do proprio boneco
const ENVIOS_DOS_INIMIGOS := 15.0   # pacotes por segundo da horda (so o anfitriao)
var _t_envio_jogador := 0.0
var _t_envio_inimigos := 0.0
var _proximo_id_inimigo := 1
var _inimigos_por_id := {}          # id de rede -> no (usado nos clientes)
var _linhas_de_controle := {}   # id da acao -> botao que mostra a tecla
var _capturando := ""          # acao esperando o jogador apertar a tecla nova
var _estado_antes_dos_controles := "escolha_sua"
var _aviso_controles: Label
var _titulo_escolha: Label
var _rodape_escolha: Label   # versao e recado do atualizador
var _hud_vida: Label
var _hud_aliado: Label
var _hud_onda: Label
var _hud_inimigos: Label
var _hud_hab: Label
var _hud_aviso: Label
var _fundo_aviso: ColorRect
var _hud_item: Label
var _hud_flash: Label       # avisa qual habilidade acabou de sair
var _tempo_flash := 0.0
var _slots := []
var _slot_hab := {}         # o slot da habilidade (tecla Q)

func _ready() -> void:
	# Continua processando mesmo com a árvore pausada (é assim que o "R" para
	# recomeçar funciona depois do fim de jogo).
	process_mode = Node.PROCESS_MODE_ALWAYS
	add_to_group("main")   # o Personagem e o Inimigo chegam aqui por este grupo

	var tela := get_viewport_rect().size

	# Duas camadas separadas de propósito:
	#  _chao  -> os tiles, na ordem em que foram criados
	#  _arena -> party, inimigos, tiros e itens, com y_sort_enabled
	# Y-sort ordena os filhos pela posição Y, então quem está mais "à frente"
	# (mais embaixo na tela) desenha por cima. Se os tiles ficassem junto,
	# um tile lá de baixo passaria na frente de um personagem lá de cima.
	_chao = Node2D.new()
	add_child(_chao)
	_monta_piso(tela)

	_arena = Node2D.new()
	_arena.y_sort_enabled = true
	add_child(_arena)

	# Camada das barras de vida: entra DEPOIS da arena, entao desenha por
	# cima de todos os personagens. E de la que sai o empilhamento.
	_barras = load("res://BarrasNaTela.gd").new()
	add_child(_barras)

	_monta_hud(tela)
	_monta_escolha(tela)
	_monta_menu(tela)
	_monta_lobby(tela)
	_monta_controles(tela)
	_camada_jogo.visible = false
	_camada_escolha.visible = false
	_talvez_pular_escolha()

# Atalho para testar/tirar print sem passar pela tela de escolha:
#   Godot.exe --path . -- mago clerigo
# O primeiro nome é a sua classe, o segundo é a do aliado.
func _talvez_pular_escolha() -> void:
	var args := OS.get_cmdline_user_args()

	# Atalhos de rede, para testar duas instancias sem clicar em nada:
	#   -- host              abre a sala
	#   -- entrar <ip>       entra na sala de alguem
	#   -- auto              (com host) comeca a partida sozinho depois de 4s
	if args.has("host"):
		var erro: String = Rede.hospedar(_meu_apelido())
		print("[rede] hospedar: %s" % ("ok" if erro == "" else erro))
		_abre_lobby()
		if args.has("auto"):
			get_tree().create_timer(4.0).timeout.connect(func(): Rede.comecar_partida())
		return
	var onde := args.find("entrar")
	if onde >= 0 and onde + 1 < args.size():
		var erro2: String = Rede.entrar(args[onde + 1], _meu_apelido())
		print("[rede] entrar em %s: %s" % [args[onde + 1], "ok" if erro2 == "" else erro2])
		_abre_lobby()
		return

	if args.size() < 2:
		return
	var sua := Classes.ORDEM.find(args[0])
	var aliado := Classes.ORDEM.find(args[1])
	if sua < 0 or aliado < 0:
		push_warning("Classe desconhecida na linha de comando: %s" % str(args))
		return
	# "hostil" como terceiro argumento ja comeca com os inimigos batendo,
	# util para testar o que so aparece quando a vida cai.
	if args.has("hostil"):
		_inimigos_neutros = false
	if args.has("controles"):
		# atalho para conferir a tela de controles sem depender de apertar F1
		call_deferred("_abre_controles")
	_escolhe_classe(sua)
	_escolhe_classe(aliado)

func _monta_piso(tela: Vector2) -> void:
	var textura := load("res://arte/piso2/grama.png")
	var colunas := int(ceil(tela.x / LADO_DO_TILE))
	var linhas := int(ceil(tela.y / LADO_DO_TILE))
	for lin in linhas:
		for col in colunas:
			var chao := Sprite2D.new()
			chao.texture = textura
			chao.centered = false
			chao.position = Vector2(col * LADO_DO_TILE, lin * LADO_DO_TILE)
			# NADA de variacao de brilho por tile: este tile e uma cor chapada,
			# e mesmo 1,5% de diferenca ja aparece como xadrez na tela. Fica so
			# um escurecido igual para todos, que faz os personagens saltarem
			# do fundo.
			chao.modulate = Color(0.78, 0.78, 0.78)
			_chao.add_child(chao)

# --- Escolha de classe ------------------------------------------------------

func _monta_escolha(tela: Vector2) -> void:
	_camada_escolha = CanvasLayer.new()
	_camada_escolha.layer = 20
	add_child(_camada_escolha)

	var veu := ColorRect.new()
	veu.color = Color(0, 0, 0, 0.72)
	veu.size = tela
	_camada_escolha.add_child(veu)

	_titulo_escolha = Label.new()
	_titulo_escolha.position = Vector2(0, 56)
	_titulo_escolha.size = Vector2(tela.x, 40)
	_titulo_escolha.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_titulo_escolha.add_theme_font_size_override("font_size", 30)
	_camada_escolha.add_child(_titulo_escolha)

	# Cards com o RETRATO EMOLDURADO de cada classe (arte/retratos). A moldura
	# ja da o enquadramento, entao o card nao precisa de caixa em volta -- so de
	# um fundo atras do texto, para ele nao brigar com o veu.
	var largura := 156.0
	var vao := 6.0
	var total := Classes.ORDEM.size() * largura + (Classes.ORDEM.size() - 1) * vao
	var x0 := (tela.x - total) / 2.0
	var y := 104.0
	var altura_retrato := 189.0

	for i in Classes.ORDEM.size():
		var classe: String = Classes.ORDEM[i]
		var dados := Classes.dados(classe)
		var x := x0 + i * (largura + vao)

		var retrato := TextureRect.new()
		retrato.texture = load("res://arte/retratos/%s.png" % classe)
		# EXPAND_IGNORE_SIZE e obrigatorio: sem ele o TextureRect desenha no
		# tamanho original da imagem (310px) e transborda o card, cortando o
		# retrato no meio.
		retrato.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		retrato.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		retrato.size = Vector2(largura, altura_retrato)
		retrato.position = Vector2(x, y)
		_camada_escolha.add_child(retrato)

		# Numero da tecla, num selo escuro sobre o canto do retrato
		var selo := ColorRect.new()
		selo.color = Color(0, 0, 0, 0.7)
		selo.size = Vector2(26, 24)
		selo.position = Vector2(x + 4, y + 4)
		_camada_escolha.add_child(selo)
		var tecla := Label.new()
		tecla.position = Vector2(x + 4, y + 2)
		tecla.size = Vector2(26, 24)
		tecla.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		tecla.add_theme_font_size_override("font_size", 18)
		tecla.text = str(i + 1)
		tecla.modulate = dados["cor"]
		_camada_escolha.add_child(tecla)

		var fundo_texto := ColorRect.new()
		fundo_texto.color = Color(0.08, 0.09, 0.12, 0.92)
		# 200 e nao 150: a ficha do druida, que e a mais longa, vazava para fora
		# do fundo escuro e ficava ilegivel sobre o veu.
		fundo_texto.size = Vector2(largura, 200)
		fundo_texto.position = Vector2(x, y + altura_retrato)
		_camada_escolha.add_child(fundo_texto)

		# Faixa na cor da classe, ligando o retrato ao texto
		var faixa := ColorRect.new()
		faixa.color = dados["cor"]
		faixa.size = Vector2(largura, 4)
		faixa.position = Vector2(x, y + altura_retrato)
		_camada_escolha.add_child(faixa)

		var nome := Label.new()
		nome.position = Vector2(x, y + altura_retrato + 8)
		nome.size = Vector2(largura, 24)
		nome.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		nome.add_theme_font_size_override("font_size", 19)
		nome.text = dados["nome"]
		_camada_escolha.add_child(nome)

		var ficha := Label.new()
		ficha.position = Vector2(x + 8, y + altura_retrato + 34)
		ficha.size = Vector2(largura - 16, 160)
		ficha.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		ficha.add_theme_font_size_override("font_size", 12)
		ficha.text = "%s

Vida %d · %s
Q: %s" % [
			dados["resumo"], dados["vida"], _nome_do_ataque(dados["ataque"]), dados["hab_nome"]]
		_camada_escolha.add_child(ficha)

	_atualiza_titulo_escolha()

func _ao_falar_o_atualizador(texto: String) -> void:
	if _rodape_escolha != null:
		_rodape_escolha.text = "versão %s — %s   ·   F1 configura os controles" % [Atualizador.versao_em_uso, texto]

func _ao_baixar_atualizacao(nova: String) -> void:
	if _rodape_escolha == null:
		return
	_rodape_escolha.text = "Versão %s baixada! Feche e abra o jogo para aplicar." % nova
	_rodape_escolha.modulate = Color(0.5, 1.0, 0.6)

func _nome_do_ataque(tipo: String) -> String:
	match tipo:
		"arco": return "corpo a corpo"
		"explosivo": return "tiro que estoura"
		"gelado": return "tiro que congela"
		_: return "tiro reto"

func _atualiza_titulo_escolha() -> void:
	if _estado == "escolha_sua":
		_titulo_escolha.text = "ESCOLHA A SUA CLASSE   (teclas 1 a 7)"
		_titulo_escolha.modulate = Color.WHITE
	else:
		_titulo_escolha.text = "Você é %s.   AGORA ESCOLHA A CLASSE DO ALIADO" % \
			Classes.dados(_classe_sua)["nome"]
		_titulo_escolha.modulate = Classes.dados(_classe_sua)["cor"]

func _escolhe_classe(indice: int) -> void:
	if indice < 0 or indice >= Classes.ORDEM.size():
		return
	if _estado == "escolha_sua":
		_classe_sua = Classes.ORDEM[indice]
		_estado = "escolha_aliado"
		_atualiza_titulo_escolha()
	elif _estado == "escolha_aliado":
		_classe_aliado = Classes.ORDEM[indice]
		_comeca_o_jogo()

func _comeca_o_jogo() -> void:
	_estado = "jogando"
	_camada_escolha.visible = false
	_camada_jogo.visible = true
	_monta_party(get_viewport_rect().size)
	_atualiza_hud()
	_atualiza_inventario()

# --- Menu inicial e lobby ---------------------------------------------------

func _monta_menu(tela: Vector2) -> void:
	_camada_menu = CanvasLayer.new()
	_camada_menu.layer = 25
	add_child(_camada_menu)

	var veu := ColorRect.new()
	veu.color = Color(0.05, 0.06, 0.08, 0.97)
	veu.size = tela
	_camada_menu.add_child(veu)

	var titulo := Label.new()
	titulo.position = Vector2(0, tela.y * 0.22)
	titulo.size = Vector2(tela.x, 50)
	titulo.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	titulo.add_theme_font_size_override("font_size", 40)
	titulo.text = "BRAWL COOP"
	_camada_menu.add_child(titulo)

	_texto_menu = Label.new()
	_texto_menu.position = Vector2(0, tela.y * 0.22 + 70)
	_texto_menu.size = Vector2(tela.x, 160)
	_texto_menu.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_texto_menu.add_theme_font_size_override("font_size", 20)
	_camada_menu.add_child(_texto_menu)

	# Campo de IP, usado só na opção de entrar
	_campo_ip = LineEdit.new()
	_campo_ip.position = Vector2(tela.x / 2.0 - 150, tela.y * 0.22 + 150)
	_campo_ip.size = Vector2(300, 36)
	_campo_ip.placeholder_text = "IP do anfitrião (ex: 10.147.20.5)"
	_campo_ip.visible = false
	_camada_menu.add_child(_campo_ip)

	_mostra_menu_principal()

func _mostra_menu_principal() -> void:
	_estado = "menu"
	_campo_ip.visible = false
	_texto_menu.text = "[1]  Jogar sozinho (com aliado de computador)

[2]  Hospedar uma partida

[3]  Entrar na partida de alguém


F1 configura os controles"

func _mostra_entrar_ip() -> void:
	_estado = "entrar_ip"
	_campo_ip.visible = true
	_campo_ip.grab_focus()
	_texto_menu.text = "Digite o IP do anfitrião e aperte ENTER.

Numa rede virtual (ZeroTier/Radmin) use o IP que ela
mostra para a máquina do anfitrião.




Esc volta"

func _monta_lobby(tela: Vector2) -> void:
	_camada_lobby = CanvasLayer.new()
	_camada_lobby.layer = 26
	_camada_lobby.visible = false
	add_child(_camada_lobby)

	var veu := ColorRect.new()
	veu.color = Color(0.05, 0.06, 0.08, 0.97)
	veu.size = tela
	_camada_lobby.add_child(veu)

	var titulo := Label.new()
	titulo.position = Vector2(0, 50)
	titulo.size = Vector2(tela.x, 40)
	titulo.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	titulo.add_theme_font_size_override("font_size", 30)
	titulo.text = "SALA — até 4 jogadores"
	_camada_lobby.add_child(titulo)

	_lista_lobby = Label.new()
	_lista_lobby.position = Vector2(tela.x / 2.0 - 300, 120)
	_lista_lobby.size = Vector2(600, 220)
	_lista_lobby.add_theme_font_size_override("font_size", 20)
	_camada_lobby.add_child(_lista_lobby)

	_dica_lobby = Label.new()
	_dica_lobby.position = Vector2(0, tela.y - 130)
	_dica_lobby.size = Vector2(tela.x, 90)
	_dica_lobby.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_dica_lobby.add_theme_font_size_override("font_size", 17)
	_camada_lobby.add_child(_dica_lobby)

	Rede.lista_mudou.connect(_atualiza_lobby)
	Rede.partida_comecou.connect(_ao_comecar_em_rede)
	Rede.desconectado.connect(_ao_desconectar)

func _abre_lobby() -> void:
	_estado = "lobby"
	_sozinho = false
	_camada_menu.visible = false
	_camada_lobby.visible = true
	_atualiza_lobby()

func _atualiza_lobby() -> void:
	if _lista_lobby == null:
		return
	var linhas := []
	var i := 1
	for id in Rede.jogadores:
		var j: Dictionary = Rede.jogadores[id]
		var eu := " (você)" if id == Rede.meu_id() else ""
		var dono := " — anfitrião" if id == 1 else ""
		linhas.append("%d. %s%s%s   ·   %s" % [i, j.get("nome", "?"), eu, dono,
			Classes.dados(j.get("classe", "guerreiro"))["nome"]])
		i += 1
	while linhas.size() < Rede.MAXIMO_DE_JOGADORES:
		linhas.append("%d. (vaga livre — vira aliado de computador)" % (linhas.size() + 1))
	_lista_lobby.text = "

".join(linhas)
	if OS.get_cmdline_user_args().has("log"):
		print("[sala] %d jogador(es): %s" % [Rede.jogadores.size(), str(Rede.jogadores)])

	var dica := "Teclas 1 a 7 escolhem a sua classe."
	if Rede.sou_anfitriao:
		dica += "
ENTER começa a partida."
	else:
		dica += "
Esperando o anfitrião começar..."
	dica += "
Esc sai da sala."
	_dica_lobby.text = dica

func _ao_comecar_em_rede() -> void:
	if OS.get_cmdline_user_args().has("log"):
		print("[partida] comecou com %d jogador(es); eu sou o id %d" % [Rede.jogadores.size(), Rede.meu_id()])
	_camada_lobby.visible = false
	_classe_sua = Rede.jogadores.get(Rede.meu_id(), {}).get("classe", "guerreiro")
	_comeca_o_jogo()

func _ao_desconectar(motivo: String) -> void:
	_camada_lobby.visible = false
	_camada_menu.visible = true
	_mostra_menu_principal()
	_texto_menu.text = "Conexão perdida: %s


" % motivo + _texto_menu.text

# --- Tela de controles ------------------------------------------------------

func _monta_controles(tela: Vector2) -> void:
	_camada_controles = CanvasLayer.new()
	_camada_controles.layer = 30
	_camada_controles.visible = false
	# Funciona mesmo com a arvore pausada (fim de jogo, por exemplo).
	_camada_controles.process_mode = Node.PROCESS_MODE_ALWAYS
	add_child(_camada_controles)

	# Praticamente opaco: com 0.88 dava para ver o jogo atras e o texto ficava
	# dificil de ler.
	var veu := ColorRect.new()
	veu.color = Color(0.04, 0.05, 0.07, 0.985)
	veu.size = tela
	_camada_controles.add_child(veu)

	var titulo := Label.new()
	titulo.position = Vector2(0, 30)
	titulo.size = Vector2(tela.x, 36)
	titulo.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	titulo.add_theme_font_size_override("font_size", 26)
	titulo.text = "CONTROLES — clique numa tecla e aperte a nova"
	_camada_controles.add_child(titulo)

	# Duas colunas: 16 acoes nao cabem numa so sem virar lista minuscula.
	var por_coluna := int(ceil(Controles.ACOES.size() / 2.0))
	var largura_col := 460.0
	var x0 := (tela.x - largura_col * 2.0) / 2.0
	var y0 := 90.0
	var altura := 34.0

	for i in Controles.ACOES.size():
		var acao: Dictionary = Controles.ACOES[i]
		var col := 0 if i < por_coluna else 1
		var linha := i if i < por_coluna else i - por_coluna
		var x := x0 + col * largura_col
		var y := y0 + linha * altura

		var nome := Label.new()
		nome.position = Vector2(x, y + 4)
		nome.size = Vector2(260, 26)
		nome.add_theme_font_size_override("font_size", 15)
		nome.text = acao["nome"]
		_camada_controles.add_child(nome)

		var botao := Button.new()
		botao.position = Vector2(x + 270, y)
		botao.size = Vector2(150, 28)
		botao.add_theme_font_size_override("font_size", 15)
		botao.pressed.connect(_comeca_a_capturar.bind(acao["id"]))
		_camada_controles.add_child(botao)
		_linhas_de_controle[acao["id"]] = botao

	var dica := Label.new()
	dica.position = Vector2(0, tela.y - 128.0)
	dica.size = Vector2(tela.x, 22)
	dica.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	dica.add_theme_font_size_override("font_size", 13)
	dica.modulate = Color(0.65, 0.65, 0.7)
	dica.text = "Botão do mouse só vale para \"Atacar\". Duas ações não dividem a mesma tecla: a antiga fica sem."
	_camada_controles.add_child(dica)

	_aviso_controles = Label.new()
	_aviso_controles.position = Vector2(0, tela.y - 92.0)
	_aviso_controles.size = Vector2(tela.x, 24)
	_aviso_controles.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_aviso_controles.add_theme_font_size_override("font_size", 15)
	_camada_controles.add_child(_aviso_controles)

	var padrao := Button.new()
	padrao.position = Vector2(tela.x / 2.0 - 230, tela.y - 62.0)
	padrao.size = Vector2(210, 32)
	padrao.text = "Restaurar o padrão"
	padrao.pressed.connect(_restaura_controles)
	_camada_controles.add_child(padrao)

	var voltar := Button.new()
	voltar.position = Vector2(tela.x / 2.0 + 20, tela.y - 62.0)
	voltar.size = Vector2(210, 32)
	voltar.text = "Voltar  (Esc)"
	voltar.pressed.connect(_fecha_controles)
	_camada_controles.add_child(voltar)

	Controles.controles_mudaram.connect(_atualiza_rotulos_de_tecla)
	_atualiza_rotulos_de_tecla()

func _abre_controles() -> void:
	_estado_antes_dos_controles = _estado
	_estado = "controles"
	_capturando = ""
	_aviso_controles.text = ""
	_camada_controles.visible = true

func _fecha_controles() -> void:
	_capturando = ""
	_camada_controles.visible = false
	_estado = _estado_antes_dos_controles

func _comeca_a_capturar(id: String) -> void:
	_capturando = id
	_aviso_controles.text = "Aperte a tecla nova para \"%s\"  (Esc cancela)" % Controles.nome_da_acao(id)
	_aviso_controles.modulate = Color(1, 0.9, 0.4)
	_atualiza_rotulos_de_tecla()

func _restaura_controles() -> void:
	Controles.restaura_padrao()
	_aviso_controles.text = "Controles de volta ao padrão."
	_aviso_controles.modulate = Color(0.6, 0.9, 1.0)

# Chamada sempre que uma tecla muda: os rotulos nao podem mentir sobre o que
# esta valendo, nem aqui nem no HUD do jogo.
func _atualiza_rotulos_de_tecla() -> void:
	for id in _linhas_de_controle:
		var botao: Button = _linhas_de_controle[id]
		botao.text = "..." if id == _capturando else Controles.tecla_de(id)
	for i in _slots.size():
		if _slots[i].has("tecla"):
			_slots[i]["tecla"].text = Controles.tecla_de("item_%d" % (i + 1))
	if not _slot_hab.is_empty():
		_slot_hab["letra"].text = Controles.tecla_de("habilidade")
	if _jogador != null:
		_atualiza_inventario()
		_atualiza_hud()

# --- Party ------------------------------------------------------------------

# Os dois membros saem do mesmo script. Classe e "por_ia" PRECISAM ser
# definidos antes do add_child, porque é no _ready que a folha de sprite e a
# vida da classe são carregadas.
func _monta_party(tela: Vector2) -> void:
	var Personagem := load("res://Personagem.gd")
	var pontos := [Vector2(0, 0), Vector2(90, 40), Vector2(-90, 40), Vector2(0, 90)]

	if _sozinho:
		# Partida local: você mais um aliado de computador.
		_jogador = _cria_membro(Personagem, _classe_sua, tela / 2.0, false, false)
		_aliado = _cria_membro(Personagem, _classe_aliado, tela / 2.0 + pontos[1], true, false)
		_aliado.lider = _jogador
		return

	# Partida em rede: um personagem por jogador conectado, na ordem da lista.
	var i := 0
	for id in Rede.jogadores:
		var dados: Dictionary = Rede.jogadores[id]
		var sou_eu: bool = id == Rede.meu_id()
		var membro = _cria_membro(Personagem, dados.get("classe", "guerreiro"),
			tela / 2.0 + pontos[i % pontos.size()], false, not sou_eu)
		membro.id_de_rede = id
		if sou_eu:
			_jogador = membro
		elif _aliado == null:
			_aliado = membro
		i += 1

	# Vagas que sobraram viram aliados de computador, para a party ficar cheia.
	# As vagas viram aliados de computador. Eles sao do ANFITRIAO: se cada
	# maquina rodasse a IA por conta, o mesmo aliado apareceria em lugares
	# diferentes em cada tela.
	while i < Rede.MAXIMO_DE_JOGADORES:
		var bot = _cria_membro(Personagem, Classes.ORDEM[i % Classes.ORDEM.size()],
			tela / 2.0 + pontos[i % pontos.size()], Rede.sou_anfitriao, not Rede.sou_anfitriao)
		bot.id_de_rede = -(i + 1)   # negativo = aliado de computador
		bot.lider = _jogador
		if _aliado == null:
			_aliado = bot
		i += 1

func _cria_membro(Personagem, classe: String, onde: Vector2, ia: bool, remoto: bool):
	var membro = Personagem.new()
	membro.classe = classe
	membro.por_ia = ia
	membro.remoto = remoto
	membro.global_position = onde
	_arena.add_child(membro)
	membro.vida_mudou.connect(_ao_mudar_vida)
	if not ia and not remoto:
		membro.inventario_mudou.connect(_atualiza_inventario)
		membro.morreu.connect(_ao_morrer_jogador)
		membro.habilidade_usada.connect(_ao_usar_habilidade.bind("Você"))
	else:
		membro.morreu.connect(_ao_cair_aliado)
		membro.habilidade_usada.connect(_ao_usar_habilidade.bind("Aliado"))
	return membro

# --- Laço e teclas ----------------------------------------------------------

func _process(delta: float) -> void:
	if _estado != "jogando":
		return
	_atualiza_habilidade()
	_conta_o_flash(delta)

	# Em rede, quem cria as ondas e o anfitriao; o cliente so mostra o que chega.
	# O anfitriao continua comandando MESMO CAIDO: se ele parasse, os
	# inimigos congelavam em todas as telas.
	if Rede.esta_em_rede():
		_sincroniza(delta)
		if not Rede.sou_anfitriao:
			return
	elif _fim_de_jogo:
		return

	if _vivos == 0:
		_tempo_ate_proxima_onda -= delta
		if _tempo_ate_proxima_onda <= 0.0:
			_comeca_onda()
		else:
			_mostra_aviso("Onda %d em %d..." % [_onda + 1, ceili(_tempo_ate_proxima_onda)])

func _input(evento: InputEvent) -> void:
	# A tela de controles tem prioridade sobre tudo.
	if _estado == "controles":
		_input_dos_controles(evento)
		return

	# F1 abre os controles de qualquer lugar. F1 e nao uma letra: letra poderia
	# ser justamente a que o jogador acabou de mapear para outra coisa.
	if evento is InputEventKey and evento.pressed and not evento.echo 		and evento.physical_keycode == KEY_F1:
		_abre_controles()
		return

	if _estado == "menu" or _estado == "entrar_ip" or _estado == "lobby":
		_input_das_telas_de_rede(evento)
		return

	# Na tela de escolha as teclas sao fixas (1 a 7): menu nao entra no
	# remapeamento, senao o jogador poderia se trancar fora do proprio menu.
	if _estado != "jogando":
		if evento is InputEventKey and evento.pressed and not evento.echo:
			var n: int = evento.physical_keycode - KEY_1
			if n >= 0 and n < Classes.ORDEM.size():
				_escolhe_classe(n)
		return

	# Em jogo tudo passa por ACAO, entao respeita o que o jogador configurou.
	for i in ITENS.size():
		if evento.is_action_pressed("item_%d" % (i + 1)):
			_escolhe_slot(i)
			return
	if evento.is_action_pressed("trocar_alvo"):
		_troca_alvo()
	elif evento.is_action_pressed("usar_item"):
		_usa_slot_escolhido()
	elif evento.is_action_pressed("habilidade"):
		_jogador.ativar_habilidade()
	elif evento.is_action_pressed("neutro"):
		_alterna_neutros()
	elif evento.is_action_pressed("recomecar") and _fim_de_jogo:
		get_tree().paused = false
		get_tree().call_deferred("reload_current_scene")

func _input_das_telas_de_rede(evento: InputEvent) -> void:
	if not (evento is InputEventKey) or not evento.pressed or evento.echo:
		return
	var codigo: int = evento.physical_keycode

	match _estado:
		"menu":
			match codigo:
				KEY_1:
					# Sozinho: segue o fluxo antigo, escolhendo as duas classes.
					_sozinho = true
					_camada_menu.visible = false
					_camada_escolha.visible = true
					_estado = "escolha_sua"
					_atualiza_titulo_escolha()
				KEY_2:
					var erro: String = Rede.hospedar(_meu_apelido())
					if erro == "":
						_abre_lobby()
					else:
						_texto_menu.text = "Não deu para hospedar: %s

" % erro + _texto_menu.text
				KEY_3:
					_mostra_entrar_ip()
		"entrar_ip":
			if codigo == KEY_ESCAPE:
				_mostra_menu_principal()
			elif codigo == KEY_ENTER or codigo == KEY_KP_ENTER:
				var ip := _campo_ip.text.strip_edges()
				if ip == "":
					return
				var erro: String = Rede.entrar(ip, _meu_apelido())
				if erro == "":
					_abre_lobby()
				else:
					_texto_menu.text = "Não deu para entrar: %s" % erro
		"lobby":
			if codigo == KEY_ESCAPE:
				Rede.sair()
				_camada_lobby.visible = false
				_camada_menu.visible = true
				_mostra_menu_principal()
			elif codigo == KEY_ENTER or codigo == KEY_KP_ENTER:
				if Rede.sou_anfitriao:
					Rede.comecar_partida()
			else:
				var n: int = codigo - KEY_1
				if n >= 0 and n < Classes.ORDEM.size():
					Rede.escolher_classe(Classes.ORDEM[n])

# Nome curto para aparecer na lista da sala.
func _meu_apelido() -> String:
	var nome := OS.get_environment("USERNAME")
	return nome if nome != "" else "jogador"

func _input_dos_controles(evento: InputEvent) -> void:
	if not evento.is_pressed() or evento.is_echo():
		return
	var e_esc: bool = evento is InputEventKey and evento.physical_keycode == KEY_ESCAPE

	if _capturando == "":
		if e_esc:
			_fecha_controles()
		return

	if e_esc:
		_capturando = ""
		_aviso_controles.text = "Cancelado."
		_aviso_controles.modulate = Color(0.8, 0.8, 0.8)
		_atualiza_rotulos_de_tecla()
		return

	# So o "Atacar" aceita botao de mouse. Nos outros, um clique seria quase
	# sempre a pessoa tentando clicar em outra linha da lista, e viraria atalho
	# sem querer.
	var vale: bool = evento is InputEventKey
	if evento is InputEventMouseButton and _capturando == "atacar":
		vale = true
	if not vale:
		return

	var id := _capturando
	_capturando = ""
	var conflito := Controles.define(id, evento)
	if conflito == "":
		_aviso_controles.text = "%s agora é %s." % [Controles.nome_da_acao(id), Controles.tecla_de(id)]
		_aviso_controles.modulate = Color(0.6, 1.0, 0.7)
	else:
		_aviso_controles.text = "%s agora é %s — e \"%s\" ficou sem tecla." % [
			Controles.nome_da_acao(id), Controles.tecla_de(id), Controles.nome_da_acao(conflito)]
		_aviso_controles.modulate = Color(1.0, 0.8, 0.4)
	_atualiza_rotulos_de_tecla()

# --- Ondas ------------------------------------------------------------------

func _comeca_onda() -> void:
	_onda += 1
	_mostra_aviso("")
	var quantidade := INIMIGOS_DA_PRIMEIRA_ONDA + (_onda - 1) * INIMIGOS_A_MAIS_POR_ONDA
	for i in quantidade:
		var inimigo: CharacterBody2D = load("res://Inimigo.gd").new()
		inimigo.id_rede = _proximo_id_inimigo
		_proximo_id_inimigo += 1
		inimigo.global_position = _posicao_de_spawn()
		inimigo.neutro = _inimigos_neutros
		inimigo.morreu.connect(_ao_morrer_inimigo)
		_arena.add_child(inimigo)
		_vivos += 1
	_atualiza_hud()

func _posicao_de_spawn() -> Vector2:
	var tela := get_viewport_rect().size
	var pos := Vector2.ZERO
	for tentativa in 8:
		match randi() % 4:
			0: pos = Vector2(randf_range(MARGEM_DE_SPAWN, tela.x - MARGEM_DE_SPAWN), MARGEM_DE_SPAWN)
			1: pos = Vector2(randf_range(MARGEM_DE_SPAWN, tela.x - MARGEM_DE_SPAWN), tela.y - MARGEM_DE_SPAWN)
			2: pos = Vector2(MARGEM_DE_SPAWN, randf_range(MARGEM_DE_SPAWN, tela.y - MARGEM_DE_SPAWN))
			_: pos = Vector2(tela.x - MARGEM_DE_SPAWN, randf_range(MARGEM_DE_SPAWN, tela.y - MARGEM_DE_SPAWN))
		if pos.distance_to(_jogador.global_position) >= LONGE_DA_PARTY:
			break
	return pos

func _ao_morrer_inimigo(_inimigo: Node) -> void:
	_vivos = max(0, _vivos - 1)
	_atualiza_hud()
	if _vivos == 0 and not _fim_de_jogo:
		_tempo_ate_proxima_onda = PAUSA_ENTRE_ONDAS

func _alterna_neutros() -> void:
	_inimigos_neutros = not _inimigos_neutros
	for inimigo in get_tree().get_nodes_in_group("inimigos"):
		inimigo.neutro = _inimigos_neutros
	_atualiza_hud()

# --- Sincronia da partida em rede -------------------------------------------
#
# Cada maquina manda o proprio boneco; o anfitriao manda a horda. Os pacotes vao
# como "unreliable": perder um nao importa, o proximo chega logo -- e esperar
# confirmacao de cada um travaria o movimento.

func _sincroniza(delta: float) -> void:
	_relata(delta)
	_t_envio_jogador += delta
	if _t_envio_jogador >= 1.0 / ENVIOS_DO_JOGADOR and _jogador != null:
		_t_envio_jogador = 0.0
		_estado_do_jogador.rpc(_jogador.global_position, _jogador.mira(), _jogador.vida)

	if Rede.sou_anfitriao:
		_t_envio_inimigos += delta
		if _t_envio_inimigos >= 1.0 / ENVIOS_DOS_INIMIGOS:
			_t_envio_inimigos = 0.0
			_estado_dos_inimigos.rpc(_foto_dos_inimigos(), _onda)
			_estado_dos_aliados.rpc(_foto_dos_aliados())

# Relatorio periodico no console, so com o argumento "log". Serve para conferir
# a sincronia entre duas maquinas sem precisar olhar as duas telas.
var _t_relato := 0.0
func _relata(delta: float) -> void:
	if not OS.get_cmdline_user_args().has("log"):
		return
	_t_relato += delta
	if _t_relato < 2.0:
		return
	_t_relato = 0.0
	var party := get_tree().get_nodes_in_group("jogador")
	var posicoes := []
	for m in party:
		posicoes.append("id%d%s@%s" % [m.id_de_rede, ("(eu)" if m == _jogador else ""),
			str(m.global_position.round())])
	var inimigos := get_tree().get_nodes_in_group("inimigos")
	var primeiro := "-"
	if inimigos.size() > 0:
		primeiro = "id%d@%s vida=%d" % [inimigos[0].id_rede,
			str(inimigos[0].global_position.round()), inimigos[0].vida]
	var tiros := 0
	for f in _arena.get_children():
		if f is Area2D and f.has_method("_ao_acertar"):
			tiros += 1
	print("[%s] party: %s | inimigos: %d | 1o: %s | onda %d | tiros na tela: %d"
		% ["ANFITRIAO" if Rede.sou_anfitriao else "CLIENTE", ", ".join(posicoes),
		   inimigos.size(), primeiro, _onda, tiros])

# Aliados de computador: mesma ideia da horda, mas eles tem mira, que importa
# para a animacao de qual lado o boneco esta olhando.
func _foto_dos_aliados() -> Array:
	var foto := []
	for m in get_tree().get_nodes_in_group("jogador"):
		if m.id_de_rede >= 0:
			continue
		foto.append([m.id_de_rede, m.global_position.x, m.global_position.y,
			m.mira().x, m.mira().y, m.vida])
	return foto

@rpc("authority", "unreliable_ordered")
func _estado_dos_aliados(foto: Array) -> void:
	for e in foto:
		for m in get_tree().get_nodes_in_group("jogador"):
			if m.id_de_rede == e[0]:
				m.aplica_estado_remoto(Vector2(e[1], e[2]), Vector2(e[3], e[4]), e[5])
				break

func _foto_dos_inimigos() -> Array:
	var foto := []
	for i in get_tree().get_nodes_in_group("inimigos"):
		foto.append([i.id_rede, i.global_position.x, i.global_position.y, i.vida,
			i._tempo_preso > 0.0, i._tempo_lentidao > 0.0])
	return foto

@rpc("any_peer", "unreliable_ordered")
func _estado_do_jogador(pos: Vector2, mira: Vector2, vida: int) -> void:
	var id := multiplayer.get_remote_sender_id()
	for membro in get_tree().get_nodes_in_group("jogador"):
		if membro.id_de_rede == id:
			membro.aplica_estado_remoto(pos, mira, vida)
			return

@rpc("authority", "unreliable_ordered")
func _estado_dos_inimigos(foto: Array, onda: int) -> void:
	_onda = onda
	var vistos := {}
	for e in foto:
		var id: int = e[0]
		vistos[id] = true
		var no = _inimigos_por_id.get(id)
		if no == null or not is_instance_valid(no):
			no = load("res://Inimigo.gd").new()
			no.remoto = true
			no.id_rede = id
			no.global_position = Vector2(e[1], e[2])
			_arena.add_child(no)
			_inimigos_por_id[id] = no
		no.aplica_estado_remoto(Vector2(e[1], e[2]), e[3], e[4], e[5])

	# Quem sumiu da foto morreu (ou nunca existiu para este cliente).
	for id in _inimigos_por_id.keys():
		if not vistos.has(id):
			var no = _inimigos_por_id[id]
			if is_instance_valid(no):
				no.queue_free()
			_inimigos_por_id.erase(id)

	_vivos = foto.size()
	_atualiza_hud()

# Tiro de alguem: as outras maquinas so DESENHAM, nao contam dano.
func avisa_tiro(pos: Vector2, direcao: Vector2, classe: String) -> void:
	if Rede.esta_em_rede() and Rede.em_partida:
		_tiro_de_alguem.rpc(pos, direcao, classe)

@rpc("any_peer", "unreliable")
func _tiro_de_alguem(pos: Vector2, direcao: Vector2, classe: String) -> void:
	var dados := Classes.dados(classe)
	if dados["ataque"] == "arco":
		return   # corpo a corpo nao tem projetil para mostrar
	var bala: Area2D = load("res://Bala.gd").new()
	bala.so_enfeite = true
	bala.direcao = direcao
	bala.cor = dados.get("cor", Color(1, 0.85, 0.2))
	bala.alcance = float(dados.get("alcance", 450.0))
	bala.global_position = pos
	_arena.add_child(bala)

# Chamado pelo Inimigo de um cliente: quem aplica o dano e o anfitriao.
func pede_dano_em_inimigo(id: int, dano: int) -> void:
	if Rede.esta_em_rede():
		_dano_em_inimigo.rpc_id(1, id, dano)

@rpc("any_peer", "reliable")
func _dano_em_inimigo(id: int, dano: int) -> void:
	if not Rede.sou_anfitriao:
		return
	for i in get_tree().get_nodes_in_group("inimigos"):
		if i.id_rede == id:
			i.receber_dano(dano)
			return

# Chamado quando um inimigo do anfitriao encosta num jogador de outra maquina.
func avisa_dano_em_jogador(id: int, dano: int) -> void:
	if Rede.esta_em_rede():
		_dano_em_jogador.rpc_id(id, dano)

@rpc("any_peer", "reliable")
func _dano_em_jogador(dano: int) -> void:
	if _jogador != null:
		_jogador.receber_dano(dano)

# --- Inventário e habilidade ------------------------------------------------

func _escolhe_slot(indice: int) -> void:
	_slot_escolhido = indice
	_atualiza_inventario()

func _troca_alvo() -> void:
	_mirando_no_aliado = not _mirando_no_aliado
	_atualiza_inventario()

func _usa_slot_escolhido() -> void:
	var tipo: String = ITENS[_slot_escolhido]["tipo"]
	if tipo == "":
		return
	# Com o aliado caído o item volta para você, senão sumiria à toa.
	var alvo: Node = _jogador
	if _mirando_no_aliado and _aliado.vida > 0:
		alvo = _aliado
	_jogador.usar_item(tipo, alvo)
	_atualiza_inventario()

func _atualiza_inventario() -> void:
	if _jogador == null:
		return
	for i in _slots.size():
		var slot: Dictionary = _slots[i]
		var tipo: String = ITENS[i]["tipo"]
		var quantos: int = _jogador.estoque.get(tipo, 0) if tipo != "" else 0
		var escolhido := i == _slot_escolhido
		slot["fundo"].color = Color(1, 0.85, 0.3, 0.30) if escolhido else Color(0, 0, 0, 0.45)
		slot["borda"].visible = escolhido
		slot["conta"].text = "x%d" % quantos if tipo != "" else ""
		slot["icone"].modulate = Color(1, 1, 1, 1.0 if quantos > 0 else 0.25)

	var em_quem := "no ALIADO" if _mirando_no_aliado else "em VOCÊ"
	_hud_item.text = "[%s] %s   —   %s usa %s   (%s troca o alvo)" % [
		Controles.tecla_de("item_%d" % (_slot_escolhido + 1)),
		ITENS[_slot_escolhido]["nome"], Controles.tecla_de("usar_item"), em_quem,
		Controles.tecla_de("trocar_alvo")]
	_hud_item.modulate = Color(0.6, 0.85, 1.0) if _mirando_no_aliado else Color.WHITE

# Aviso curto de que uma habilidade saiu -- o anel no chao dura meio segundo
# e passa batido, ainda mais se voce estiver olhando para outro canto.
func _ao_usar_habilidade(nome_da_hab: String, de_quem: String) -> void:
	_hud_flash.text = "%s: %s!" % [de_quem, nome_da_hab]
	_hud_flash.modulate = _jogador.cor_da_classe() if de_quem == "Você" else _aliado.cor_da_classe()
	_tempo_flash = 1.6

func _conta_o_flash(delta: float) -> void:
	_tempo_flash = max(0.0, _tempo_flash - delta)
	if _tempo_flash <= 0.0:
		_hud_flash.text = ""

func _atualiza_habilidade() -> void:
	if _jogador == null:
		return
	var nome: String = _jogador.nome_da_habilidade()
	var cor: Color = _jogador.cor_da_classe()
	var pronta: bool = _jogador.habilidade_pronta()
	var restante: float = _jogador.recarga_restante()
	var total: float = max(_jogador.recarga_total(), 0.001)

	# Linha de texto no canto (a mesma de antes)
	if _jogador.aura_ativa():
		_hud_hab.text = "%s  %s: ATIVA" % [Controles.tecla_de("habilidade"), nome]
		_hud_hab.modulate = Color(0.45, 1.0, 0.55)
	elif pronta:
		_hud_hab.text = "%s  %s: pronta" % [Controles.tecla_de("habilidade"), nome]
		_hud_hab.modulate = cor
	else:
		_hud_hab.text = "%s  %s: %ds" % [Controles.tecla_de("habilidade"), nome, ceili(restante)]
		_hud_hab.modulate = Color(0.65, 0.65, 0.65)

	# Slot da habilidade, ao lado dos itens
	if _slot_hab.is_empty():
		return
	var lado: float = _slot_hab["lado"]
	_slot_hab["nome"].text = nome
	_slot_hab["nome"].modulate = cor if pronta else Color(0.7, 0.7, 0.7)
	_slot_hab["fundo"].color = Color(cor.r, cor.g, cor.b, 0.85 if pronta else 0.35)
	_slot_hab["borda"].color = Color(1, 0.9, 0.4, 0.95) if pronta else Color(0.25, 0.25, 0.3, 0.9)
	_slot_hab["letra"].modulate = Color.WHITE if pronta else Color(0.75, 0.75, 0.8)

	# A cortina escura cobre o quanto AINDA falta recarregar, e vai encolhendo.
	var falta: float = 0.0 if pronta else clampf(restante / total, 0.0, 1.0)
	_slot_hab["cortina"].size.y = lado * falta
	_slot_hab["segundos"].text = "" if pronta else "%ds" % ceili(restante)

# --- HUD --------------------------------------------------------------------

func _monta_hud(tela: Vector2) -> void:
	_camada_jogo = CanvasLayer.new()
	_camada_jogo.layer = 10     # explícito: o HUD fica sempre por cima dos bonecos
	add_child(_camada_jogo)

	_fundo_aviso = ColorRect.new()
	_fundo_aviso.color = Color(0, 0, 0, 0.55)
	_fundo_aviso.size = Vector2(tela.x, 92)
	_fundo_aviso.position = Vector2(0, tela.y * 0.16)
	_fundo_aviso.visible = false
	_camada_jogo.add_child(_fundo_aviso)

	_hud_vida = _cria_texto(Vector2(16, 12), 20)
	_hud_aliado = _cria_texto(Vector2(16, 38), 20)
	_hud_onda = _cria_texto(Vector2(16, 64), 20)
	_hud_inimigos = _cria_texto(Vector2(16, 90), 16)
	_hud_hab = _cria_texto(Vector2(16, 112), 16)
	_hud_flash = _cria_texto(Vector2(16, 136), 18)

	_hud_aviso = _cria_texto(Vector2(0, tela.y * 0.16), 30)
	_hud_aviso.size = Vector2(tela.x, 92)   # no alto: o meio é onde a briga acontece
	_hud_aviso.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hud_aviso.vertical_alignment = VERTICAL_ALIGNMENT_CENTER

	# Versao no canto: o testador precisa saber em qual esta ao relatar algo,
	# e nem sempre ele volta para a tela inicial para olhar.
	# Canto DIREITO: o esquerdo agora e do painel de habilidade.
	var etiqueta := _cria_texto(Vector2(tela.x - 92.0, tela.y - 24.0), 12)
	etiqueta.size = Vector2(80, 18)
	etiqueta.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	etiqueta.text = "v%s" % Atualizador.versao_em_uso
	etiqueta.modulate = Color(1, 1, 1, 0.45)

	_monta_habilidade(tela)
	_monta_inventario(tela)

# --- As duas barras de baixo ------------------------------------------------
#
# Habilidade e inventario ficam em GRUPOS SEPARADOS, cada um com painel e
# titulo proprios: colados numa fileira so, o slot da habilidade parecia mais
# um item, e a pessoa tentava usar a habilidade com a tecla de usar item.

const ALTURA_DO_PAINEL := 108.0
const LADO_DO_SLOT := 64.0
const VAO_ENTRE_SLOTS := 10.0

func _painel(pos: Vector2, tam: Vector2) -> void:
	var fundo := ColorRect.new()
	fundo.color = Color(0, 0, 0, 0.42)
	fundo.size = tam
	fundo.position = pos
	_camada_jogo.add_child(fundo)

func _titulo_do_painel(pos: Vector2, largura: float, texto: String) -> void:
	var etiqueta := _cria_texto(pos, 11)
	etiqueta.size = Vector2(largura, 16)
	etiqueta.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	etiqueta.text = texto
	etiqueta.modulate = Color(0.72, 0.72, 0.78)

# Habilidade: canto de baixo à esquerda, sozinha.
func _monta_habilidade(tela: Vector2) -> void:
	var largura_painel := 232.0
	var px := 16.0
	var py := tela.y - 124.0
	_painel(Vector2(px, py), Vector2(largura_painel, ALTURA_DO_PAINEL))
	_titulo_do_painel(Vector2(px, py + 5.0), largura_painel, "HABILIDADE")

	var x := px + 12.0
	var y := py + 26.0

	var borda := ColorRect.new()
	borda.size = Vector2(LADO_DO_SLOT + 6, LADO_DO_SLOT + 6)
	borda.position = Vector2(x - 3, y - 3)
	_camada_jogo.add_child(borda)

	var fundo := ColorRect.new()
	fundo.size = Vector2(LADO_DO_SLOT, LADO_DO_SLOT)
	fundo.position = Vector2(x, y)
	_camada_jogo.add_child(fundo)

	var letra := _cria_texto(Vector2(x, y + 8), 30)
	letra.size = Vector2(LADO_DO_SLOT, 40)
	letra.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	letra.text = Controles.tecla_de("habilidade")

	# Cortina da recarga: fica em cima do slot e vai encolhendo.
	var cortina := ColorRect.new()
	cortina.color = Color(0, 0, 0, 0.68)
	cortina.size = Vector2(LADO_DO_SLOT, LADO_DO_SLOT)
	cortina.position = Vector2(x, y)
	_camada_jogo.add_child(cortina)

	var segundos := _cria_texto(Vector2(x, y + LADO_DO_SLOT - 26), 17)
	segundos.size = Vector2(LADO_DO_SLOT, 22)
	segundos.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

	# Nome ao LADO do slot, dentro do painel: sobrava espaco a direita e assim
	# ele nao briga com a linha de texto do inventario, que e centralizada.
	var nome := _cria_texto(Vector2(x + LADO_DO_SLOT + 10.0, y + 20.0), 14)
	nome.size = Vector2(largura_painel - LADO_DO_SLOT - 34.0, 40)
	nome.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	_slot_hab = {"borda": borda, "fundo": fundo, "letra": letra,
		"cortina": cortina, "segundos": segundos, "nome": nome, "lado": LADO_DO_SLOT, "y": y}

# Inventário: centralizado embaixo, no seu próprio painel.
func _monta_inventario(tela: Vector2) -> void:
	var largura_dos_slots := ITENS.size() * LADO_DO_SLOT + (ITENS.size() - 1) * VAO_ENTRE_SLOTS
	var largura_painel := largura_dos_slots + 24.0
	var px := (tela.x - largura_painel) / 2.0
	var py := tela.y - 124.0
	_painel(Vector2(px, py), Vector2(largura_painel, ALTURA_DO_PAINEL))
	_titulo_do_painel(Vector2(px, py + 5.0), largura_painel, "INVENTÁRIO")

	var x0 := px + 12.0
	var y := py + 26.0

	# A descrição do item fica ACIMA do painel, para não apertar os slots.
	_hud_item = _cria_texto(Vector2(0, py - 24.0), 16)
	_hud_item.size = Vector2(tela.x, 22)
	_hud_item.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

	for i in ITENS.size():
		var x := x0 + i * (LADO_DO_SLOT + VAO_ENTRE_SLOTS)

		var borda := ColorRect.new()
		borda.color = Color(1, 0.85, 0.3, 0.9)
		borda.size = Vector2(LADO_DO_SLOT + 6, LADO_DO_SLOT + 6)
		borda.position = Vector2(x - 3, y - 3)
		_camada_jogo.add_child(borda)

		var fundo := ColorRect.new()
		fundo.size = Vector2(LADO_DO_SLOT, LADO_DO_SLOT)
		fundo.position = Vector2(x, y)
		_camada_jogo.add_child(fundo)

		var icone := TextureRect.new()
		icone.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icone.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icone.size = Vector2(LADO_DO_SLOT - 12, LADO_DO_SLOT - 12)
		icone.position = Vector2(x + 6, y + 6)
		var tipo: String = ITENS[i]["tipo"]
		if tipo != "":
			icone.texture = load("res://arte/itens2/%s.png" % tipo)
		_camada_jogo.add_child(icone)

		# A tecla vem do Controles: se o jogador remapear, o rotulo acompanha.
		var tecla := _cria_texto(Vector2(x + 4, y + 1), 13)
		tecla.text = Controles.tecla_de("item_%d" % (i + 1))

		var conta := _cria_texto(Vector2(x, y + LADO_DO_SLOT - 24), 16)
		conta.size = Vector2(LADO_DO_SLOT - 6, 20)
		conta.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

		_slots.append({"fundo": fundo, "borda": borda, "icone": icone, "conta": conta, "tecla": tecla})

func _cria_texto(pos: Vector2, tamanho: int) -> Label:
	var etiqueta := Label.new()
	etiqueta.position = pos
	etiqueta.add_theme_font_size_override("font_size", tamanho)
	_camada_jogo.add_child(etiqueta)
	return etiqueta

func _mostra_aviso(texto: String) -> void:
	_hud_aviso.text = texto
	_fundo_aviso.visible = texto != ""

func _ao_mudar_vida(_vida_atual: int) -> void:
	_atualiza_hud()

# O aliado cair NÃO acaba o jogo — você continua sozinho.
func _ao_cair_aliado() -> void:
	_atualiza_hud()

func _ao_morrer_jogador() -> void:
	_fim_de_jogo = true
	_atualiza_hud()
	if Rede.esta_em_rede():
		# Em rede ninguem pausa nada: pausar a arvore do anfitriao congelaria
		# os inimigos em TODAS as telas.
		_mostra_aviso("Você caiu na onda %d — a partida continua para os outros." % _onda)
		return
	_mostra_aviso("FIM DE JOGO — chegou até a onda %d
Aperte %s para recomeçar"
		% [_onda, Controles.tecla_de("recomecar")])
	get_tree().paused = true   # congela inimigos e tiros

func _atualiza_hud() -> void:
	if _jogador == null:
		return
	_hud_vida.text = "Você (%s): %d" % [_jogador.nome_da_classe(), _jogador.vida]
	_hud_vida.modulate = _jogador.cor_da_classe()
	if _aliado.vida > 0:
		_hud_aliado.text = "Aliado (%s): %d" % [_aliado.nome_da_classe(), _aliado.vida]
		_hud_aliado.modulate = _aliado.cor_da_classe()
	else:
		_hud_aliado.text = "Aliado (%s): caiu" % _aliado.nome_da_classe()
		_hud_aliado.modulate = Color(0.7, 0.7, 0.7)
	_hud_onda.text = "Onda: %d    Inimigos: %d" % [_onda, _vivos]
	_hud_inimigos.text = "Inimigos: %s   (%s alterna)" % [("NEUTROS" if _inimigos_neutros else "HOSTIS"), Controles.tecla_de("neutro")]
	_hud_inimigos.modulate = Color(0.5, 0.9, 1.0) if _inimigos_neutros else Color(1.0, 0.6, 0.6)
