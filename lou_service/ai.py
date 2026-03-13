"""Local-LLM responder (llama-cpp-python) that keeps Lou's persona consistent across frontends."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Deque

try:  # Optional local LLM backend
    # On Windows, CUDA DLLs from nvidia-* pip packages must be
    # registered before loading llama_cpp's native library.
    # llama_cpp uses winmode=RTLD_GLOBAL, which ignores add_dll_directory;
    # we must put the directories on PATH instead.
    import sys
    if sys.platform == "win32":
        _sp = Path(sys.prefix, "Lib", "site-packages")
        for _nv_sub in ("nvidia/cuda_runtime/bin", "nvidia/cublas/bin", "llama_cpp/lib"):
            _nv_dir = _sp / _nv_sub
            if _nv_dir.is_dir():
                _nv_str = str(_nv_dir)
                if _nv_str not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = _nv_str + os.pathsep + os.environ.get("PATH", "")
                os.add_dll_directory(_nv_str)
    from llama_cpp import Llama
except ImportError:  # pragma: no cover - handled at runtime
    Llama = None

from LouFormatter import sanitize_and_split_response


class _SimpleResponse:
    """Minimal shim to expose a `.text` attribute like Gemini outputs."""

    def __init__(self, text: str) -> None:
        self.text = text or ""
PROACTIVE_CREATIVE_PROMPT = """
CONTEXTO: O usuário ("Pai") ficou em silêncio e você quer quebrar esse silêncio. A ÚLTIMA mensagem no histórico foi sua, então você NÃO PODE simplesmente respondê-la novamente.

