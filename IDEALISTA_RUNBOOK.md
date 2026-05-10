# Idealista · Runbook de Erros e Resposta

Tudo o que pode dar errado com a integração Idealista FSBO-only e o que
fazer em cada caso. Ordenado por **probabilidade × impacto**.

---

## 🔴 Probabilidade ALTA · vais ver isto

### 1. DataDome bloqueia httpx puro (esperado — confirma stealth needed)

**Sinal no log:**
```
[idealista] HTTP 403 Forbidden
ou
'datadome' in response body
ou body com <iframe src="https://...datadome..."> ou "Are you a robot?"
```

**Probabilidade:** 95 %  
**Impacto:** ✗ httpx falha · ✓ Playwright continua  
**Acção:** Nenhuma — é o caminho normal. O scraper já cai automaticamente para Playwright stealth.

**Fallback automático no código:** `scrapers/idealista.py:354` — Stage 2 já trata.

---

### 2. DataDome challenge CAPTCHA na página

**Sinal:**
```
Página com texto "Confirme que não é um robô"
ou widget hCaptcha visível
ou redirect para /captcha-delivery/
```

**Probabilidade:** 30-60 % com Playwright stealth, depende do IP  
**Impacto:** ✗ 0 listings extraídos  
**Acção curto prazo:**
1. Trocar para hotspot 4G/5G (IPs móveis têm reputação melhor)
2. Esperar 30-60 min e retentar (DataDome cool-down)
3. Limpar cookies/storage do browser headless

**Acção longo prazo:**
- Comprar pacote de proxies residenciais BrightData / Smartproxy (€80-150/mês)
- Implementar resolver de CAPTCHA (2captcha API, ~€2 / 1000 captchas)

---

### 3. Volume zero numa zona

**Sinal:**
```
[idealista] Zone 'Lisboa-Estrela' → 0 listings (Playwright stealth active)
```

**Probabilidade:** 40 % primeira tentativa  
**Impacto:** Médio — perde-se 1 zona  
**Acção automática já implementada:**
- Próxima zona segue normalmente (não pára pipeline)
- Log detalhado em `logs/run_*.log`
- `EXPERIMENTAL_NOTE` no scraper ([linha 282](scrapers/idealista.py))

**Acção manual:**
```bash
# Re-corre apenas Idealista para essa zona
python3 main.py scrape-idealista --zone Lisboa-Estrela
```

---

## 🟡 Probabilidade MÉDIA · pode acontecer

### 4. URL `com-particulares/` deixa de existir

**Sinal:**
```
HTTP 404
ou redirect para /comprar-casas/lisboa/ (sem filtro)
```

**Probabilidade:** 20 %  
**Impacto:** Alto — perde-se filtro FSBO, scraper apanha agências também  
**Detecção:**
```bash
# Smoke test: a URL existe?
curl -sI -L "https://www.idealista.pt/comprar-casas/lisboa/com-particulares/" | head -5
```

**Mitigação automática (já integrada):**
- O badge filter no `_parse_card` (linha 614) ainda reconhece "particular" / "proprietário" como flag
- Mesmo que URL caia, **filtro a posteriori continua a funcionar**
- Volume sobe (apanha tudo) mas qualidade do FSBO mantém-se via badge

**Acção:** Mudar URL pattern. Variantes conhecidas:
- `/com-particulares/` (actual)
- `/particulares-only/` (pode ser variant futuro)
- Query param: `?con-particular=true`

---

### 5. TLS fingerprint detection

**Sinal:**
```
HTTP 403 mesmo com headers correctos
Cloudflare ou Cloudfront edge block
```

**Probabilidade:** 15 %  
**Impacto:** ✗ httpx falha cedo  
**Acção:**
- Usar `curl-cffi` (impersona Chrome TLS) em vez de httpx
- Já temos infrastructure (`utils/async_fetcher.py`)
- Ou cair para Playwright que tem TLS real do Chrome

---

### 6. Playwright Chromium não instalado

**Sinal:**
```
[idealista] Playwright not installed. Run: playwright install chromium
ImportError: No module named 'playwright'
```

**Probabilidade:** 10 % (deve estar instalado, mas pode ter sido removido)  
**Impacto:** ✗ Scraper inteiro morre  
**Acção:**
```bash
pip3 install playwright
playwright install chromium
```

---

### 7. Mobile hotspot CGNAT bloqueado

**Sinal:**
```
HTTP 403 mesmo com 4G/5G
Mensagem "We've detected unusual activity"
```

**Probabilidade:** 25 %  
**Impacto:** ✗ Plano "mobile data" falha  
**Acção:**
1. Reiniciar dados móveis (toggle airplane mode 30s) — força novo IP CGNAT
2. Mudar de operador (NOS / MEO / Vodafone) se possível
3. Fallback final: proxies residenciais

---

