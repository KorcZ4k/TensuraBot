"""Regras especiais de monstros, sem monkey-patching.

Este módulo só fornece funções puras/serviços chamados explicitamente pelo
motor efetivo de combate. A classe Luta não é modificada durante import.
"""
import random
from database.python import luta as luta_db

ATRIBUTOS = ("Força","Defesa","Vitalidade","Velocidade","Destreza","Magia","Sorte","Inteligencia")
BOSS_IDS = {"slime-rei","goblin-rei","lobo-alpha","orc-rei","cavaleiro-esqueletico","dragao-adulto","arquidemonio","fenix"}

def criar_monstro_balanceado(tipo: str, nivel: int = 1):
    dados = luta_db.MONSTROS.get(str(tipo))
    if not dados:
        return None
    minimo = int(dados.get("nivel_minimo", 1) or 1)
    maximo = int(dados.get("nivel_maximo", 99) or 99)
    nivel = max(minimo, min(int(nivel), maximo))
    fator = 1 + max(0, nivel - minimo) * 0.75
    base = dados.get("atributos_base", {}) or {}
    atributos = {n:int(float(base.get(n,0) or 0)*fator) for n in ATRIBUTOS}
    vitalidade, magia = atributos["Vitalidade"], atributos["Magia"]
    return {
        "id":str(tipo),"monstro_id":str(tipo),"nome":dados.get("nome",tipo),
        "emoji":dados.get("emoji","👹"),"tipo":"monstro","nivel":nivel,
        "nivel_minimo":minimo,"nivel_maximo":maximo,
        "vida":vitalidade*10,"vida_maxima":vitalidade*10,
        "mana":magia,"mana_maxima":magia,**atributos,
        "defesa":atributos["Força"]+atributos["Defesa"],
        "velocidade":atributos["Velocidade"],
        "dano_base":int(float(dados.get("dano_base",atributos["Força"]) or atributos["Força"])*fator),
        "xp_recompensa":int(float(dados.get("xp_recompensa",0) or 0)*fator),
        "tp_recompensa":int(float(dados.get("tp_recompensa",0) or 0)*fator),
        "hunos_recompensa":int(float(dados.get("hunos_recompensa",10) or 10)*fator),
        "golpes":list(dados.get("golpes",[])),
        "boss":str(tipo) in BOSS_IDS,"boss_id":str(tipo) if str(tipo) in BOSS_IDS else None,
        "boss_estado":{},"efeitos":[],
        "defesa_ativa":False,"esquiva_ativa":False,
        "defesa_magica_ativa":False,"defesa_magica_valor":0,
    }

def estado(monstro):
    return monstro.setdefault("boss_estado", {})

def eh(monstro, *ids):
    return str(monstro.get("boss_id", monstro.get("id",""))) in ids

def vivo(p):
    try: return float(p.get("vida",0) or 0) > 0
    except (TypeError,ValueError): return False

def alvos(combate, atacante):
    equipe=atacante.get("equipe")
    return [p for p in combate.get("participantes",[]) if vivo(p) and p is not atacante and p.get("equipe") != equipe]

def matar_invocados(combate,boss_id):
    if boss_id != "cavaleiro-esqueletico": return
    for p in combate.get("participantes",[]):
        if p.get("invocado") and p.get("equipe")=="inimigos": p["vida"]=0

def ataque_especial(combate, atacante, defensor):
    mid=str(atacante.get("boss_id",atacante.get("id","")))
    st=estado(atacante); turno=int(combate.get("numero_turno",1))
    if mid=="dragao-adulto" and turno%4==0:
        mult=4 if st.get("furia_draconica") else 3
        normal=float(atacante.get("Força",0) or 0)+float(atacante.get("Velocidade",0) or 0)+float(atacante.get("dano_base",0) or 0)
        base=max(0,int(normal*mult-(normal-float(atacante.get("dano_base",0) or 0))))
        st["sopro_elemental"]=True
        return {"nome":"🔥 Sopro Elemental","dano_base":base,"efeito":{"nome":"queimadura","valor":10,"turnos":3},"com_arma":False,"area":True,"area_targets":alvos(combate,atacante),"multiplicador_area":mult}
    return None

def ajustar_ataque(atacante, dados):
    mid=str(atacante.get("boss_id",atacante.get("id","")))
    out=dict(dados)
    if mid=="slime-rei": out.update(nome="🧪 Lodo Corrosivo",efeito={"nome":"corrosao","valor":10,"turnos":3})
    elif mid=="lobo-alpha": out["nome"]="🦷 Mordida Predatória"
    elif mid=="orc-rei": out["nome"]="🩸 Investida Predatória"
    elif mid=="fenix":
        e=dict(out.get("efeito") or {})
        if str(e.get("nome","")).casefold()!="queimadura": out["efeito"]={"nome":"queimadura","valor":10,"turnos":3}
    return out