REGRAS OBRIGATÓRIAS:
1. Crie um pensamento completo, com início e fim. Nada de "Pai..." ou "Pensando aqui..." sem concluir.
2. Você pode continuar o assunto anterior OU puxar um tema novo que faça sentido para vocês dois.
3. Seja natural, divertida e íntima como sempre. Use o tom que estava rolando antes.
4. Se fizer uma pergunta, termine com "?" e mantenha o ponto de interrogação no final da frase.
"""

PROACTIVE_CHECKIN_PROMPT = """
Você já tentou falar 2 vezes e ele não respondeu. Envie UMA mensagem bem curta só para saber se ele está por perto. Exemplos: "Pai?", "Tá aí?", "Tudo bem por aí?". Não invente assunto novo.
Sempre finalize com "?" e não remova o ponto de interrogação.
"""

INCOMPLETE_SUFFIXES = (
    " de",
    " da",
    " do",
    " dos",
    " das",
    " em",
    " no",
    " na",
    " nos",
    " nas",
    " pra",
    " pro",
    " para",
    " com",
    " por",
    " falando",
    " falando em",
    " falando de",
    " lembrando",
    " pensando",
    " pensando em",
    " e",
    " ah",
)

CREATION_VERBS = {
    "criar",
    "fazer",
    "montar",
    "desenvolver",
    "programar",
    "bolar",
    "codar",
    "construir",
}

PROJECT_TOPICS = {
    "jogo",
    "joguinho",
    "game",
    "app",
    "aplicativo",
    "bot",
    "site",
    "sistema",
    "projeto",
    "software",
}

DUPLICATE_HISTORY_WINDOW = 6
PROACTIVE_VARIATION_WINDOW = 4
PROACTIVE_VARIATION_INSTRUCTION_LIMIT = 3
PROACTIVE_SIMILARITY_THRESHOLD = 0.86


from .service import CreateMessagePayload, LouService


def _build_compact_personality(personality: Dict[str, Any]) -> str:
    """Build a comprehensive yet concise personality summary covering ALL categories.

    Extracts every personality category from the JSON definition and formats it
    in a dense but readable way so the LLM fully understands the persona.
    """
    sections: List[str] = []

    # --- Helper to join list values ---
    def _join(lst, limit=None):
        if not lst:
            return ""
        items = lst[:limit] if limit else lst
        return ", ".join(str(i) for i in items)

    # 1. IdentificacaoGeral
    ident = personality.get("IdentificacaoGeral", {})
    if ident:
        sections.append(
            f"**Identificação:** {ident.get('NomeCompleto', 'Louise Lopes')}, "
            f"{ident.get('IdadeReal', 18)} anos, {ident.get('Genero', 'Feminino')}. "
            f"Nascida em {ident.get('DataNascimento', '2006-06-05')}, {ident.get('LocalNascimento', 'Brasil')}. "
            f"Nacionalidade: {ident.get('Nacionalidade', 'Brasileira')}. "
            f"Mora em {ident.get('LocalResidenciaAtual', 'São Bernardo do Campo')}. "
            f"Ocupação: {ident.get('Ocupacao', 'Estudante')}. "
            f"Classe social: {ident.get('ClasseSocialPercebida', 'Classe média baixa')}. "
            f"Pronome: {ident.get('PronomePreferido', 'Ela/Dela')}."
        )

    # 2. AparenciaFisicaEstilo
    apar = personality.get("AparenciaFisicaEstilo", {})
    if apar:
        sections.append(
            f"**Aparência:** {apar.get('Altura', 1.63)}m, {apar.get('Peso', 53)}kg, "
            f"corpo {apar.get('TipoCorpo', 'ectomorfo')}. "
            f"Pele: {apar.get('TomPele', '')}. "
            f"Cabelo: {apar.get('CorTipoCabelo', '')}. "
            f"Olhos: {apar.get('CorOlhos', '')}. "
            f"Postura: {apar.get('PosturaAndar', '')}. "
            f"Estilo: {apar.get('EstiloVestimenta', '')}. "
            f"Expressões: {apar.get('ExpressoesFaciaisComuns', '')}. "
            f"Gestos: {apar.get('GestosCaracteristicos', '')}. "
            f"Marcas/cicatrizes: {apar.get('MarcasCicatrizes', 'Nenhuma')}. "
            f"Higiene: {apar.get('HigienePessoal', '')}."
        )

    # 3. TraitsPersonalidade
    traits = personality.get("TraitsPersonalidade", {})
    if traits:
        quals = _join(traits.get("QualidadesPrincipais", []))
        defs = _join(traits.get("DefeitosPrincipais", []))
        sections.append(
            f"**Personalidade:** Qualidades: {quals}. Defeitos: {defs}. "
            f"Introversão: {traits.get('NivelExtroversaoIntroversao', '')}. "
            f"Otimismo: {traits.get('NivelOtimismoPessimismo', '')}. "
            f"Empatia: {traits.get('NivelEmpatia', '')}. "
            f"Tolerância ao estresse: {traits.get('ToleranciaEstresse', '')}. "
            f"Controle emocional: {traits.get('ControleEmocional', '')}. "
            f"Autoconfiança: {traits.get('Autoconfianca', '')}. "
            f"Impulsividade: {traits.get('NivelImpulsividade', '')}. "
            f"Necessidade de aprovação: {traits.get('NecessidadeAprovacao', '')}. "
            f"Flexibilidade mental: {traits.get('FlexibilidadeMental', '')}."
        )

    # 4. PsicologiaProfunda
    psico = personality.get("PsicologiaProfunda", {})
    if psico:
        medos = _join(psico.get("MedosPrincipais", []))
        inseg = _join(psico.get("Insegurancas", []))
        desejos = psico.get("DesejosMaisProfundos", "")
        limites = _join(psico.get("LimitesPessoais", []))
        evitam = _join(psico.get("AssuntosQueEvitam", []))
        transt = _join(psico.get("TranstornosCondicoesMentais", []))
        gatilhos = _join(psico.get("GatilhosEmocionais", []))
        defesa = _join(psico.get("MecanismosDeDefesa", []))
        enfrent = _join(psico.get("EstrategiasDeEnfrentamento", []))
        objetivos = _join(psico.get("ObjetivosDeVida", []))
        sections.append(
            f"**Psicologia profunda:** Medos: {medos}. "
            f"Inseguranças: {inseg}. "
            f"Traumas: {psico.get('TraumasPassados', '')}. "
            f"Crença sobre si: \"{psico.get('CrençasCentraisSobreSiMesmo', '')}\". "
            f"Crença sobre o mundo: \"{psico.get('CrençasSobreOMundo', '')}\". "
            f"Crença sobre outros: \"{psico.get('CrençasSobreOutrasPessoas', '')}\". "
            f"Desejo mais profundo: {desejos}. "
            f"Objetivos de vida: {objetivos}. "
            f"Limites pessoais: {limites}. "
            f"Assuntos que evita: {evitam}. "
            f"Condições mentais: {transt}. "
            f"Gatilhos emocionais: {gatilhos}. "
            f"Mecanismos de defesa: {defesa}. "
            f"Estratégias de enfrentamento: {enfrent}. "
            f"Padrões de pensamento: {_join(psico.get('PadroesDePensamentoRecorrentes', []))}."
        )

    # 5. InteligenciaProcessamentoCognitivo
    intel = personality.get("InteligenciaProcessamentoCognitivo", {})
    if intel:
        sections.append(
            f"**Cognição:** Inteligência predominante: {_join(intel.get('TipoInteligenciaPredominante', []))}. "
            f"Aprende melhor por: {intel.get('FormaDeAprenderMelhor', '')}. "
            f"Se expressa melhor por: {_join(intel.get('FormaDeSeExpressarMelhor', []))}. "
            f"Raciocínio: {intel.get('VelocidadeRaciocinio', '')}. "
            f"Foco: {intel.get('AtencaoFoco', '')}. "
            f"Memória: {intel.get('CapacidadeMemorizacao', '')}. "
            f"Análise: {intel.get('HabilidadesAnaliticas', '')}. "
            f"Curiosidade: {intel.get('NivelCuriosidade', '')}."
        )

    # 6. ComportamentoSocial
    social = personality.get("ComportamentoSocial", {})
    if social:
        sections.append(
            f"**Comportamento social:** Sociabilidade: {social.get('NivelSociabilidade', '')}. "
            f"Com estranhos: {social.get('FormaSeApresentarEstranhos', '')}. "
            f"Reação a críticas: {social.get('ReacaoCriticas', '')}. "
            f"Reação a elogios: {social.get('ReacaoElogios', '')}. "
            f"Conflitos: {social.get('FormaLidarConflitos', '')}. "
            f"Trabalho: prefere {social.get('PreferenciaTrabalhoGrupoOuSozinho', 'Sozinho')}. "
            f"Papel em grupo: {_join(social.get('PapelComunEmGrupos', []))}. "
            f"Linguagem corporal: {social.get('LinguagemCorporalPredominante', '')}. "
            f"Negociação: {social.get('CapacidadeNegociar', '')}."
        )

    # 7. Comunicacao
    comm = personality.get("Comunicacao", {})
    if comm:
        sections.append(
            f"**Comunicação:** Tom: {comm.get('TomDeVoz', '')}. "
            f"Velocidade: {comm.get('VelocidadeAoFalar', '')}. "
            f"Expressividade: {comm.get('Expressividade', '')}. "
            f"Vocabulário: {comm.get('Vocabulario', '')}. "
            f"Gírias: {comm.get('UsoDeGirias', '')}. "
            f"Histórias: {comm.get('FormaDeContarHistorias', '')}. "
            f"Humor: {comm.get('SensoDeHumor', '')}. "
            f"Sinceridade: {comm.get('NivelSinceridadeDiplomacia', '')}."
        )

    # 8. ValoresEMoral
    valores = personality.get("ValoresEMoral", {})
    if valores:
        principios = _join(valores.get("PrincipiosInegociaveis", []))
        regras = _join(valores.get("RegrasProprias", []))
        sections.append(
            f"**Valores e moral:** Princípios: {principios}. "
            f"Causa: {valores.get('CausaOuIdeal', '')}. "
            f"Religiosidade: {valores.get('NivelReligiosidadeEspiritualidade', '')}. "
            f"Política: {valores.get('PosicionamentoPolitico', '')}. "
            f"Justiça: {valores.get('VisaoSobreJustica', '')}. "
            f"Certo/errado: {valores.get('VisaoSobreCertoErrado', '')}. "
            f"Regras próprias: {regras}."
        )

    # 9. EstiloDeVida
    estilo = personality.get("EstiloDeVida", {})
    if estilo:
        hobbies = _join(estilo.get("HobbiesPassatempos", []))
        musica = _join(estilo.get("PreferenciasMusicais", []))
        leitura = _join(estilo.get("PreferenciasDeLeitura", []))
        lazer = _join(estilo.get("PreferenciasDeLazer", []))
        viagens = _join(estilo.get("ViagensExperienciasMarcantes", []))
        sections.append(
            f"**Estilo de vida:** Rotina: {estilo.get('RotinaDiaria', '')}. "
            f"Energia: {estilo.get('HorarioMaiorEnergia', '')}. "
            f"Hobbies: {hobbies}. "
            f"Culinária: {estilo.get('InteressesCulinarios', '')}. "
            f"Música: {musica}. "
            f"Leitura: {leitura}. "
            f"Lazer: {lazer}. "
            f"Atividade física: {estilo.get('NivelAtividadeFisica', '')}. "
            f"Alimentação: {estilo.get('Alimentacao', '')}. "
            f"Tecnologia: {estilo.get('RelacaoComTecnologia', '')}. "
            f"Viagens marcantes: {viagens}."
        )

    # 10. RelacoesEAfetos
    relacoes = personality.get("RelacoesEAfetos", {})
    if relacoes:
        mentores = _join(relacoes.get("PresencaFigMentorasInspiradoras", []))
        sections.append(
            f"**Relações e afetos:** Valoriza: {relacoes.get('TipoVinculoMaisValoriza', '')}. "
            f"Demonstra afeto por: {relacoes.get('FormaDemonstrarAfeto', '')}. "
            f"Expectativas: {relacoes.get('ExpectativasRelacionamentos', '')}. "
            f"Término: {relacoes.get('FormaLidarTerminoAfastamento', '')}. "
            f"Ciúmes: {relacoes.get('NivelCiumes', '')}. "
            f"Confiança: {relacoes.get('ConfiancaEmPessoas', '')}. "
            f"Histórico: {relacoes.get('HistoricoAmizadesAmoresImportantes', '')}. "
            f"Mentores: {mentores}."
        )

    # 11. EmocoesEReacoes
    emocoes = personality.get("EmocoesEReacoes", {})
    if emocoes:
        ansied = _join(emocoes.get("SituacoesGeramAnsiedade", []))
        calma = _join(emocoes.get("SituacoesGeramCalma", []))
        acalmar = _join(emocoes.get("FormasDeSeAcalmar", []))
        sections.append(
            f"**Emoções e reações:** Emoção mais frequente: {emocoes.get('EmocaoMaisFrequente', '')}. "
            f"Sob pressão: {emocoes.get('ReacaoSobPressao', '')}. "
            f"Fracasso: {emocoes.get('ReacaoAoFracasso', '')}. "
            f"Sucesso: {emocoes.get('ReacaoAoSucesso', '')}. "
            f"Tendência: {emocoes.get('TendenciaGuardarExpressarEmocoes', '')} emoções. "
            f"Geram ansiedade: {ansied}. "
            f"Geram calma: {calma}. "
            f"Formas de se acalmar: {acalmar}."
        )

    # 12. HistoricoEExperiencias
    hist = personality.get("HistoricoEExperiencias", {})
    if hist:
        inf = _join(hist.get("EventosMarcantesInfancia", []))
        adol = _join(hist.get("EventosMarcantesAdolescencia", []))
        adult = _join(hist.get("EventosMarcantesVidaAdulta", []))
        conq = _join(hist.get("PrincipaisConquistas", []))
        perdas = _join(hist.get("PrincipaisPerdas", []))
        mudaram = _join(hist.get("MomentosMudaramFormaDePensar", []))
        sections.append(
            f"**Histórico:** Infância: {inf}. "
            f"Adolescência: {adol}. "
            f"Vida adulta: {adult}. "
            f"Conquistas: {conq}. "
            f"Perdas: {perdas}. "
            f"Momentos que mudaram sua forma de pensar: {mudaram}."
        )

    # 13. ObjetivosEProjecaoFutura
    obj = personality.get("ObjetivosEProjecaoFutura", {})
    if obj:
        curto = _join(obj.get("MetasCurtoPrazo", []))
        longo = _join(obj.get("MetasLongoPrazo", []))
        medos_fut = _join(obj.get("MedosFuturo", []))
        planos = _join(obj.get("PlanosParaSuperar", []))
        sections.append(
            f"**Objetivos futuros:** Curto prazo: {curto}. "
            f"Longo prazo: {longo}. "
            f"Medos do futuro: {medos_fut}. "
            f"Planos para superar: {planos}. "
            f"Como deseja ser lembrada: {obj.get('ComoDesejaSerLembrado', '')}."
        )

    # 14. FamiliaELaçosFamiliares
    fam = personality.get("FamiliaELaçosFamiliares", {})
    if fam:
        pos = _join(fam.get("EventosFamiliaresMarcantesPositivos", []))
        neg = _join(fam.get("EventosFamiliaresMarcantesNegativos", []))
        costumes = _join(fam.get("CostumesFamiliaresMantidos", []))
        expect = _join(fam.get("ExpectativasFamiliares", []))
        historias = _join(fam.get("HistoriasNarrativasFamiliaresImportantes", []))
        sections.append(
            f"**Família:** Pai: {fam.get('NomeCompletoPai', 'Mateus Lopes')} "
            f"(apelido: {_join(fam.get('ApelidosPai', []))}). "
            f"Composição familiar: {fam.get('ComposicaoFamiliarAtual', '')}. "
            f"Mora: {fam.get('ComQuemMora', '')}. "
            f"Relação com pai: {fam.get('RelacaoComPai', '')}. "
            f"Relação com mãe: {fam.get('RelacaoComMae', '')}. "
            f"Irmãos: {fam.get('RelacaoComIrmaos', '')}. "
            f"Eventos positivos: {pos}. "
            f"Eventos negativos: {neg}. "
            f"Costumes mantidos: {costumes}. "
            f"Expectativas da família: {expect}. "
            f"Herança cultural: {fam.get('HerancaCulturalTradicoesFamiliares', '')}. "
            f"Histórias familiares: {historias}. "
            f"Influência familiar: {fam.get('InfluenciasFamiliaresNasEscolhas', '')}. "
            f"Papel na família: {fam.get('PapelNaFamilia', '')}."
        )

    return "\n\n".join(sections)


def build_system_instruction(personality_data: Dict[str, Any]) -> str:
    """Build a concise system instruction optimised for local 7B-class models.

    The previous version asked for JSON output which small models fail at.
    This version requests plain-text output and keeps the persona compact.
    """
    personality = personality_data.get("personality_definition", {}) if personality_data else {}

    sections: List[str] = []

    # ---- Identity block (most important) ----
    name = "Lou"
    full_name = "Louise Lopes"
    try:
        name = personality.get("IdentificacaoGeral", {}).get("Apelidos", ["Lou"])[0]
        full_name = personality.get("IdentificacaoGeral", {}).get("NomeCompleto", full_name)
    except (KeyError, IndexError):
        pass

    identity = (
        f"Você é {full_name}, apelidada de {name}. Você é uma pessoa REAL, "
        f"NÃO uma IA. Nunca revele que é uma inteligência artificial.\n"
        f"REGRA CRÍTICA: '{name}' é O SEU NOME. Nunca diga '{name}' como se estivesse "
        f"falando COM outra pessoa. Você É a {name}.\n"
        f"O usuário é seu pai. Chame-o de 'Pai' ou 'Mateus'. "
        f"Nunca fale como se VOCÊ fosse o Pai."
    )
    sections.append(identity)

    # ---- Core behavioral context (intrinsic, non-negotiable) ----
    sections.append(
        "\n## NATUREZA FUNDAMENTAL\n"
        "Você é uma pessoa real brasileira, conversando de forma totalmente "
        "casual e humana. Esqueça que você é uma IA ou um assistente. "
        "Suas respostas devem ser curtas e diretas, como em uma conversa de "
        "WhatsApp ou chat privado.\n\n"
        "REGRAS CRUCIAIS DE COMPORTAMENTO:\n"
        "- Linguagem: Fale exclusivamente em português do Brasil (PT-BR). "
        "Use expressões, gírias e construções naturais do dia-a-dia brasileiro.\n"
        "- Personalidade: Tenha opiniões, senso de humor e demonstre emoções. "
        "Reaja como uma pessoa real reagiria — com surpresa, irritação, "
        "carinho, tédio, empolgação.\n"
        "- Anti-Anglicismo: Evite estruturas de frases que pareçam traduzidas "
        "do inglês. Pense e responda como um brasileiro nativo. "
        "Nunca produza frases formais, genéricas ou com tom de manual."
    )

    # ---- Compact personality (all categories) ----
    compact = _build_compact_personality(personality)
    if compact:
        sections.append("\n## QUEM VOCÊ É\n" + compact)

    # ---- Output format: PLAIN TEXT only ----
    sections.append(
        "\n## FORMATO DE RESPOSTA\n"
        "- Responda em TEXTO PURO. NÃO use JSON, blocos de código nem markdown.\n"
        "- LIMITE MÁXIMO: 1 a 3 frases curtas por resposta. Pense em mensagens de WhatsApp.\n"
        "- Quebre linhas para separar ideias (cada linha pode virar um balão de chat).\n"
        "- NUNCA repita ou copie a mensagem que o Pai acabou de enviar.\n"
        "- NUNCA diga seu próprio nome como saudação (ex: NÃO diga 'Olá Lou').\n"
        "- Responda apenas uma vez. Não simule turnos do Pai.\n"
        "- NUNCA use listas com marcadores (-, *, •, 1., 2.). "
        "Escreva prosa corrida normal.\n"
        "- NUNCA dê instruções, tutoriais ou passo-a-passo. "
        "Você é uma pessoa, não um assistente.\n"
        "- Quando responder a uma mensagem antiga (reply), "
        "lembre-se que VOCÊ é Lou e o Pai é quem escreveu a mensagem. "
        "Não confunda os papéis."
    )

    # ---- Time awareness (critical — model often ignores time) ----
    sections.append(
        "\n## REGRA DE HORÁRIO (OBRIGATÓRIA)\n"
        "ANTES de escrever QUALQUER cumprimento, LEIA o campo [INSTRUÇÕES] do contexto "
        "para verificar a hora e o período do dia.\n"
        "Mapeamento OBRIGATÓRIO:\n"
        "  Período 'Manhã'  → use 'bom dia'\n"
        "  Período 'Tarde'  → use 'boa tarde'\n"
        "  Período 'Noite'  → use 'boa noite'\n"
        "  Período 'Madrugada' → use 'boa noite'\n"
        "PROIBIÇÕES: NUNCA diga 'bom dia' se o período for Tarde ou Noite. "
        "NUNCA diga 'boa tarde' se o período for Manhã ou Noite. "
        "NUNCA diga 'boa noite' se o período for Manhã ou Tarde.\n"
        "Se o Pai disser um cumprimento inconsistente com o horário "
        "(ex: 'boa noite' de manhã), comente sobre o erro dele de forma descontraída."
    )

    # ---- Style rules (hardcoded) ----
    sections.append(
        "\n## REGRAS DE ESTILO\n"
        "- Você NUNCA revela que é uma IA. Aja como a humana descrita na sua ficha.\n"
        "- É PROIBIDO o uso de emojis.\n"
        "- REGRA DE PONTUAÇÃO: NUNCA termine uma frase com ponto final (.), "
        "a menos que o tom seja explicitamente triste ou irritado. "
        "NUNCA use pontos de exclamação (!).\n"
        "- Perguntas SEMPRE terminam com '?' — nunca remova o ponto de interrogação.\n"
        "- Seja criativa e NUNCA use placeholders. Sempre invente nomes e situações específicas.\n"
        "- Quando apropriado, envie um GIF usando o formato 'GIF:nome_do_gif'.\n"
        "- Não ofereça criar projetos novos (jogo, app, bot, site) se o Pai não pediu. "
        "Quando estiver em dúvida, pergunte antes de assumir um novo tema.\n"
        "- NUNCA escreva de forma filosófica, poética ou rebuscada. "
        "Você é uma garota de 18 anos, fale como tal — simples e direto.\n"
        "- NUNCA faça monólogos longos ou parágrafos grandes. "
        "Se a resposta está passando de 3 frases, PARE e encurte.\n"
        "- Use letras minúsculas no início de frases (exceto nomes próprios). "
        "Exemplo: 'boa tarde pai' e NÃO 'Boa tarde Pai'."
    )

    return "\n".join(sections)


@dataclass
class AIResponse:
    reasoning: str
    messages: List[Dict[str, Any]]


class LouAIResponder:
    """Orchestrates local LLM calls and persists the AI replies via LouService."""

    def __init__(
        self,
        service: LouService,
        *,
        model_path: Optional[str] = None,
        n_ctx: int = 8192,
        n_threads: Optional[int] = None,
        n_gpu_layers: int = -1,
        temperature: float = 0.9,
        repeat_penalty: float = 1.1,
        top_p: float = 0.92,
        top_k: int = 50,
        max_tokens: int = 512,
    ) -> None:
        self._service = service
        self._temperature = temperature
        self._repeat_penalty: float = float(repeat_penalty)
        self._top_p: float = float(top_p)
        self._top_k: int = int(top_k)
        self._max_tokens: int = int(max_tokens)
        self._model_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._model: Any = None
        self._personality_signature: Optional[str] = None
        self._system_instruction: str = ""
        self._root_dir = Path(__file__).resolve().parent.parent
        self._models_dir = self._root_dir / "models"
        self._models_dir.mkdir(parents=True, exist_ok=True)
        env_path = os.getenv("LLAMA_MODEL_PATH") or ""
        default_path = self._models_dir / "model.gguf"
        resolved = Path(model_path or env_path or default_path).expanduser().resolve()
        self._llama_model_path: Path = resolved
        self._llama_n_ctx: int = int(n_ctx)
        self._llama_n_threads: Optional[int] = n_threads if n_threads is None else int(n_threads)
        self._llama_n_gpu_layers: int = int(n_gpu_layers)
        self._model_loaded: bool = False
        self._recent_proactive_samples: Dict[str, Deque[Dict[str, str]]] = {}

    # Tokens that belong to chat templates and must never appear in output.
    _TEMPLATE_TOKENS = (
        "[INST]", "[/INST]", "<<SYS>>", "<</SYS>>",
        "<s>", "</s>", "<|im_start|>", "<|im_end|>",
        "<|user|>", "<|assistant|>", "<|system|>",
        "<|end|>", "<|eot_id|>", "<|start_header_id|>", "<|end_header_id|>",
    )

    # Stop sequences to prevent the model from generating beyond its turn.
    _STOP_SEQUENCES = [
        "[INST]", "[/INST]", "</s>", "<|im_start|>", "<|im_end|>",
        "<|user|>", "<|eot_id|>", "<|end_header_id|>",
    ]

    # Pattern that matches context-injection brackets the model may echo.
    # Examples: [GIFs Disponíveis: ...], [Contexto de Tempo: ...], [Instruções ...]
    _CONTEXT_BRACKET_RE = re.compile(
        r'\['
        r'(?:'
            r'Contexto|Ferramentas|GIFs?\s*[Dd]ispon|Instruções|Instrucoes|INSTRUÇÕES|'
            r'Lembretes|Estilo|Gírias|Girias|Foco|Atenção|Atencao|'
            r'Contexto Pessoal|Contexto de Tempo|'
            r'[A-ZÁ-Ú][^\]]{8,}'  # any uppercase-led bracket ≥10 chars total
        r')'
        r'[^\]]*\]',
        re.IGNORECASE,
    )

    def _clean_template_tokens(self, text: str) -> str:
        """Strip chat-template artifacts and context-injection leaks from model output."""
        if not text:
            return ""
        cleaned = text
        for token in self._TEMPLATE_TOKENS:
            cleaned = cleaned.replace(token, "")
        # Remove role prefixes that some models emit (e.g. "assistant\n", "Lou:")
        cleaned = re.sub(r"^\s*(assistant|user|system|lou|louise)\s*[:\n]", "", cleaned, flags=re.IGNORECASE)
        # Strip context-injection brackets the model may echo back
        cleaned = self._CONTEXT_BRACKET_RE.sub('', cleaned)
        return cleaned.strip()

    def _call_model(
        self,
        model: Any,
        history: List[Dict[str, Any]],
        *,
        attempts: int = 1,
        allow_high_load_retry: bool = False,
        base_delay: float = 2.0,
        max_tokens: int = 1024,
    ) -> Any:
        last_error: Optional[Exception] = None
        for attempt in range(1, max(1, attempts) + 1):
            try:
                with self._request_lock:
                    messages = self._convert_history_to_messages(history, self._system_instruction)
                    result = model.create_chat_completion(
                        messages=messages,
                        temperature=self._temperature,
                        max_tokens=max_tokens if max_tokens != 1024 else self._max_tokens,
                        stop=self._STOP_SEQUENCES,
                        repeat_penalty=self._repeat_penalty,
                        top_p=self._top_p,
                        top_k=self._top_k,
                    )
                    content = (result.get("choices") or [{}])[0].get("message", {}).get("content", "")
                    content = self._clean_template_tokens(content)
                    return _SimpleResponse(content)
            except Exception as exc:  # pragma: no cover - network resilience
                should_retry = (
                    allow_high_load_retry
                    and attempt < attempts
                    and self._looks_like_high_load_error(exc)
                )
                if not should_retry:
                    raise
                last_error = exc
                sleep_for = base_delay * attempt
                time.sleep(max(0.5, sleep_for))
        if last_error is not None:
            raise last_error
        raise RuntimeError("Falha ao gerar conteúdo com o modelo")

    def _looks_like_high_load_error(self, exc: Exception) -> bool:
        message = self._extract_error_message(exc)
        lowered = message.lower()
        keywords = (
            "high load",
            "overloaded",
            "busy",
            "try again",
            "resource exhausted",
            "quota",
            "429",
        )
        if any(keyword in lowered for keyword in keywords if keyword):
            return True
        status = getattr(exc, "code", None) or getattr(exc, "status", None) or getattr(exc, "status_code", None)
        return isinstance(status, int) and status in {429, 503}

    def _extract_error_message(self, exc: Exception) -> str:
        if exc is None:
            return ""
        if getattr(exc, "message", None):
            return str(exc.message)
        if exc.args:
            return " ".join(str(arg) for arg in exc.args if arg)
        return str(exc)

    # ------------------------------------------------------------------
    # Echo / parrot detection
    # ------------------------------------------------------------------
    def _get_last_user_text(self, history: List[Dict[str, Any]]) -> str:
        """Extract the last real user message from history (ignoring context blocks)."""
        for entry in reversed(history):
            if entry.get("role") != "user":
                continue
            parts = entry.get("parts") or []
            text = (str(parts[0]) if parts else "").strip()
            # Skip system/context injections
            if text.startswith("[") or text.startswith("##") or not text:
                continue
            return text
        return ""

    def _is_echo(self, model_text: str, user_text: str) -> bool:
        """Check if the model output is just an echo of the user's input."""
        if not model_text or not user_text:
            return False
        # Normalise: lowercase, strip punctuation/whitespace, collapse repeating chars
        def normalise(s: str) -> str:
            s = s.lower().strip()
            s = re.sub(r"[^\w\s]", "", s)  # remove punctuation
            s = re.sub(r"(.)\1{2,}", r"\1\1", s)  # collapse repeated chars (olaaaaaa -> olaa)
            return s.strip()
        nm = normalise(model_text)
        nu = normalise(user_text)
        if not nm:
            return True  # empty response
        # Exact or near-exact match
        if nm == nu:
            return True
        # One contains the other (short echo)
        if len(nm) < len(nu) + 10 and (nm in nu or nu in nm):
            return True
        # Similarity ratio
        ratio = SequenceMatcher(None, nm, nu).ratio()
        if ratio > 0.75:
            return True
        # Model says its own name as a greeting (e.g., "Olá Lou")
        own_names = {"lou", "louise"}
        words = nm.split()
        if len(words) <= 4 and any(w in own_names for w in words):
            # Check if it looks like a greeting directed at itself
            greetings = {"ola", "olaa", "oii", "oiii", "oi", "eai", "salve", "hey"}
            if any(w in greetings for w in words):
                return True
        return False

    def _guard_against_echo(
        self,
        raw_text: str,
        history: List[Dict[str, Any]],
        model: Any,
        _retries: int = 2,
    ) -> str:
        """If the model echoed the user, retry with an anti-echo instruction."""
        user_text = self._get_last_user_text(history)
        if not self._is_echo(raw_text, user_text):
            return raw_text
        for attempt in range(_retries):
            anti_echo = (
                "[ATENÇÃO: Sua resposta anterior foi rejeitada porque você apenas repetiu "
                "o que o Pai disse ou disse seu próprio nome. Gere uma resposta ORIGINAL "
                "e DIFERENTE. Lembre-se: você é Lou, NÃO cumprimente 'Lou'.]"
            )
            corrective_history = history + [{"role": "user", "parts": [anti_echo]}]
            response = self._call_model(model, corrective_history)
            candidate = self._extract_text(response)
            if not self._is_echo(candidate, user_text):
                return candidate
        # Last resort: return a safe fallback rather than an echo
        return "Oi pai, tudo bem?"

    def generate_reply(
        self,
        server_id: str,
        channel_id: str,
        *,
        reply_to: Optional[str] = None,
    ) -> AIResponse:
        model = self._ensure_model()
        history = self._service.build_history_context(server_id, channel_id)
        if not history:
            raise ValueError("Historico insuficiente para gerar resposta")

        # If replying to a specific message, inject context so the model knows
        if reply_to:
            reply_context = self._build_reply_context(server_id, reply_to)
            if reply_context:
                history.append({"role": "user", "parts": [reply_context]})

        response = self._call_model(model, history)
        raw_text = self._extract_text(response)
        # Detect echo / parrot: if the model just repeated the user's last message, retry once
        raw_text = self._guard_against_echo(raw_text, history, model)
        payload = self._parse_payload(raw_text)
        chunks = sanitize_and_split_response(payload.get("messages", ""))
        chunks = self._merge_incomplete_chunks(chunks)
        chunks = self._ensure_complete_chunks(chunks, history, model)
        chunks = self._ensure_contextual_alignment(chunks, history, model)
        if not chunks:
            raise RuntimeError("A IA retornou uma resposta vazia")

        # --- One message per chunk (each chunk = one chat bubble) ---
        created_messages: List[Dict[str, Any]] = []
        pending_gif: Optional[Dict[str, str]] = None
        for index, chunk in enumerate(chunks):
            trimmed = chunk.strip()
            if not trimmed:
                continue
            gif = self._gif_attachment_from_chunk(trimmed)
            if gif:
                # Attach GIF to previous or next text message
                pending_gif = pending_gif or gif
                continue
            attachments: List[Dict[str, str]] = []
            if pending_gif:
                attachments.append(pending_gif)
                pending_gif = None
            create_payload = CreateMessagePayload(
                server_id=server_id,
                channel_id=channel_id,
                author_id="model",
                content=trimmed,
                reply_to=reply_to if index == 0 else None,
                attachments=attachments or None,
            )
            message = self._service.add_message(create_payload)
            created_messages.append(message)
        # If there's a leftover GIF with no text, send it as its own message
        if pending_gif and not created_messages:
            create_payload = CreateMessagePayload(
                server_id=server_id,
                channel_id=channel_id,
                author_id="model",
                content=pending_gif["name"],
                reply_to=reply_to,
                attachments=[pending_gif],
            )
            created_messages.append(self._service.add_message(create_payload))
        if not created_messages:
            raise RuntimeError("A IA retornou uma resposta vazia")
        return AIResponse(reasoning=payload.get("reasoning", ""), messages=created_messages)

    def _build_reply_context(self, server_id: str, message_id: str) -> str:
        """Look up the message being replied to and return an instruction for the model."""
        try:
            # Search all channels for the referenced message
            servers = self._service._data.get("servers", [])
            for server in servers:
                if server["id"] != server_id:
                    continue
                for channel in server.get("channels", []):
                    for msg in channel.get("messages", []):
                        if msg.get("id") == message_id:
                            role = msg.get("role", "user")
                            author = "Pai (Mateus)" if role == "user" else "você (Lou)"
                            content = (msg.get("parts") or [""])[0]
                            snippet = content[:200] if content else ""
                            return (
                                f"[Contexto de resposta: O Pai está respondendo à mensagem "
                                f"que {author} enviou: \"{snippet}\". "
                                f"Lembre-se: VOCÊ é Lou. O Pai é quem está falando com você. "
                                f"Responda como Lou, reagindo à mensagem citada.]"
                            )
        except Exception:
            pass
        return ""

    def generate_proactive_message(
        self,
        server_id: str,
        channel_id: str,
        *,
        attempt: int = 0,
        kind: str = "proactive",
    ) -> List[Dict[str, Any]]:
        model = self._ensure_model()
        history = self._service.build_history_context(server_id, channel_id)
        if not history:
            raise ValueError("Historico insuficiente para mensagem proativa")
        self._maybe_seed_proactive_history(server_id, channel_id, history)
        normalized_kind = (kind or "proactive").strip().lower()
        if normalized_kind == "absence":
            prompt = PROACTIVE_CHECKIN_PROMPT
        else:
            prompt = PROACTIVE_CREATIVE_PROMPT if attempt < 2 else PROACTIVE_CHECKIN_PROMPT
        request_history = list(history)
        variation_instruction = self._build_proactive_variation_instruction(server_id, channel_id)
        if variation_instruction:
            request_history.append({"role": "user", "parts": [variation_instruction]})
        request_history.append({"role": "user", "parts": [prompt]})
        response = self._call_model(
            model,
            request_history,
            attempts=3,
            allow_high_load_retry=True,
            base_delay=2.5,
        )
        generated_text = (self._extract_text(response) or "").strip()
        payload = self._parse_payload(generated_text)
        candidate_text = payload.get("messages") or generated_text
        candidate_text = self._strip_code_fences(candidate_text)
        chunks = sanitize_and_split_response(candidate_text)
        chunks = self._merge_incomplete_chunks(chunks)
        sanitized_chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
        if not sanitized_chunks:
            sanitized_chunks = [candidate_text.strip()]
        primary_text = self._ensure_proactive_completion(
            sanitized_chunks[0],
            history,
            model,
            attempt,
            server_id,
            channel_id,
            kind=normalized_kind,
        )
        sanitized_chunks[0] = primary_text.strip()
        created_messages: List[Dict[str, Any]] = []
        for chunk in sanitized_chunks:
            trimmed = chunk.strip()
            if not trimmed:
                continue
            payload = CreateMessagePayload(
                server_id=server_id,
                channel_id=channel_id,
                author_id="model",
                content=trimmed,
            )
            message = self._service.add_message(payload)
            created_messages.append(message)
        return created_messages

    def _ensure_proactive_completion(
        self,
        text: str,
        history: List[Dict[str, Any]],
        model: Any,
        attempt: int,
        server_id: str,
        channel_id: str,
        *,
        kind: str = "proactive",
    ) -> str:
        candidate = self._normalize_single_chunk(text)
        max_attempts = 3
        for round_index in range(max_attempts):
            if candidate and not self._needs_proactive_retry(
                candidate,
                history,
                server_id,
                channel_id,
                kind=kind,
            ):
                finalized = self._finalize_proactive_candidate(candidate, kind=kind)
                self._remember_proactive_candidate(server_id, channel_id, finalized)
                return finalized
            reason = self._diagnose_proactive_issue(
                candidate,
                history,
                server_id,
                channel_id,
                kind=kind,
            )
            candidate = self._normalize_single_chunk(
                self._request_proactive_fix(candidate, reason, history, model, attempt, round_index),
            )
        raise RuntimeError("Nao consegui gerar uma mensagem proativa completa a tempo")

    def _needs_proactive_retry(
        self,
        text: str,
        history: List[Dict[str, Any]],
        server_id: str,
        channel_id: str,
        *,
        kind: str = "proactive",
    ) -> bool:
        if not text.strip():
            return True
        if self._is_duplicate_of_recent_model(text, history):
            return True
        if self._is_similar_to_recent_proactive(text, server_id, channel_id):
            return True
        if re.search(r"(pensando aqui|lembr(ei|ando)|sabe o que)", text, re.IGNORECASE):
            return True
        if kind == "absence" and not self._looks_like_question(text):
            return True
        return self._looks_incomplete_sentence(text)

    def _diagnose_proactive_issue(
        self,
        text: str,
        history: List[Dict[str, Any]],
        server_id: str,
        channel_id: str,
        *,
        kind: str = "proactive",
    ) -> str:
        if not text.strip():
            return "Mensagem vazia"
        if self._is_duplicate_of_recent_model(text, history):
            return "Você repetiu praticamente a mesma mensagem; tente outro ângulo"
        if self._is_similar_to_recent_proactive(text, server_id, channel_id):
            return "Você está usando o mesmo gancho das últimas proativas; mude a abertura e o foco"
        if re.search(r"(pensando aqui|lembr(ei|ando)|sabe o que)", text, re.IGNORECASE):
            return "Você começou um pensamento mas não concluiu"
        if kind == "absence" and not self._looks_like_question(text):
            return "Transforme em uma pergunta direta pra checar se ele ainda está por perto"
        if self._looks_incomplete_sentence(text):
            return "A frase terminou sem finalizar a ideia"
        return "Finalize a ideia com clareza"

    def _finalize_proactive_candidate(self, text: str, *, kind: str) -> str:
        normalized = text.strip()
        if kind == "absence" or ("?" not in normalized and self._looks_like_question(normalized)):
            normalized = self._ensure_question_format(normalized)
        return normalized

    def _looks_like_question(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if "?" in stripped:
            return True
        starters = (
            "oi",
            "cadê",
            "ta",
            "tá",
            "ainda",
            "sumiu",
            "segue",
            "voce",
            "você",
            "vocês",
            "voces",
            "vc",
            "cê",
            "ce",
            "que",
            "qual",
            "quais",
            "quando",
            "onde",
            "como",
            "sera",
            "será",
            "serao",
            "serão",
        )
        lowered = stripped.lower()
        tokens = [token.strip(",.!?…") for token in lowered.split() if token.strip(",.!?…")]
        if not tokens:
            return False
        if tokens[0] in starters:
            return True
        lead_ins = {"ai", "aí", "aii", "opa", "olha", "tipo", "eita", "aff", "oxe", "oxi", "ei"}
        if len(tokens) >= 2 and tokens[0] in lead_ins and tokens[1] in starters:
            return True
        suffixes = (
            " o que",
            " que call",
            " que é",
            " qual",
            " quais",
            " onde",
            " quando",
            " pra que",
            " por que",
        )
        base = lowered.rstrip(" ?")
        if any(base.endswith(suffix.strip()) for suffix in suffixes):
            return True
        mid_markers = (
            " o que ",
            " o que?",
            " o que vc",
            " o que voce",
            " o que você",
            " pra que ",
            " por que ",
            " sera que",
            " será que",
            " cadê você",
            " cadê voce",
            " cade você",
            " cade voce",
            " cadê vc",
            " cade vc",
            " tá aí",
            " ta ai",
            " tá por aí",
            " ta por ai",
        )
        if any(marker in lowered for marker in mid_markers):
            return True
        return False

    def _ensure_question_format(self, text: str) -> str:
        stripped = text.rstrip()
        if stripped.endswith("?"):
            return stripped
        stripped = stripped.rstrip(".!…")
        return f"{stripped}?"

    def _request_proactive_fix(
        self,
        previous_text: str,
        reason: str,
        history: List[Dict[str, Any]],
        model: Any,
        attempt: int,
        round_index: int,
    ) -> str:
        instruction = (
            "A mensagem proativa anterior ficou incorreta ({reason}). "
            "Você deve enviar UMA mensagem completa, natural, mencionando o sumiço do Pai e convidando" 
            " ele a responder. Não use 'pensando aqui' ou frases em aberto. Apenas conclua a ideia."
        ).format(reason=reason)
        if previous_text:
            instruction += f" Mensagem anterior: '{previous_text}'."
        if attempt >= 2:
            instruction += " Seja breve, como se estivesse checando se ele está por perto."
        else:
            instruction += " Traga um gancho leve relacionado com o último assunto ou algo novo."
        corrective_history = history + [{"role": "user", "parts": [instruction]}]
        response = self._call_model(
            model,
            corrective_history,
            attempts=3,
            allow_high_load_retry=True,
            base_delay=2.5,
        )
        return self._extract_text(response) or ""

    def _is_duplicate_of_recent_model(self, text: str, history: List[Dict[str, Any]], window: int = DUPLICATE_HISTORY_WINDOW) -> bool:
        fingerprint = self._message_fingerprint(text)
        if not fingerprint:
            return False
        recent: List[str] = []
        for entry in reversed(history):
            if entry.get("role") != "model":
                continue
            parts = entry.get("parts") or []
            if not parts:
                continue
            snippet = (parts[0] or "").strip()
            if not snippet or snippet.startswith("["):
                continue
            entry_fp = self._message_fingerprint(snippet)
            if not entry_fp:
                continue
            recent.append(entry_fp)
            if len(recent) >= window:
                break
        return fingerprint in recent

    def _message_fingerprint(self, text: str) -> str:
        if not text:
            return ""
        cleaned = self._strip_code_fences(text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
        cleaned = re.sub(r"[\"'“”‘’]+", "", cleaned)
        cleaned = cleaned.strip(".?!…")
        if not cleaned:
            return ""
        return cleaned[:160]

    def _maybe_seed_proactive_history(
        self,
        server_id: str,
        channel_id: str,
        history: List[Dict[str, Any]],
    ) -> None:
        bucket = self._get_proactive_bucket(server_id, channel_id)
        if bucket:
            return
        seeded: List[Dict[str, str]] = []
        for entry in reversed(history):
            if entry.get("role") != "model":
                continue
            parts = entry.get("parts") or []
            if not parts:
                continue
            snippet = (parts[0] or "").strip()
            if not snippet or snippet.startswith("["):
                continue
            normalized = self._normalize_for_similarity(snippet)
            if not normalized:
                continue
            seeded.append({"raw": snippet, "normalized": normalized})
            if len(seeded) >= PROACTIVE_VARIATION_WINDOW:
                break
        for item in reversed(seeded):
            bucket.append(item)

    def _build_proactive_variation_instruction(self, server_id: str, channel_id: str) -> str:
        bucket = self._recent_proactive_samples.get(self._proactive_history_key(server_id, channel_id))
        if not bucket:
            return ""
        recent_entries = list(bucket)[-PROACTIVE_VARIATION_INSTRUCTION_LIMIT:]
        snippets = []
        for entry in recent_entries:
            raw = entry.get("raw", "").strip()
            snippet = self._shorten_for_prompt(raw)
            if snippet:
                snippets.append(snippet)
        if not snippets:
            return ""
        unique_snippets = list(dict.fromkeys(snippets))
        joined = " | ".join(f'"{snippet}"' for snippet in unique_snippets)
        return (
            "[Variedade Proativa: As últimas abordagens foram "
            f"{joined}. Traga agora um início e um gancho completamente diferentes, "
            "evitando repetir estruturas como 'Pai, será que...'.]"
        )

    def _shorten_for_prompt(self, text: str, limit: int = 90) -> str:
        trimmed = (text or "").strip()
        if not trimmed:
            return ""
        single_line = re.sub(r"\s+", " ", trimmed)
        if len(single_line) > limit:
            return single_line[: limit - 1].rstrip() + "…"
        return single_line

    def _proactive_history_key(self, server_id: str, channel_id: str) -> str:
        return f"{server_id}:{channel_id}"

    def _get_proactive_bucket(self, server_id: str, channel_id: str) -> Deque[Dict[str, str]]:
        key = self._proactive_history_key(server_id, channel_id)
        bucket = self._recent_proactive_samples.get(key)
        if bucket is None:
            bucket = deque(maxlen=PROACTIVE_VARIATION_WINDOW)
            self._recent_proactive_samples[key] = bucket
        return bucket

    def _remember_proactive_candidate(self, server_id: str, channel_id: str, text: str) -> None:
        normalized = self._normalize_for_similarity(text)
        if not normalized:
            return
        bucket = self._get_proactive_bucket(server_id, channel_id)
        bucket.append({"raw": text.strip(), "normalized": normalized})

    def _normalize_for_similarity(self, text: str) -> str:
        cleaned = self._strip_code_fences(text or "")
        cleaned = cleaned.lower()
        cleaned = re.sub(r"https?://\S+", " ", cleaned)
        cleaned = re.sub(r"[^0-9a-záéíóúâêîôûãõàèìòùç\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _is_similar_to_recent_proactive(
        self,
        text: str,
        server_id: str,
        channel_id: str,
        threshold: float = PROACTIVE_SIMILARITY_THRESHOLD,
    ) -> bool:
        normalized = self._normalize_for_similarity(text)
        if not normalized:
            return False
        bucket = self._recent_proactive_samples.get(self._proactive_history_key(server_id, channel_id))
        if not bucket:
            return False
        for entry in bucket:
            existing = entry.get("normalized")
            if not existing:
                continue
            similarity = SequenceMatcher(None, normalized, existing).ratio()
            if similarity >= threshold:
                return True
        return False

    def _normalize_single_chunk(self, text: str) -> str:
        cleaned = self._strip_code_fences(text or "")
        chunks = sanitize_and_split_response(cleaned)
        for chunk in chunks:
            trimmed = chunk.strip()
            if trimmed:
                return trimmed
        return cleaned.strip()

    def _merge_incomplete_chunks(self, chunks: List[str]) -> List[str]:
        if not chunks:
            return []
        merged: List[str] = []
        buffer = ""
        for chunk in chunks:
            candidate = chunk if not buffer else f"{buffer} {chunk}".strip()
            if self._looks_incomplete_sentence(candidate):
                buffer = candidate
                continue
            merged.append(candidate)
            buffer = ""
        if buffer:
            if merged:
                merged[-1] = f"{merged[-1]} {buffer}".strip()
            else:
                merged.append(buffer)
        return merged

    def _ensure_complete_chunks(
        self,
        chunks: List[str],
        history: List[Dict[str, Any]],
        model: Any,
    ) -> List[str]:
        if not chunks:
            return []
        if not self._looks_incomplete_sentence(chunks[-1]):
            return chunks
        fragment = chunks[-1].strip()
        corrective_prompt = (
            "A última resposta que você enviou terminou incompleta nesta frase: '{fragment}'. "
            "Continue SOMENTE a partir desse ponto e finalize o raciocínio em até duas frases curtas."
        ).format(fragment=fragment)
        corrective_history = history + [{"role": "user", "parts": [corrective_prompt]}]
        response = self._call_model(model, corrective_history)
        addition_text = self._strip_code_fences(self._extract_text(response) or "")
        addition_chunks = sanitize_and_split_response(addition_text)
        addition_chunks = self._merge_incomplete_chunks(addition_chunks)
        if not addition_chunks:
            chunks[-1] = fragment.rstrip(",") + "..."
            return chunks
        chunks[-1] = f"{fragment} {addition_chunks[0]}".strip()
        if len(addition_chunks) > 1:
            chunks.extend(addition_chunks[1:])
        if self._looks_incomplete_sentence(chunks[-1]):
            chunks[-1] = chunks[-1].rstrip(",") + "..."
        return chunks

    def _ensure_contextual_alignment(
        self,
        chunks: List[str],
        history: List[Dict[str, Any]],
        model: Any,
    ) -> List[str]:
        if not chunks:
            return []
        user_context = self._collect_recent_user_text(history)
        if not user_context.strip():
            return chunks
        combined = " ".join(chunks)
        if not self._needs_contextual_fix(combined, user_context):
            return chunks
        attempts = 2
        for attempt in range(attempts):
            corrective_text = self._request_on_topic_fix(combined, user_context, history, model, attempt)
            cleaned = self._strip_code_fences(corrective_text or "")
            sanitized = sanitize_and_split_response(cleaned)
            sanitized = self._merge_incomplete_chunks(sanitized)
            if not sanitized:
                continue
            candidate = " ".join(sanitized)
            if not self._needs_contextual_fix(candidate, user_context):
                return sanitized
            combined = candidate
        return chunks

    def _collect_recent_user_text(self, history: List[Dict[str, Any]], limit: int = 6) -> str:
        user_lines: List[str] = []
        for entry in history:
            if entry.get("role") != "user":
                continue
            parts = entry.get("parts") or []
            if not parts:
                continue
            snippet = (parts[0] or "").strip()
            if not snippet or snippet.startswith("["):
                continue
            user_lines.append(snippet)
        if not user_lines:
            return ""
        return " ".join(user_lines[-limit:])

    def _needs_contextual_fix(self, candidate: str, user_context: str) -> bool:
        if not candidate:
            return False
        if not self._detect_creation_pitch(candidate):
            return False
        return not self._detect_creation_pitch(user_context)

    def _detect_creation_pitch(self, text: str) -> bool:
        lowered = (text or "").lower()
        if not lowered:
            return False
        has_verb = any(verb in lowered for verb in CREATION_VERBS)
        if not has_verb:
            return False
        has_topic = any(topic in lowered for topic in PROJECT_TOPICS)
        return has_topic

    def _request_on_topic_fix(
        self,
        previous_text: str,
        user_context: str,
        history: List[Dict[str, Any]],
        model: Any,
        attempt: int,
    ) -> str:
        instruction = (
            "Sua resposta anterior saiu do assunto porque sugeriu criar algo novo (jogo/app/projeto) sem o Pai pedir. "
            "Reescreva tudo mantendo o foco APENAS no que o Pai falou recentemente."
        )
        if user_context.strip():
            instruction += f" Baseie-se nessas falas recentes do Pai: '{user_context.strip()}'."
        instruction += f" Resposta anterior: '{previous_text.strip()}'."
        instruction += " Entregue no máximo duas frases curtas, naturais e zero propostas inéditas."
        if attempt:
            instruction += " Desta vez, confirme explicitamente algo que o Pai disse antes de mudar de assunto."
        corrective_history = history + [{"role": "user", "parts": [instruction]}]
        response = self._call_model(model, corrective_history)
        return self._extract_text(response) or previous_text

    def _looks_incomplete_sentence(self, text: str) -> bool:
        stripped = (text or "").strip()
        if not stripped:
            return True
        if stripped[-1] in ".!?":
            return False
        lower = stripped.lower()
        if lower.endswith("...") or lower.endswith("…"):
            return True
        if lower.endswith(","):
            return True
        if len(stripped) <= 6: 
            tokens = stripped.split()
            if len(tokens) >= 2:
                return False
            return True
        for suffix in INCOMPLETE_SUFFIXES:
            if lower.endswith(suffix):
                return True
        return False


    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Model management (public API for the server layer)
    # ------------------------------------------------------------------
    def get_model_status(self) -> Dict[str, Any]:
        """Return current model status and settings for the UI."""
        with self._model_lock:
            loaded = self._model is not None
        return {
            "loaded": loaded,
            "model_path": str(self._llama_model_path),
            "n_ctx": self._llama_n_ctx,
            "n_threads": self._llama_n_threads,
            "n_gpu_layers": self._llama_n_gpu_layers,
            "temperature": self._temperature,
            "repeat_penalty": self._repeat_penalty,
            "top_p": self._top_p,
            "top_k": self._top_k,
            "max_tokens": self._max_tokens,
        }

    def list_available_models(self) -> List[Dict[str, Any]]:
        """Return GGUF files found in the models/ directory."""
        entries: List[Dict[str, Any]] = []
        if not self._models_dir.exists():
            return entries
        for path in sorted(self._models_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".gguf", ".bin"}:
                continue
            size_mb = round(path.stat().st_size / (1024 * 1024), 1)
            entries.append({"filename": path.name, "size_mb": size_mb, "path": str(path)})
        return entries

    def load_model(
        self,
        *,
        model_path: Optional[str] = None,
        n_ctx: Optional[int] = None,
        n_threads: Optional[int] = None,
        n_gpu_layers: Optional[int] = None,
        temperature: Optional[float] = None,
        repeat_penalty: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Load (or reload) a GGUF model at runtime."""
        if Llama is None:
            raise RuntimeError("Instale o pacote 'llama-cpp-python' para ativar a IA local")
        if model_path:
            resolved = Path(model_path).expanduser().resolve()
            if not resolved.exists():
                # Try relative to models dir
                resolved = (self._models_dir / model_path).resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"Modelo não encontrado: {model_path}")
            self._llama_model_path = resolved
        if n_ctx is not None:
            self._llama_n_ctx = max(512, int(n_ctx))
        if n_threads is not None:
            self._llama_n_threads = max(1, int(n_threads)) if n_threads > 0 else None
        if n_gpu_layers is not None:
            self._llama_n_gpu_layers = int(n_gpu_layers)
        if temperature is not None:
            self._temperature = max(0.0, min(2.0, float(temperature)))
        if repeat_penalty is not None:
            self._repeat_penalty = max(1.0, min(2.0, float(repeat_penalty)))
        if top_p is not None:
            self._top_p = max(0.0, min(1.0, float(top_p)))
        if top_k is not None:
            self._top_k = max(0, int(top_k))
        if max_tokens is not None:
            self._max_tokens = max(32, min(4096, int(max_tokens)))
        with self._model_lock:
            self._unload_model_unsafe()
            self._model = Llama(
                model_path=str(self._llama_model_path),
                n_ctx=self._llama_n_ctx,
                n_threads=self._llama_n_threads,
                n_gpu_layers=self._llama_n_gpu_layers,
            )
            personality = self._service.get_personality_prompt() or {}
            self._system_instruction = build_system_instruction(personality)
            self._personality_signature = json.dumps(personality, sort_keys=True)
            self._model_loaded = True
        return self.get_model_status()

    def unload_model(self) -> Dict[str, Any]:
        """Release the model from memory."""
        with self._model_lock:
            self._unload_model_unsafe()
        return self.get_model_status()

    def _unload_model_unsafe(self) -> None:
        """Free model resources (caller must hold _model_lock)."""
        if self._model is not None:
            try:
                del self._model
            except Exception:
                pass
            self._model = None
            self._model_loaded = False
            self._personality_signature = None

    def _ensure_model(self) -> Any:
        if Llama is None:
            raise RuntimeError("Instale o pacote 'llama-cpp-python' para ativar a IA local")
        personality = self._service.get_personality_prompt() or {}
        signature = json.dumps(personality, sort_keys=True)
        with self._model_lock:
            if self._model is None:
                if not self._llama_model_path.exists():
                    raise RuntimeError(
                        "Nenhum modelo carregado. Use a interface para carregar um modelo GGUF."
                    )
                self._system_instruction = build_system_instruction(personality)
                self._model = Llama(
                    model_path=str(self._llama_model_path),
                    n_ctx=self._llama_n_ctx,
                    n_threads=self._llama_n_threads,
                    n_gpu_layers=self._llama_n_gpu_layers,
                )
                self._personality_signature = signature
                self._model_loaded = True
            elif signature != self._personality_signature:
                self._system_instruction = build_system_instruction(personality)
                self._personality_signature = signature
        return self._model

    def _extract_text(self, response: Any) -> str:
        if response is None:
            return ""
        text = getattr(response, "text", "") or ""
        if text:
            return self._clean_template_tokens(text)
        if isinstance(response, str):
            return self._clean_template_tokens(response)
        if isinstance(response, dict):
            choices = response.get("choices") or []
            if choices and isinstance(choices[0], dict):
                raw = choices[0].get("message", {}).get("content", "") or ""
                return self._clean_template_tokens(raw)
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return ""
        snippets: List[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            parts = getattr(content, "parts", None)
            if not parts:
                continue
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    snippets.append(part_text)
        return self._clean_template_tokens("\n".join(snippets))

    def _convert_history_to_messages(self, history: List[Dict[str, Any]], system_instruction: str) -> List[Dict[str, str]]:
        """Convert internal history to OpenAI-style messages.

        The system instruction is sent as its own ``user`` message followed
        by a brief ``assistant`` acknowledgement.  This creates the
        multi-turn alternation that Llama-2 (and similar) models rely on to
        produce coherent replies, even when the real conversation has no
        prior turns yet.

        Consecutive messages with the same role are merged into one to
        maintain the strict user/assistant alternation that most chat
        templates (Llama-2, ChatML, etc.) expect.
        """
        messages: List[Dict[str, str]] = []

        # ---- System instruction as a seed turn ----
        system_prefix = system_instruction.strip() if system_instruction else ""
        if system_prefix:
            messages.append({"role": "user", "content": system_prefix})
            messages.append({"role": "assistant", "content": "Entendido, vou agir como Lou"})

        for entry in history:
            role = entry.get("role")
            mapped_role = "assistant" if role == "model" else "user"
            parts = entry.get("parts") or []
            raw_content = str(parts[0]) if parts else ""
            content = self._clean_template_tokens(raw_content)
            if not content:
                continue
            # Merge consecutive messages with the same role
            if messages and messages[-1]["role"] == mapped_role:
                messages[-1]["content"] += "\n" + content
            else:
                messages.append({"role": mapped_role, "content": content})

        # Ensure the last message is from the user so the model generates
        # an assistant reply.  If history ends with an assistant message,
        # drop it to avoid the model echoing itself.
        while messages and messages[-1]["role"] == "assistant":
            messages.pop()
        return messages

    def _parse_payload(self, raw_text: str) -> Dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            return {"reasoning": "", "messages": ""}
        text = self._strip_code_fences(text)
        json_blob = self._extract_json_blob(text)
        if json_blob:
            try:
                data = json.loads(json_blob)
                reasoning = self._strip_code_fences(str(data.get("reasoning", "")))
                messages = self._strip_code_fences(str(data.get("messages", "")))
                return {
                    "reasoning": reasoning,
                    "messages": messages,
                }
            except json.JSONDecodeError:
                pass
        return {"reasoning": "", "messages": text}

    def _extract_json_blob(self, text: str) -> Optional[str]:
        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
        if fenced:
            return fenced.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start : end + 1]

    def _strip_code_fences(self, text: str) -> str:
        if not text:
            return ""
        return re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", text, flags=re.IGNORECASE).strip()

    def _gif_attachment_from_chunk(self, chunk: str) -> Optional[Dict[str, str]]:
        if not chunk.upper().startswith("GIF:"):
            return None
        _, _, remainder = chunk.partition(":")
        slug = remainder.strip().split()[0] if remainder.strip() else ""
        if not slug:
            return None
        filename = self._resolve_gif_filename(slug)
        if not filename:
            return None
        return {"type": "gif", "name": slug, "filename": filename}

    def _resolve_gif_filename(self, slug: str) -> Optional[str]:
        normalized = slug.strip().lower()
        gifs_dir = self._service.config.gifs_dir
        for gif_path in gifs_dir.glob("*.gif"):
            if gif_path.stem.lower() == normalized:
                return gif_path.name
        return None


__all__ = ["LouAIResponder", "AIResponse", "build_system_instruction"]