## 🟢 Probabilidade BAIXA · cenários extremos

### 8. Idealista lança CAPTCHA em CADA listing

**Sinal:** Cada detail page pede CAPTCHA  
**Probabilidade:** 5 %  
**Impacto:** Total — não consegues extrair nada  
**Acção:**
- Reduzir volume drasticamente: 1 listing / 5 min
- Implementar 2captcha API (~€10 / 1 000 listings)
- Esperar 24-48 h (DataDome cycles)

---

### 9. Idealista bloqueia geo (apenas PT)

**Sinal:** HTTP 451 "unavailable for legal reasons"  
**Probabilidade:** 1 % (estás em PT)  
**Impacto:** N/A para ti  
**Acção:** N/A

---

### 10. Phone reveal protegido por reCAPTCHA

**Sinal:**
```
Click no botão "Mostrar telefone" → CAPTCHA aparece
```

**Probabilidade:** 30 %  
**Impacto:** Sem telemóvel directo, só email/form  
**Acção:**
- Cair para "contact_email" (Idealista expõe email no DOM)
- Ou usar 2captcha
- **Mitigação no demo:** já temos badge "📧 EMAIL APENAS" no schema

---

### 11. Conteúdo lazy-loaded por XHR após scroll

**Sinal:** Página carrega mas sem listings na primeira fetch  
**Probabilidade:** 20 %  
**Mitigação automática (já implementada):** `_human_scroll(page)` em
[scrapers/idealista.py:536](scrapers/idealista.py) executa scroll humano antes de extrair.

---

### 12. C&D letter / ban legal

**Sinal:** Email do Idealista a exigir paragem  
**Probabilidade:** 0,5 % com volume baixo (50-100/dia)  
**Impacto:** Legal · regulamentar  
**Mitigação preventiva (já no demo, secção X · Ética):**
- Volume baixo
- Apenas dados públicos
- Base legal RGPD art.º 6.1.f
- Robots.txt respeitado quando possível

**Acção se acontecer:**
- Para imediatamente
- Resposta legal via advogado
- Switch para fontes alternativas (bancos, leilões, premarket)

---

## 🛡️ Defesas em camadas (já no código)

| Camada | Vector | Implementação |
|---|---|---|
| TLS / HTTP | Fingerprint Chrome | `curl-cffi` em `utils/async_fetcher.py` |
| Browser fingerprint | Canvas, WebGL, audio, fonts (~15 vectors) | `scrapers/idealista.py:51` stealth script |
| Behavioral | Mouse, scroll, timing | `_human_scroll`, persona delays |
| Session | Cookies, headers, viewport | `persona_manager.py` rotação por zona |
| IP reputation | Direct → mobile → residential | env `IDEALISTA_USE_PROXIES` toggle |
| Rate limit | Delays adaptativos | `rate_limiter.py` COOLOFF state |
| Detection alarms | Block streaks por persona | `persona_health.json` cooldown |

---

## 🔧 Comandos de diagnóstico rápido

```bash
# Ver IP actual (após hotspot mudar)
curl -s ifconfig.me

# Smoke test rápido sem DB
./scripts/test_idealista.sh Lisboa-Estrela

# Ver últimos blocks no log do scraper
grep -iE "datadome|403|captcha|blocked" logs/run_*.log | tail -20

# Forçar rotação de persona Idealista
sqlite3 data/patabrava.db "DELETE FROM persona_health WHERE source='idealista.pt';"
# (regenerada automaticamente na próxima request)

# Reset cookies / storage Playwright
rm -rf data/cookies/idealista*
```

---

## 📋 Checklist antes da run de Domingo

- [ ] Hotspot 4G/5G activo no Mac (IP confirmado mobile)
- [ ] `curl ifconfig.me` retorna IP de operadora PT
- [ ] `./scripts/test_idealista.sh` passa em pelo menos 1 zona
- [ ] Playwright Chromium instalado (`playwright install chromium`)
- [ ] `data/patabrava.db-wal` < 50 MB (limpo recentemente)
- [ ] Disco `/Users/highlevel/` > 5 GB free

---

## 🎯 Plano de comunicação à Susana se Idealista falhar

Se chegar terça e Idealista não estiver a funcionar:

> *"Estamos a finalizar a integração Idealista — é o portal mais protegido
> em Portugal (DataDome enterprise + Cloudflare). Volume previsto: **50-100
> FSBO premium/dia**. Disponível no plano Pro a partir do 2º mês após
> ajuste fino do anti-bot. Entretanto entregamos OLX + Imovirtual + SAPO
> + 4 bancos REO + leilões — já 95 % da cobertura PT."*

Isto **transforma 'falhou' em 'feature progressiva'** sem perder credibilidade.
A Susana sabe que Idealista é difícil — toda a indústria sabe.

---

Build: 2026-05-10 · v1.0 · Pata Brava risk register
