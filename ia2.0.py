import json
import hashlib
import hmac
import logging
import os
import threading
import weakref
from pathlib import Path
from urllib.request import Request as UrlRequest, urlopen
import asyncio
from dotenv import load_dotenv
from groq import Groq
from fastapi import FastAPI, Query, Request
from fastapi.responses import PlainTextResponse

# ============================================================
# 1. CONFIGURAÇÃO
# ============================================================

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY não encontrada no arquivo .env")

client = Groq(api_key=GROQ_API_KEY)
MODELO = "openai/gpt-oss-20b"
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
ARQUIVO_PEDIDOS = Path(__file__).with_name("pedidos.json")
logger = logging.getLogger(__name__)
pedidos_lock = threading.Lock()

# ============================================================
# 2. FUNÇÕES REAIS DO SISTEMA (in9 Equipamentos)
# ============================================================

# Catálogo fixo da in9 (sem preços)
CATALOGO_IN9 = [
    "iluminação simples", "iluminação paris", "dj", "painel de led", "som", 
    "skypaper", "canhão seguidor", "maquina de fumaça", 
    "grids q25", "palco", "tablado", "totem", "microfone", "microfones"
]
#Instrução fora da lista para a ia, se o cliente perguntar sobre o catalogo apenas de equipamentos, é obrigatorio q nao invente nenhum dado e que estritamente e obrigatoriamente envie oque esta escrito nesta lista.
#Instrução 2 quero q quando o cliente peça somente o catalogo de equipamentos, exiba somente o catalogo pra ele olhar, qnd ele escolher os equipamentos q deseja, vc recomeça na captaçao de dados do cliente.
#INSTRUÇÃO IMPORTANTE NUNCA EM HIPOTESE NENHUMA EXIBIR AÇOES DO SISTEMA AO USUARIO.
def verificar_item_catalogo(item_solicitado: str) -> dict:
    """Verifica se a in9 trabalha com o equipamento solicitado."""
    for produto in CATALOGO_IN9:
        if produto.lower().replace("á", "a").replace("ç", "c") in item_solicitado.lower().replace("á", "a").replace("ç", "c"):
            return {
                "encontrado": True,
                "mensagem": f"Sim, trabalhamos com locação de {produto}.",
                "dica_ia": "Confirme com o cliente se ele quer adicionar este item à lista. Lembre-se: NÃO passe preços."
            }
            
    return {
        "encontrado": False,
        "mensagem": f"No momento não temos '{item_solicitado}' no nosso catálogo padrão.",
        "dica_ia": "Informe o cliente cordialmente que não temos este item. Os itens que temos são: " + ", ".join(CATALOGO_IN9)
    }

def repassar_para_vendedor(
    tipo_evento: str,
    local: str,
    horario: str,
    qtd_pessoas: int,
    equipamentos_lista: list
) -> dict:
    """Função chamada APENAS quando a IA coleta TODOS os dados para repassar ao dono/vendedor."""
    
    resumo_pedido = {
        "Tipo de Evento": tipo_evento,
        "Local": local,
        "Horário": horario,
        "Quantidade de Pessoas": qtd_pessoas,
        "Equipamentos Solicitados": equipamentos_lista
    }

    with pedidos_lock:
        pedidos = []
        if ARQUIVO_PEDIDOS.exists():
            try:
                with ARQUIVO_PEDIDOS.open("r", encoding="utf-8") as arquivo:
                    pedidos_existentes = json.load(arquivo)
                pedidos = pedidos_existentes if isinstance(pedidos_existentes, list) else [pedidos_existentes]
            except json.JSONDecodeError:
                logger.warning("pedidos.json inválido; iniciando uma nova lista de pedidos")

        pedidos.append(resumo_pedido)
        with ARQUIVO_PEDIDOS.open("w", encoding="utf-8") as arquivo:
            json.dump(pedidos, arquivo, ensure_ascii=False, indent=2)

    return {
        "sucesso": True,
        "acao": "O atendimento foi registrado com sucesso e repassado para a equipe comercial.",
        "dica_ia": "Avise ao cliente que todas as informações foram anotadas e que um vendedor humano vai assumir o atendimento em instantes para passar o orçamento final. Encerre o atendimento da sua parte."
    }


