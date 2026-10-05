# vpn2router

Transforma contas ProtonVPN em proxies HTTP com entrada unica (rede interna).

```
[seu app] --user hotel / otavio-1--> http://vpn-router:8888 --> vpn-1 | vpn-2 ... --> internet via Proton
```

## Regra de roteamento

Cadastro base (`ROUTER_USERS=hotel:senha,otavio:senha`):

| Login usado | Vai para |
|---|---|
| `hotel` | backend aleatorio (load balance) |
| `otavio-1`, `otavio#1`, `otavio_1` | sempre `vpn-1` |
| `otavio-2` | sempre `vpn-2` |

HTTP puro (GET + CONNECT). SOCKS5 nao suportado (proxy embutido do Gluetun e HTTP-only).

## 10 conexoes, 1 conta

O compose sobe `vpn-1..vpn-10` usando a MESMA conta Proton (`PROTON_USER_1`). A Proton permite 10 conexoes simultaneas por conta, entao cada tunel conta como 1.

| Login usado | Vai para |
|---|---|
| `otavio-1` ... `otavio-10` | sempre `vpn-1` ... `vpn-10` (fixo) |
| `hotel` (sem sufixo) | backend aleatorio entre os 10 |
| `otavio-rotate` / `otavio-livre` / `otavio_free` / `otavio#rotate` | backend com ZERO conexoes ativas; se todos ocupados, erro HTTP 503 |

Cada `vpn-N` escolhe um servidor Proton aleatorio (dentro de `SERVER_COUNTRIES_1`), entao os IPs de saida tendem a ser distintos. Para uma 2a conta (+10 tuneis), duplique os blocos com `PROTON_USER_2` e estenda o `HTTP_UPSTREAMS`.

## 1. Credenciais Proton

Nao e o login do site. Em account.protonvpn.com > Account > OpenVPN / IKEv2 username: gere usuario/senha e use em `PROTON_USER_N` / `PROTON_PASS_N`. Cada conta aguenta 10 conexoes simultaneas.

## 2. Subir (local)

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f vpn-router
```

Debug local: descomente o bloco `ports:` do `vpn-router` no compose e teste:

```bash
curl -x http://hotel:SENHA@127.0.0.1:8888 ifconfig.me
curl -x http://otavio-1:SENHA@127.0.0.1:8888 ifconfig.me
```

IPs diferentes = cada backend saiu por um tunel Proton distinto. Depois volte a comentar o `ports:` antes de subir em producao.

## 3. Coolify (producao, rede interna)

O compose nao expoe nenhuma porta por padrao. No Coolify:

1. Deploy este repo como um servico (Docker Compose).
2. Coloque as variaveis do `.env.example` como Environment Variables do recurso (marque as senhas como secret).
3. No app cliente (mesmo servidor/projeto), use o endereco interno:
   - `http://vpn-router:8888` (mesma Docker network gerenciada pelo Coolify)
   - Se o app estiver em outro compose/projeto, conecte-o na mesma network ou use o nome DNS que o Coolify gerar.
4. No cliente: `http_proxy=http://otavio-1:SENHA@vpn-router:8888` + `https_proxy=` igual.

`FIREWALL_OUTBOUND_SUBNETS` ja libera `10/8,172.16/12,192.168/16` para o router alcancar os tuneis.

## 4. Escalar

```bash
./scripts/add-vpn.sh 3
```

Cole o bloco no `docker-compose.yml` e adicione `vpn-3:8888` em `HTTP_UPSTREAMS`.

## Notas

- WireGuard e mais rapido que OpenVPN; para trocar, gere config WireGuard e ajuste `VPN_TYPE=wireguard` no compose.
- Logs limitados a 10MB x 3 arquivos por servico; `ROUTER_DEBUG=on` ativa log por requisicao.
