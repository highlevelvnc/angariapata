#!/bin/bash
# Smoke-test do Idealista FSBO-only.
#
# Uso:
#   1. Liga hotspot 4G/5G do telemóvel ao Mac (USB tethering ou WiFi)
#   2. Confirma a ligação:    curl -s ifconfig.me     (vê o IP novo)
#   3. ./scripts/test_idealista.sh
#
# O que faz:
#   - Testa http nu primeiro (rápido, sem Playwright) numa zona
#   - Depois Playwright com stealth profile completo
#   - Reporta: nº listings devolvidos, se DataDome bloqueou, IPs de rede
#   - NÃO escreve nada na DB (modo isolado)

set -u
cd "$(dirname "$0")/.."

ZONE="${1:-Lisboa-Estrela}"
LOG="logs/idealista_smoketest_$(date +%Y%m%d_%H%M%S).log"

echo "═══════════════════════════════════════════════════════════"
echo "  IDEALISTA · SMOKE TEST · zona=$ZONE"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════════"
echo

echo "→ IP actual de saída:"
EXTERNAL_IP=$(curl -s --max-time 5 https://ifconfig.me || echo "?")
echo "  $EXTERNAL_IP"
echo

echo "→ Confirma se a ligação é mobile data (procura prefixos PT mobile como 89.x, 95.x, 81.x):"
if [[ "$EXTERNAL_IP" =~ ^(89|95|81|85|193|62)\. ]]; then
  echo "  ⚠ Possivelmente fixed line (residencial / fibra). Testar com fibra primeiro é razoável."
else
  echo "  ✓ Pode ser mobile (mas confirmaa pelo provider)."
fi
echo

echo "→ Stage 1 · httpx puro (sem Playwright, ver se DataDome cookia logo):"
IDEALISTA_FSBO_ONLY=1 python3 -c "
import os, sys
sys.path.insert(0, '.')
from scrapers.idealista import IdealistaScraper, BASE_URL, _ZONE_KEYS
import httpx

zone = '$ZONE'
slug = _ZONE_KEYS.get(zone)
url = f'{BASE_URL}/comprar-casas/{slug}/com-particulares/'
print(f'  URL: {url}')

ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15'
try:
    r = httpx.get(url, headers={'User-Agent': ua}, timeout=15, follow_redirects=True)
    body_size = len(r.text)
    blocked = 'datadome' in r.text.lower() or 'are you a robot' in r.text.lower()
    print(f'  Status: {r.status_code}')
    print(f'  Body: {body_size} bytes')
    print(f'  DataDome no HTML: {blocked}')
    if r.status_code == 200 and body_size > 50000 and not blocked:
        print('  ✓ HTTP simples passou. DataDome dormiu desta vez.')
    else:
        print('  ✗ HTTP simples bloqueado/insuficiente. Vamos testar Playwright.')
except Exception as e:
    print(f'  ✗ Erro: {type(e).__name__}: {e}')
" 2>&1 | tee -a "$LOG"
echo

echo "→ Stage 2 · Playwright com stealth (real test):"
IDEALISTA_FSBO_ONLY=1 python3 <<'PY' 2>&1 | tee -a "$LOG"
import asyncio, sys
sys.path.insert(0, '.')
from scrapers.idealista import IdealistaScraper

async def smoke():
    s = IdealistaScraper()
    items = await s._async_scrape_zone('Lisboa-Estrela')
    print(f'  Listings retornados: {len(items)}')
    if items:
        for it in items[:5]:
            print(f'    · {it.get("title","—")[:60]}  ·  {it.get("price_raw","—")}  ·  zone={it.get("zone","—")}')
        print(f'  ✓ FUNCIONA — Idealista FSBO está vivo nesta ligação.')
    else:
        print(f'  ✗ 0 listings · DataDome provavelmente bloqueou. Tenta com hotspot 4G/5G.')

asyncio.run(smoke())
PY

echo
echo "═══════════════════════════════════════════════════════════"
echo "  Log completo: $LOG"
echo "═══════════════════════════════════════════════════════════"
echo
echo "Próximos passos consoante o resultado:"
echo "  ✓ Funcionou       →  python3 -c \"from config.sources_registry import SOURCE_REGISTRY; SOURCE_REGISTRY['idealista'].is_active = True\""
echo "                       (mas é melhor editar config/sources_registry.py manualmente)"
echo "  ✗ Falhou em fibra →  liga hotspot 4G/5G e re-corre este script"
echo "  ✗ Falhou em 4G    →  precisamos proxies residenciais (€100-200/mês)"