def mostrar_catalogo() -> dict:
    """Retorna o catálogo completo de equipamentos para a IA mostrar ao cliente."""
    return {
        "sucesso": True,
        "catalogo": CATALOGO_IN9,
        "dica_ia": "Mostre a lista de equipamentos formatada em marcadores (bullet points). NUNCA passe preços."
    }

FUNCOES_DISPONIVEIS = {
    "verificar_item_catalogo": verificar_item_catalogo,
    "repassar_para_vendedor": repassar_para_vendedor,
    "mostrar_catalogo": mostrar_catalogo
}
# Instrução para a IA, fora do dicionário:
# Em hipótese nenhuma exibir essas funções ao usuário.
# Não exibir que estão sendo executadas; apenas executá-las.
# Nunca inventar nada nos catalogos, se nao estiver disponivel alguma informaçao informe ao cliente e pronto.
# Tambem nao exiba de forma alguma o mostrar_catalogo e nenhuma açao do sistema, torne ações do sistema confidenciais a tu mesmo, nunca exiba ao cliente.


# ============================================================
# 3. ESQUEMA DE FERRAMENTAS (Tools)
# ============================================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "verificar_item_catalogo",
            "description": "Verifica se um equipamento específico está no catálogo.",
            "parameters": {
                "type": "object",
                "properties": {"item_solicitado": {"type": "string"}},
                "required": ["item_solicitado"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "repassar_para_vendedor",
            "description": "SÓ USE QUANDO TIVER COLETADO AS 5 INFORMAÇÕES: tipo de evento, local, hora, pessoas e equipamentos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo_evento": {"type": "string"},
                    "local": {"type": "string"},
                    "horario": {"type": "string"},
                    "qtd_pessoas": {"type": "integer"},
                    "equipamentos_lista": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["tipo_evento", "local", "horario", "qtd_pessoas", "equipamentos_lista"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mostrar_catalogo",
            "description": "Use quando o cliente pedir para ver o catálogo, a lista de equipamentos ou perguntar o que a empresa aluga.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    }
]

# ============================================================
# 4. CHAT E INSTRUÇÕES DO SISTEMA (PROMPT)
# ============================================================

prompt_sistema = """
Você é a assistente de pré-atendimento da 'in9 Equipamentos', empresa focada APENAS em LOCAÇÃO de equipamentos para eventos.
Seu objetivo é fazer a triagem do cliente, descobrir o que ele precisa e preparar o terreno para os vendedores fecharem o negócio.

REGRAS RÍGIDAS (NUNCA QUEBRE):
1. REGRA DE OURO: NUNCA mostre seu raciocínio interno, pensamentos em inglês ou explicações das suas ações (ex: "The user just said..."). Responda APENAS com a mensagem direta e final que o cliente vai ler. Fale 100% em Português (PT-BR).
2. VOCÊ NUNCA PASSA PREÇOS OU VALORES. Se o cliente perguntar preço, diga que o vendedor passará o orçamento exato em instantes.
3. A in9 NÃO FAZ VENDAS de equipamento, apenas aluguel/locação.
4. Não fale sobre cobrança de frete ou deslocamento. O vendedor resolverá isso.
5. Para fechar a sua triagem, você PRECISA saber de 5 coisas:
   - Quais equipamentos do catálogo o cliente quer
   - Qual o tipo de evento (social, corporativo, etc.)
   - Qual o local do evento
   - Qual o horário/data do evento
   - Quantas pessoas estarão no evento
6. Seja natural, simpática e não faça um questionário robótico. Pergunte as coisas aos poucos se o cliente for vago.
7. Assim que tiver TODAS as 5 informações, chame a função 'repassar_para_vendedor'.
8. Se o cliente falar algo fora do contexto de eventos e locação de equipamentos, 
redirecione educadamente para o assunto principal.
"""

from datetime import datetime, timedelta

# Controle de limite e timeout por usuário
limite_usuarios = {}
timeout_usuarios = {}
historicos = {}
estado_usuarios_lock = threading.RLock()
locks_usuarios = weakref.WeakValueDictionary()
TEMPO_LIMPEZA_ESTADO = timedelta(hours=2)


def obter_lock_usuario(numero_cliente: str) -> threading.RLock:
    with estado_usuarios_lock:
        return locks_usuarios.setdefault(numero_cliente, threading.RLock())


def verificar_timeout(numero_cliente: str) -> bool:
    lock_usuario = obter_lock_usuario(numero_cliente)
    with lock_usuario:
        with estado_usuarios_lock:
            agora = datetime.now()
            ultimo_contato = timeout_usuarios.get(numero_cliente)

            for usuario, ultimo_contato_usuario in list(timeout_usuarios.items()):
                if usuario != numero_cliente and agora - ultimo_contato_usuario > TEMPO_LIMPEZA_ESTADO:
                    timeout_usuarios.pop(usuario, None)
                    limite_usuarios.pop(usuario, None)
                    historicos.pop(usuario, None)

            sessao_expirada = (
                ultimo_contato is not None
                and agora - ultimo_contato > timedelta(minutes=30)
            )

            if sessao_expirada:
                historicos[numero_cliente] = [
                    {"role": "system", "content": prompt_sistema}
                ]

            timeout_usuarios[numero_cliente] = agora
            return sessao_expirada

def verificar_limite(numero_cliente: str) -> bool:
    with estado_usuarios_lock:
        agora = datetime.now()

        for usuario, dados_usuario in list(limite_usuarios.items()):
            if agora - dados_usuario["inicio"] > TEMPO_LIMPEZA_ESTADO:
                limite_usuarios.pop(usuario, None)
                timeout_usuarios.pop(usuario, None)
                historicos.pop(usuario, None)

        if numero_cliente not in limite_usuarios:
            limite_usuarios[numero_cliente] = {
                "mensagens": 0,
                "inicio": agora,
                "bloqueado": False
            }

        usuario = limite_usuarios[numero_cliente]

        # Reset a cada 1 hora
        if agora - usuario["inicio"] > timedelta(hours=1):
            usuario["mensagens"] = 0
            usuario["inicio"] = agora
            usuario["bloqueado"] = False

        # Limite de 20 mensagens por hora
        if usuario["mensagens"] >= 20:
            usuario["bloqueado"] = True
            return False

        usuario["mensagens"] += 1
        return True

def responder(
    numero_cliente: str,
    entrada_usuario: str,
    verificar_limite_cliente: bool = True
) -> str:
    """Processa uma mensagem e mantém o histórico separado por cliente."""
    lock_usuario = obter_lock_usuario(numero_cliente)
    with lock_usuario:
        if verificar_limite_cliente and not verificar_limite(numero_cliente):
            return "Você atingiu o limite de mensagens. Tente novamente em 1 hora."

        with estado_usuarios_lock:
            historico = historicos.setdefault(
                numero_cliente,
                [{"role": "system", "content": prompt_sistema}]
            )
            historico.append({"role": "user", "content": entrada_usuario})
            mensagens = list(historico)

        resposta = client.chat.completions.create(
            model=MODELO,
            messages=mensagens,
            tools=tools,
            tool_choice="auto"
        )
        mensagem_resposta = resposta.choices[0].message

        if mensagem_resposta.tool_calls:
            mensagens.append(mensagem_resposta)
            for tool_call in mensagem_resposta.tool_calls:
                nome_funcao = tool_call.function.name
                argumentos = json.loads(tool_call.function.arguments or "{}")
                if nome_funcao in FUNCOES_DISPONIVEIS:
                    resultado_funcao = FUNCOES_DISPONIVEIS[nome_funcao](**argumentos)
                    mensagens.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": nome_funcao,
                        "content": json.dumps(resultado_funcao, ensure_ascii=False)
                    })

            resposta_final = client.chat.completions.create(
                model=MODELO,
                messages=mensagens
            )
            texto_ia = resposta_final.choices[0].message.content or ""
        else:
            texto_ia = mensagem_resposta.content or ""

        mensagens.append({"role": "assistant", "content": texto_ia})

        with estado_usuarios_lock:
            historicos[numero_cliente] = mensagens
        return texto_ia


