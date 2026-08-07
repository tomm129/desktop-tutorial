// Valida o flows.json gerado:
//  1) sintaxe de todo codigo JS embutido nos nos function e nos templates
//  2) contagem de colunas do INSERT contra o tamanho das linhas montadas
const fs = require('fs');

const arq = process.argv[2];
const flow = JSON.parse(fs.readFileSync(arq, 'utf8'));

let erros = 0;
let checados = 0;

// ---- 1. Sintaxe dos nos function -----------------------------------
for (const no of flow) {
    for (const campo of ['func', 'initialize', 'finalize']) {
        const src = no[campo];
        if (typeof src !== 'string' || !src.trim()) continue;
        checados++;
        try {
            // Mesmo envelope que o Node-RED usa: corpo de funcao.
            new Function('msg', 'node', 'flow', 'global', 'context',
                         'RED', 'env', 'Buffer', src);
        } catch (e) {
            erros++;
            console.log(`FALHA sintaxe: no "${no.name || no.id}" (${campo})`);
            console.log(`   ${e.message}`);
        }
    }
}
console.log(`[1] sintaxe: ${checados} blocos JS checados, ${erros} com erro`);

// ---- 2. Coerencia do INSERT ----------------------------------------
const gravar = flow.find(n => typeof n.func === 'string'
                              && n.func.includes('INSERT INTO medicoes'));
if (!gravar) {
    console.log('[2] FALHA: no que monta o INSERT de medicoes nao encontrado');
    erros++;
} else {
    const m = gravar.func.match(/INSERT INTO medicoes \(([\s\S]*?)\)' \+\s*\n?\s*' VALUES/);
    let colunas = null;
    if (m) {
        colunas = m[1].replace(/'\s*\+\s*'/g, '').split(',')
                      .map(s => s.trim()).filter(Boolean);
    } else {
        // Fallback: junta os literais da query e extrai a lista.
        const juntos = gravar.func.match(/'INSERT INTO medicoes[\s\S]*?VALUES '/);
        if (juntos) {
            const txt = juntos[0].replace(/'\s*\+\s*'/g, '');
            const lista = txt.match(/\(([^)]*)\)/);
            if (lista) {
                colunas = lista[1].split(',').map(s => s.trim()).filter(Boolean);
            }
        }
    }

    if (!colunas) {
        console.log('[2] FALHA: nao consegui extrair a lista de colunas');
        erros++;
    } else {
        console.log(`[2] INSERT declara ${colunas.length} colunas:`);
        console.log('    ' + colunas.join(', '));

        // Conta os elementos de cada linhas.push([...]) do codigo.
        const empurroes = [...gravar.func.matchAll(/linhas\.push\(\[([\s\S]*?)\n\s*\]\)/g)];
        if (!empurroes.length) {
            console.log('[2] FALHA: nenhum linhas.push([...]) encontrado');
            erros++;
        }
        empurroes.forEach((mm, i) => {
            // Remove comentarios de linha antes de contar virgulas.
            const corpo = mm[1].split('\n')
                               .map(l => l.replace(/\/\/.*$/, ''))
                               .join('\n');
            // Conta virgulas em profundidade 0 (fora de parenteses/colchetes).
            let prof = 0, n = 1, emStr = null;
            for (let k = 0; k < corpo.length; k++) {
                const c = corpo[k];
                if (emStr) { if (c === emStr && corpo[k - 1] !== '\\') emStr = null; continue; }
                if (c === "'" || c === '"') { emStr = c; continue; }
                if (c === '(' || c === '[' || c === '{') prof++;
                else if (c === ')' || c === ']' || c === '}') prof--;
                else if (c === ',' && prof === 0) n++;
            }
            const ok = n === colunas.length;
            if (!ok) erros++;
            console.log(`    [${ok ? 'OK ' : 'FALHA'}] linha #${i + 1}: ${n} valores `
                        + `(esperado ${colunas.length})`);
        });
    }
}

console.log();
console.log(erros === 0 ? 'RESULTADO: tudo certo.' : `RESULTADO: ${erros} problema(s).`);
process.exit(erros === 0 ? 0 : 1);
