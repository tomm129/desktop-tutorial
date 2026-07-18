"""Interface de linha de comando do bot.

Uso:
  python -m betbot analisar jogos.json            # analisa e gera cartao.json
  python -m betbot cartao cartao.json             # exibe um cartão salvo
  python -m betbot apostar cartao.json            # simula na Betfair (dry-run)
  python -m betbot apostar cartao.json --real     # aposta de verdade na Betfair
  python -m betbot banca                          # status da banca
  python -m betbot banca --depositar 500
  python -m betbot banca --liquidar 3 --resultado ganha
  python -m betbot banca --historico
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis.analyzer import Analisador, encontrar_value_bets
from .bankroll.manager import GestorBanca
from .cartao import carregar_cartao, formatar_cartao, montar_cartao, salvar_cartao
from .models import Jogo


def cmd_analisar(args: argparse.Namespace) -> int:
    dados = json.loads(Path(args.jogos).read_text(encoding="utf-8"))
    jogos = [Jogo.model_validate(j) for j in dados]
    gestor = GestorBanca(args.banca_db)
    analisador = Analisador()

    todas_value_bets = []
    for jogo in jogos:
        print(f"Analisando: {jogo.time_casa} x {jogo.time_fora} ...")
        analise = analisador.analisar(jogo)
        print(f"  Resumo: {analise.resumo}")
        for alerta in analise.alertas:
            print(f"  [alerta] {alerta}")
        vbs = encontrar_value_bets(
            jogo, analise, ev_minimo=args.ev_minimo, confianca_minima=args.confianca_minima
        )
        for vb in vbs:
            print(f"  [VALUE] {vb.descricao} @ {vb.odd:.2f} (EV {vb.ev:+.1%})")
        todas_value_bets.extend(vbs)

    cartao = montar_cartao(todas_value_bets, gestor)
    salvar_cartao(cartao, args.saida)
    print()
    print(formatar_cartao(cartao))
    print(f"\nCartão salvo em: {args.saida}")
    return 0


def cmd_cartao(args: argparse.Namespace) -> int:
    print(formatar_cartao(carregar_cartao(args.cartao)))
    return 0


def cmd_apostar(args: argparse.Namespace) -> int:
    from .betfair.client import BetfairClient, OrdemAposta

    cartao = carregar_cartao(args.cartao)
    if not cartao.apostas:
        print("Cartão vazio — nada a apostar.")
        return 0

    gestor = GestorBanca(args.banca_db)
    ok, motivo = gestor.pode_apostar()
    if not ok:
        print(f"Bloqueado pela gestão de banca: {motivo}")
        return 1

    dry_run = not args.real
    if dry_run:
        print(">>> MODO SIMULAÇÃO (dry-run). Use --real para enviar de verdade. <<<\n")
    else:
        confirmacao = input(
            f"Você vai enviar {len(cartao.apostas)} aposta(s) REAIS "
            f"totalizando R$ {cartao.stake_total:.2f}. Digite 'CONFIRMO': "
        )
        if confirmacao.strip() != "CONFIRMO":
            print("Cancelado.")
            return 1

    client = BetfairClient()
    client.login()
    print("Login na Betfair OK.\n")

    for bet in cartao.apostas:
        # localiza o mercado na exchange pelo nome dos times
        nome_busca = bet.descricao.split("—")[0].strip()
        mercados = client.buscar_mercados_futebol(nome_busca.split(" x ")[0])
        if not mercados:
            print(f"[skip] Mercado não encontrado na Betfair: {bet.descricao}")
            continue
        mercado = mercados[0]
        market_id = mercado["marketId"]

        # mapeia a seleção (casa/empate/fora) para o runner correspondente
        runners = mercado.get("runners", [])
        selection_id = None
        if bet.selecao == "casa" and len(runners) > 0:
            selection_id = runners[0]["selectionId"]
        elif bet.selecao == "fora" and len(runners) > 1:
            selection_id = runners[1]["selectionId"]
        elif bet.selecao == "empate" and len(runners) > 2:
            selection_id = runners[2]["selectionId"]
        if selection_id is None:
            print(f"[skip] Seleção '{bet.selecao}' não mapeada para: {bet.descricao}")
            continue

        ordem = OrdemAposta(
            market_id=market_id,
            selection_id=selection_id,
            lado="BACK",
            odd=bet.odd,
            stake=bet.stake,
        )
        resultado = client.apostar(ordem, dry_run=dry_run)
        if dry_run:
            print(f"[simulado] {bet.descricao} @ {bet.odd:.2f} — R$ {bet.stake:.2f}")
        else:
            print(f"[ENVIADA] {bet.descricao} @ {bet.odd:.2f} — R$ {bet.stake:.2f}")
            print(f"          resposta: {resultado.get('status')}")
            gestor.registrar_aposta(bet)

    return 0


def cmd_banca(args: argparse.Namespace) -> int:
    gestor = GestorBanca(args.banca_db)

    if args.depositar:
        gestor.depositar(args.depositar)
        print(f"Depósito de R$ {args.depositar:.2f} registrado.")
    if args.sacar:
        gestor.sacar(args.sacar)
        print(f"Saque de R$ {args.sacar:.2f} registrado.")
    if args.liquidar:
        gestor.liquidar_aposta(args.liquidar, args.resultado)
        print(f"Aposta #{args.liquidar} liquidada como '{args.resultado}'.")

    est = gestor.estatisticas()
    print("\n--- BANCA ---")
    print(f"Saldo:            R$ {est['saldo']:.2f}")
    print(f"Apostas:          {est['total_apostas']} "
          f"({est['ganhas']}G / {est['perdidas']}P / {est['abertas']} abertas)")
    print(f"Taxa de acerto:   {est['taxa_acerto']:.1%}")
    print(f"Lucro liquidado:  R$ {est['lucro_liquidado']:+.2f}")
    ok, motivo = gestor.pode_apostar()
    print(f"Pode apostar:     {'sim' if ok else f'NÃO — {motivo}'}")

    if args.historico:
        print("\n--- ÚLTIMAS APOSTAS ---")
        for a in gestor.historico_apostas():
            print(f"#{a['id']} [{a['status']:8}] {a['descricao']} @ {a['odd']:.2f} "
                  f"— R$ {a['stake']:.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="betbot", description="Bot de apostas com IA")
    parser.add_argument("--banca-db", default="banca.db", help="arquivo SQLite da banca")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_an = sub.add_parser("analisar", help="analisa jogos e gera o cartão")
    p_an.add_argument("jogos", help="JSON com a lista de jogos (ver exemplos/jogos.json)")
    p_an.add_argument("--saida", default="cartao.json")
    p_an.add_argument("--ev-minimo", type=float, default=0.05)
    p_an.add_argument("--confianca-minima", type=float, default=0.5)
    p_an.set_defaults(func=cmd_analisar)

    p_ca = sub.add_parser("cartao", help="exibe um cartão salvo")
    p_ca.add_argument("cartao")
    p_ca.set_defaults(func=cmd_cartao)

    p_ap = sub.add_parser("apostar", help="envia o cartão para a Betfair")
    p_ap.add_argument("cartao")
    p_ap.add_argument("--real", action="store_true",
                      help="envia apostas de verdade (padrão é simulação)")
    p_ap.set_defaults(func=cmd_apostar)

    p_ba = sub.add_parser("banca", help="gestão de banca")
    p_ba.add_argument("--depositar", type=float)
    p_ba.add_argument("--sacar", type=float)
    p_ba.add_argument("--liquidar", type=int, metavar="APOSTA_ID")
    p_ba.add_argument("--resultado", choices=["ganha", "perdida", "anulada"], default="ganha")
    p_ba.add_argument("--historico", action="store_true")
    p_ba.set_defaults(func=cmd_banca)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