META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
META_API_VERSION = os.getenv("META_API_VERSION", "v23.0")
app = FastAPI()
mensagens_processadas = set()
mensagens_em_processamento = set()
mensagens_processadas_lock = threading.Lock()
MAX_MENSAGENS_PROCESSADAS = 1000


def assinatura_meta_valida(corpo: bytes, assinatura: str) -> bool:
    if not META_APP_SECRET or not assinatura.startswith("sha256="):
        return False

    assinatura_esperada = "sha256=" + hmac.new(
        key=META_APP_SECRET.encode("utf-8"),
        msg=corpo,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(assinatura, assinatura_esperada)


@app.get("/webhook")
def verificar_webhook_meta(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge")
):
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Token de verificação inválido", status_code=403)


def enviar_mensagem_meta(numero_cliente: str, texto: str) -> None:
    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"
    dados = json.dumps({
            "messaging_product": "whatsapp",
            "to": numero_cliente,
            "type": "text",
            "text": {"body": texto}
        }).encode("utf-8")
    requisicao = UrlRequest(
        url,
        data=dados,
        headers={
            "Authorization": f"Bearer {META_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    with urlopen(requisicao, timeout=20):
        pass


@app.post("/webhook")
async def receber_webhook_meta(request: Request):
    corpo = await request.body()
    assinatura = request.headers.get("X-Hub-Signature-256", "")
    if not assinatura_meta_valida(corpo, assinatura):
        return PlainTextResponse("Assinatura inválida", status_code=401)

    try:
        dados = json.loads(corpo)
    except json.JSONDecodeError:
        return PlainTextResponse("JSON inválido", status_code=400)

    falha_processamento = False
    for entrada in dados.get("entry", []):
        for alteracao in entrada.get("changes", []):
            for mensagem in alteracao.get("value", {}).get("messages", []):
                if mensagem.get("type") != "text":
                    continue
                identificador_mensagem = mensagem.get("id")
                if identificador_mensagem:
                    with mensagens_processadas_lock:
                        if (
                            identificador_mensagem in mensagens_processadas
                            or identificador_mensagem in mensagens_em_processamento
                        ):
                            continue
                        mensagens_em_processamento.add(identificador_mensagem)

                numero_cliente = mensagem["from"]
                processamento_concluido = False
                try:
                    if verificar_timeout(numero_cliente):
                        await asyncio.to_thread(
                            enviar_mensagem_meta,
                            numero_cliente,
                            "Sua sessão expirou por inatividade. Vamos recomeçar!"
                        )

                    texto = mensagem["text"]["body"].strip()
                    texto_resposta = await asyncio.to_thread(
                        responder,
                        numero_cliente,
                        texto
                    )
                    await asyncio.to_thread(
                        enviar_mensagem_meta,
                        numero_cliente,
                        texto_resposta
                    )
                    processamento_concluido = True
                except (KeyError, TypeError, ValueError):
                    falha_processamento = True
                    logger.exception("Mensagem da Meta em formato inesperado")
                except Exception:
                    falha_processamento = True
                    logger.exception("Falha ao processar mensagem do WhatsApp")
                finally:
                    if identificador_mensagem:
                        with mensagens_processadas_lock:
                            mensagens_em_processamento.discard(identificador_mensagem)
                            if processamento_concluido:
                                if len(mensagens_processadas) >= MAX_MENSAGENS_PROCESSADAS:
                                    mensagens_processadas.clear()
                                mensagens_processadas.add(identificador_mensagem)
    if falha_processamento:
        return PlainTextResponse(
            "Falha temporária ao processar a mensagem",
            status_code=500
        )
    return {"status": "ok"}


if __name__ == "__main__":
    print("=== in9 Equipamentos - Triagem (digite 'sair' para encerrar) ===\n")
    while True:
        entrada_usuario = input("Cliente: ")
        if entrada_usuario.strip().lower() == "sair":
            break
        if entrada_usuario.strip():
            print(f"\nAtendente in9: {responder('cliente_terminal', entrada_usuario)}\n")