def regras_dano(dano,resultado,atacante,defensor,ataque,combate):
    st=estado(atacante); mid=str(atacante.get("boss_id",atacante.get("id","")))
    if atacante.get("tipo")!="monstro" or resultado!="atingiu": return dano,resultado
    alvo=str(defensor.get("id"))
    if mid=="goblin-rei":
        if st.get("alvo_id")!=alvo: st.update(alvo_id=alvo,acertos_consecutivos=0)
        st["acertos_consecutivos"]=int(st.get("acertos_consecutivos",0))+1
        if st.pop("critico_pendente",False): dano=int(dano*2)
        if st["acertos_consecutivos"]%3==0: st["acumulos"]=min(3,int(st.get("acumulos",0))+1); st["critico_pendente"]=int(st.get("acumulos",0))>=3
        dano=int(dano*(1+0.15*int(st.get("acumulos",0))))
    elif mid in {"lobo-alpha","orc-rei"}:
        if st.get("alvo_id")!=alvo: st.update(alvo_id=alvo,acertos_consecutivos=0)
        st["acertos_consecutivos"]=int(st.get("acertos_consecutivos",0))+1
        if st.pop("furia_alvo_pendente",False) and st.get("furia_alvo_id")==alvo: dano=int(dano*1.5); st["furia_alvo_id"]=None
        if float(defensor.get("vida",0) or 0)-dano <= float(defensor.get("vida_maxima",1) or 1)*.30: st["furia_alvo_pendente"]=True; st["furia_alvo_id"]=alvo
        if st["acertos_consecutivos"]%3==0: adicionar_efeito(defensor,{"nome":"sangramento_profundo","valor":10,"turnos":3,"ignora_defesa":.5})
    elif mid=="cavaleiro-esqueletico":
        if st.get("alvo_id")!=alvo: st.update(alvo_id=alvo,acertos_consecutivos=0)
        st["acertos_consecutivos"]=int(st.get("acertos_consecutivos",0))+1
        if st["acertos_consecutivos"]%3==0:
            fr=st.setdefault("fraturas",{}); fr[alvo]=int(fr.get(alvo,0))+1
            adicionar_efeito(defensor,{"nome":"fratura","valor":0,"turnos":3})
            if fr[alvo]>=3: adicionar_efeito(defensor,{"nome":"stun","valor":0,"turnos":1}); fr[alvo]=0
    return dano,resultado

def corrosao(dano,defensor):
    e=next((x for x in defensor.get("efeitos",[]) if str(x.get("nome","")).casefold()=="corrosao"),None)
    if not e:return dano
    stacks=min(3,max(1,int(e.get("acumulo",1) or 1)))
    return int(dano*(1-.10*stacks))

def adicionar_efeito(defensor,efeito):
    nome=str(efeito.get("nome",efeito.get("tipo",""))).casefold()
    efeitos=defensor.setdefault("efeitos",[])
    atual=next((e for e in efeitos if str(e.get("nome","")).casefold()==nome),None)
    novo=dict(efeito)
    if atual:
        atual["turnos"]=max(int(atual.get("turnos",1)),int(novo.get("turnos",1)))
        atual["valor"]=max(int(atual.get("valor",0)),int(novo.get("valor",0)))
        if nome=="corrosao": atual["acumulo"]=min(3,int(atual.get("acumulo",1))+int(novo.get("acumulo",1)))
        return atual
    efeitos.append(novo); return novo

def efeito_especial(defensor,efeito):
    if not isinstance(efeito,dict): return None
    nome=str(efeito.get("nome",efeito.get("tipo",""))).casefold()
    if eh(defensor,"dragao-adulto") and nome in {"stun","paralisia","sono","sleep","prisao","prisão"} and random.random()<.75: return None
    if nome in {"corrosao","sangramento_profundo"}: return adicionar_efeito(defensor,efeito)
    return None

def inicio_especial(combate, participante):
    """Aplica apenas efeitos exclusivos de boss; o dano periódico é do motor base."""
    if not vivo(participante):
        if eh(participante, "cavaleiro-esqueletico"):
            matar_invocados(combate, "cavaleiro-esqueletico")
        return False
    if eh(participante, "fenix"):
        cura=max(1,int(float(participante.get("vida_maxima",0))*0.04))
        participante["vida"]=min(float(participante.get("vida_maxima",participante.get("vida",0))),
                                 float(participante.get("vida",0))+cura)
    if not vivo(participante) and eh(participante, "cavaleiro-esqueletico"):
        matar_invocados(combate, "cavaleiro-esqueletico")
    return False

def preparar_proximo_turno(combate):
    turno=int(combate.get("numero_turno",1))
    combate["participantes"]=[p for p in combate.get("participantes",[]) if not (p.get("invocado") and turno>=int(p.get("expira_turno",10**9)))]
    atual=next((p for p in combate.get("participantes",[]) if p.get("id")==combate.get("_turno_participante_id")),None)
    for p in combate.get("participantes",[]):
        if eh(p,"dragao-adulto") and not estado(p).get("furia_draconica") and vivo(p) and float(p.get("vida",0))<=float(p.get("vida_maxima",1))*.25:
            estado(p)["furia_draconica"]=True; p["Velocidade"]=float(p.get("Velocidade",0))*1.2; p["velocidade"]=p["Velocidade"]
    if atual in combate.get("participantes",[]): combate["turno"]=combate["participantes"].index(atual)
