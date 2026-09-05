extends RefCounted
class_name Classes
# Tabela das classes. É o único lugar onde se mexe para balancear o jogo —
# o Personagem.gd só lê daqui, não tem número de classe espalhado no código.
#
# RECURSO: cada classe tem o seu, com nome, cor e regra propria (a ideia veio
# das arvores de talento: Rage, Energy, Holiness, Faith, Mana, Focus, Nature).
#   "tempo"   enche sozinho com o tempo (mana, energia, foco, fe, natureza)
#   "combate" comeca vazio e enche batendo e apanhando (furia do guerreiro,
#             fervor do paladino) -- premia quem entra na briga
# A habilidade (Q) so sai se houver recurso; a recarga sozinha deixou de ser o
# unico limite.
#
# ataque:
#   "reto"      projétil comum
#   "explosivo" projétil que estoura numa área ao acertar
#   "gelado"    projétil que deixa o inimigo lento
#   "arco"      corpo a corpo: acerta todo mundo num leque à sua frente
#
# habilidade (tecla Q), cada uma com a sua recarga:
#   "giro"      dano em todo mundo em volta
#   "escudo"    escudo para a party inteira
#   "aura"      cura por segundo em quem estiver perto
#   "nova"      dano grande em área, em volta
#   "leque"     dispara vários projéteis de uma vez
#   "raizes"    prende os inimigos no lugar
#   "investida" avança para a frente machucando quem atravessar

const ORDEM := ["guerreiro", "paladino", "clerigo", "mago", "arqueiro", "druida", "assassino"]

const DADOS := {
	"guerreiro": {
		"nome": "Guerreiro", "cor": Color(0.85, 0.35, 0.25),
		"vida": 160, "velocidade": 265, "cadencia": 0.45, "dano": 40,
		"ataque": "arco", "alcance": 78,
		"habilidade": "giro", "hab_nome": "Golpe giratório",
		"recarga": 8.0, "hab_dano": 55, "hab_raio": 135.0,
		"recurso": "Fúria", "cor_recurso": Color(0.85, 0.15, 0.12),
		"recurso_max": 100, "recurso_tipo": "combate", "recurso_ganho": 9, "custo_hab": 45,
		"resumo": "Casca grossa. Bate perto e forte.",
	},
	"paladino": {
		"nome": "Paladino", "cor": Color(0.95, 0.8, 0.3),
		"vida": 150, "velocidade": 255, "cadencia": 0.55, "dano": 34,
		"ataque": "arco", "alcance": 84,
		"habilidade": "escudo", "hab_nome": "Escudo sagrado",
		"recarga": 14.0, "hab_duracao": 4.0, "hab_raio": 210.0,
		"recurso": "Fervor", "cor_recurso": Color(0.98, 0.80, 0.25),
		"recurso_max": 100, "recurso_tipo": "combate", "recurso_ganho": 8, "custo_hab": 50,
		"resumo": "Aguenta pancada e blinda a party inteira.",
	},
	"clerigo": {
		"nome": "Clérigo", "cor": Color(0.6, 0.9, 0.7),
		"vida": 110, "velocidade": 290, "cadencia": 0.35, "dano": 18,
		"ataque": "reto", "alcance": 460,
		"habilidade": "aura", "hab_nome": "Aura de cura",
		"recarga": 12.0, "hab_duracao": 4.0, "hab_raio": 145.0, "hab_cura": 10.0,
		"recurso": "Fé", "cor_recurso": Color(0.92, 0.92, 0.98),
		"recurso_max": 100, "recurso_tipo": "tempo", "recurso_regen": 7.0, "custo_hab": 40,
		"resumo": "Ataque fraco, mas segura a party viva.",
	},
	"mago": {
		"nome": "Mago", "cor": Color(0.65, 0.45, 1.0),
		"vida": 90, "velocidade": 275, "cadencia": 0.62, "dano": 28,
		"ataque": "explosivo", "alcance": 470, "raio_estouro": 72.0, "dano_estouro": 22,
		"habilidade": "nova", "hab_nome": "Nova de fogo",
		"recarga": 10.0, "hab_dano": 70, "hab_raio": 175.0,
		"recurso": "Mana", "cor_recurso": Color(0.30, 0.55, 1.0),
		"recurso_max": 100, "recurso_tipo": "tempo", "recurso_regen": 6.0, "custo_hab": 45,
		"custo_ataque": 6,
		"resumo": "Frágil. Cada tiro estoura numa área.",
	},
	"arqueiro": {
		"nome": "Arqueiro", "cor": Color(0.4, 0.85, 0.45),
		"vida": 100, "velocidade": 310, "cadencia": 0.22, "dano": 22,
		"ataque": "reto", "alcance": 620,
		"habilidade": "leque", "hab_nome": "Chuva de flechas",
		"recarga": 7.0, "hab_tiros": 7, "hab_abertura": 70.0,
		"recurso": "Foco", "cor_recurso": Color(0.75, 0.90, 0.25),
		"recurso_max": 100, "recurso_tipo": "tempo", "recurso_regen": 16.0, "custo_hab": 35,
		"custo_ataque": 4,
		"resumo": "Rápido, atira de longe e sem parar.",
	},
	"druida": {
		"nome": "Druida", "cor": Color(0.45, 0.8, 0.55),
		"vida": 120, "velocidade": 285, "cadencia": 0.40, "dano": 20,
		"ataque": "gelado", "alcance": 430, "lentidao": 0.45, "tempo_lentidao": 2.0,
		"habilidade": "raizes", "hab_nome": "Raízes",
		"recarga": 11.0, "hab_duracao": 2.6, "hab_raio": 165.0,
		"recurso": "Natureza", "cor_recurso": Color(0.35, 0.85, 0.40),
		"recurso_max": 100, "recurso_tipo": "tempo", "recurso_regen": 8.0, "custo_hab": 40,
		"resumo": "Segura a horda: tiro lento e raízes que prendem.",
	},
	"assassino": {
		"nome": "Assassino", "cor": Color(0.55, 0.5, 0.75),
		"vida": 85, "velocidade": 345, "cadencia": 0.15, "dano": 16,
		"ataque": "arco", "alcance": 62,
		"habilidade": "investida", "hab_nome": "Investida",
		"recarga": 6.0, "hab_dano": 45, "hab_distancia": 260.0,
		"recurso": "Energia", "cor_recurso": Color(0.45, 0.95, 0.45),
		"recurso_max": 100, "recurso_tipo": "tempo", "recurso_regen": 22.0, "custo_hab": 30,
		"custo_ataque": 7,
		"resumo": "Vidro. Muito rápido, golpes secos e curtos.",
	},
}

static func dados(classe: String) -> Dictionary:
	return DADOS.get(classe, DADOS["guerreiro"])

# Devolve o valor da classe, ou o padrão se aquela classe não usa esse campo.
static func campo(classe: String, chave: String, padrao):
	return dados(classe).get(chave, padrao)

static func animacoes(classe: String) -> String:
	return "res://Animacoes_%s.tres" % classe
