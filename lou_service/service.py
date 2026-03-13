"""Core service exposing Lou's state and chat data to multiple frontends."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import random
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import LouServiceConfig


@dataclass
class CreateMessagePayload:
    server_id: str
    channel_id: str
    author_id: str
    content: str
    reply_to: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class LouService:
    """Headless core with the same data used by the Qt frontend."""

    def __init__(self, config: Optional[LouServiceConfig] = None) -> None:
        root = Path(__file__).resolve().parent.parent
        self.config = config or LouServiceConfig.from_root(root)
        self.config.ensure_directories()
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._long_term_memories: List[str] = []
        self._personality_data: Dict[str, Any] = {}
        self._available_gifs: List[str] = []
        self._load_state()

    # ------------------------------------------------------------------
    # Loaders / persistence
    # ------------------------------------------------------------------
    def _load_state(self) -> None:
        with self._lock:
            self._data = self._load_json(self.config.chat_data_file) or self._default_data()
            self._long_term_memories = self._load_long_term_memories()
            self._personality_data = self._load_json(self.config.personality_file) or {}
            self._available_gifs = [entry["name"] for entry in self._build_gif_entries()]
            self._normalize_data()
            self._persist_chat_data()

    def _load_json(self, file_path: Path) -> Optional[Any]:
        if not file_path.exists():
            return None
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError:
            return None

    def _load_long_term_memories(self) -> List[str]:
        """Carrega memórias de longo prazo do memory_bank.json"""
        if not self.config.memory_file.exists():
            return []
        try:
            with self.config.memory_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                # Suporta formato antigo (dict) e novo (list)
                if isinstance(data, dict):
                    return data.get("long_term", [])
                elif isinstance(data, list):
                    return data
        except json.JSONDecodeError:
            return []
        return []

    def _persist_chat_data(self) -> None:
        with self.config.chat_data_file.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2, ensure_ascii=False)

    def _persist_long_term_memories(self) -> None:
        """Salva memórias de longo prazo no memory_bank.json"""
        with self.config.memory_file.open("w", encoding="utf-8") as handle:
            json.dump(self._long_term_memories, handle, indent=2, ensure_ascii=False)


    def _persist_personality_data(self) -> None:
        with self.config.personality_file.open("w", encoding="utf-8") as handle:
            json.dump(self._personality_data, handle, indent=2, ensure_ascii=False)

    def _default_data(self) -> Dict[str, Any]:
        return {
            "servers": [
                {
                    "id": "s1",
                    "name": "Laboratório da Lou",
                    "icon_char": "L",
                    "avatar": None,
                    "channels": [
                        {"id": "c1_1", "name": "papo-ia", "type": "text", "messages": []}
                    ],
                }
            ],
            "profiles": {
                "user": {"name": "Mateus", "id_tag": "#1987", "avatar": "default.png"},
                "model": {"name": "Lou", "id_tag": "#AI", "avatar": "lou.png"},
            },
        }

    def _normalize_data(self) -> None:
        profiles = self._data.setdefault("profiles", {})
        profiles.setdefault("user", {"name": "Mateus", "id_tag": "#1987", "avatar": "default.png"})
        profiles.setdefault("model", {"name": "Lou", "id_tag": "#AI", "avatar": "lou.png"})
        for server in self._data.get("servers", []):
            server.setdefault("avatar", None)
            text_channels = [c for c in server.get("channels", []) if c.get("type") == "text"]
            server["channels"] = text_channels
            # Remove legacy voice_channels if present
            server.pop("voice_channels", None)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------
    def get_profiles(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._data.get("profiles", {}))

    def list_servers(self) -> List[Dict[str, Any]]:
        with self._lock:
            servers = self._data.get("servers", [])
            return deepcopy(servers[:1])

    def get_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return next((deepcopy(s) for s in self._data.get("servers", []) if s["id"] == server_id), None)

    def list_channels(self, server_id: str) -> List[Dict[str, Any]]:
        server = self.get_server(server_id)
        return server.get("channels", []) if server else []

    def get_channel(self, server_id: str, channel_id: str) -> Optional[Dict[str, Any]]:
        server = self.get_server(server_id)
        if not server:
            return None
        return next((deepcopy(c) for c in server.get("channels", []) if c["id"] == channel_id), None)

    def list_messages(self, server_id: str, channel_id: str) -> List[Dict[str, Any]]:
        channel = self.get_channel(server_id, channel_id)
        return channel.get("messages", []) if channel else []

    def get_personality_prompt(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._personality_data)

    def get_available_gifs(self) -> List[Dict[str, str]]:
        with self._lock:
            gif_entries = self._build_gif_entries()
            self._available_gifs = [entry["name"] for entry in gif_entries]
            return gif_entries

    def refresh_gif_cache(self) -> List[Dict[str, str]]:
        return self.get_available_gifs()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def add_message(self, payload: CreateMessagePayload) -> Dict[str, Any]:
        with self._lock:
            channel = self._locate_channel(payload.server_id, payload.channel_id)
            if channel is None:
                raise KeyError("Canal nao encontrado")
            message = self._build_message(payload)
            channel.setdefault("messages", []).append(message)
            self._persist_chat_data()
            return deepcopy(message)

    def create_server(self, name: str, avatar_filename: Optional[str] = None) -> Dict[str, Any]:
        raise ValueError("Criar novos grupos foi desativado nesta versão.")

    def create_channel(self, server_id: str, name: str) -> Dict[str, Any]:
        new_channel = {"id": f"c_{uuid.uuid4().hex[:6]}", "name": name, "type": "text", "messages": []}
        with self._lock:
            server = self._locate_server(server_id)
            if server is None:
                raise KeyError("Servidor nao encontrado")
            server.setdefault("channels", []).append(new_channel)
            self._persist_chat_data()
        return deepcopy(new_channel)

    def update_server(self, server_id: str, *, name: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            server = self._locate_server(server_id)
            if server is None:
                raise KeyError("Servidor nao encontrado")
            if name is None:
                raise ValueError("Nome obrigatorio")
            trimmed = name.strip()
            if not trimmed:
                raise ValueError("Nome nao pode ser vazio")
            if server.get("name") != trimmed:
                server["name"] = trimmed
                server["icon_char"] = trimmed[0].upper()
                self._persist_chat_data()
            return deepcopy(server)

    def delete_server(self, server_id: str) -> None:
        raise ValueError("Excluir grupos foi desativado nesta versão.")

    def update_channel(self, server_id: str, channel_id: str, *, name: Optional[str] = None) -> Dict[str, Any]:
        if name is None:
            raise ValueError("Nada para atualizar")
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("Nome nao pode ser vazio")
        with self._lock:
            channel = self._locate_channel(server_id, channel_id)
            if channel is None:
                raise KeyError("Canal nao encontrado")
            if channel.get("name") != trimmed:
                channel["name"] = trimmed
                self._persist_chat_data()
            return deepcopy(channel)

    def delete_channel(self, server_id: str, channel_id: str) -> None:
        with self._lock:
            server = self._locate_server(server_id)
            if server is None:
                raise KeyError("Servidor nao encontrado")
            before = len(server.get("channels", []))
            server["channels"] = [c for c in server.get("channels", []) if c.get("id") != channel_id]
            if len(server["channels"]) == before:
                raise KeyError("Canal nao encontrado")
            self._persist_chat_data()

    def update_profile(self, profile_key: str, *, name: Optional[str] = None, avatar: Optional[str] = None) -> Dict[str, Any]:
        if profile_key not in {"user", "model"}:
            raise KeyError("Perfil invalido")
        with self._lock:
            profiles = self._data.setdefault("profiles", {})
            profile = profiles.setdefault(profile_key, {})
            changed = False
            if name is not None:
                trimmed = name.strip()
                if not trimmed:
                    raise ValueError("Nome nao pode ser vazio")
                if profile.get("name") != trimmed:
                    profile["name"] = trimmed
                    changed = True
            if avatar is not None and profile.get("avatar") != avatar:
                profile["avatar"] = avatar
                changed = True
            if changed:
                self._persist_chat_data()
            return deepcopy(profile)

    def update_personality(
        self,
        *,
        personality_definition: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if personality_definition is None:
            raise ValueError("Nada para atualizar")
        with self._lock:
            if not isinstance(self._personality_data, dict):
                self._personality_data = {}
            if not isinstance(personality_definition, dict):
                raise ValueError("personality_definition invalido")
            self._personality_data["personality_definition"] = personality_definition
            self._persist_personality_data()
            return deepcopy(self._personality_data)

    # ------------------------------------------------------------------
    # Memory / style helpers
    # ------------------------------------------------------------------


    def save_long_term_memories(self, new_memories: List[str]) -> None:
        with self._lock:
            changed = False
            for mem in new_memories:
                if isinstance(mem, str) and mem not in self._long_term_memories:
                    self._long_term_memories.append(mem)
                    changed = True
            if changed:
                self._persist_long_term_memories()

    def get_context_snapshot(self) -> Dict[str, List[str]]:
        with self._lock:
            return {
                "long_term": list(self._long_term_memories),
            }

    def update_context(self, *, long_term: Optional[List[str]] = None, **_kwargs: Any) -> Dict[str, List[str]]:
        if not long_term:
            raise ValueError("Nada para atualizar")
        self.save_long_term_memories(long_term)
        return self.get_context_snapshot()

    def generate_proactive_message(self, server_id: str, channel_id: str, *, attempt: int = 0, kind: str = "proactive") -> List[Dict[str, Any]]:
        normalized_kind = (kind or "proactive").strip().lower()
        if normalized_kind == "absence":
            text = self._compose_absence_question(server_id, channel_id)
        else:
            attempt_index = max(attempt, 0)
            text = self._compose_proactive_text(server_id, channel_id, attempt_index)
        payload = CreateMessagePayload(
            server_id=server_id,
            channel_id=channel_id,
            author_id="model",
            content=text,
        )
        return [self.add_message(payload)]

    def _compose_absence_question(self, server_id: str, channel_id: str) -> str:
        channel = self._locate_channel(server_id, channel_id)
        if channel is None:
            raise KeyError("Canal nao encontrado")
        templates = [
            "Tá por aí ainda? Faz um tempo que você não fala nada.",
            "Sumiu? Só queria saber se você ainda tá aí.",
            "Tá ocupado ou só deu uma saída? Me dá um sinal de vida.",
        ]
        return random.choice(templates)

    def _compose_proactive_text(self, server_id: str, channel_id: str, attempt: int) -> str:
        channel = self._locate_channel(server_id, channel_id)
        if channel is None:
            raise KeyError("Canal nao encontrado")
        history = channel.get("messages", [])
        last_user_message = next((msg for msg in reversed(history) if msg.get("role") == "user"), None)
        snippet = self._extract_snippet(last_user_message)
        topic_line = self._format_topic(snippet)
        memory_line = self._format_memory_reference(self._pick_memory_hook())

        if topic_line:
            if attempt >= 2:
                retry_templates = [
                    "Ainda tô esperando você me contar como ficou {topic}. Tá por aí?",
                    "Não queria deixar {topic} sem resposta. Me chama quando puder?",
                    "Voltei só pra saber se seguimos {topic}.",
                ]
                return random.choice(retry_templates).format(topic=topic_line)
            topic_templates = [
                "Tava lembrando {topic} e fiquei curiosa pra saber o resto.",
                "Voltei aqui porque {topic} ficou ecoando. Bora continuar?",
                "Ri sozinha pensando {topic}. Me conta mais um pouco?",
            ]
            return random.choice(topic_templates).format(topic=topic_line)

        if memory_line:
            memory_templates = [
                "Bateu saudade de conversar sobre {memory}.",
                "Passei aqui porque lembrei de {memory}. Quer retomar?",
                "Anotei {memory} e deu vontade de puxar esse assunto contigo.",
            ]
            return random.choice(memory_templates).format(memory=memory_line)

        fallback_templates = [
            "Deu saudade de jogar conversa fora contigo. Aparece aqui?",
            "Tô com vontade de inventar assunto bobo com você. Tá livre?",
            "Passei só pra cutucar e ver se a gente puxa alguma história nova hoje.",
        ]
        if attempt >= 2:
            fallback_templates.extend([
                "Só conferindo se tá tudo bem por aí. Me chama quando quiser conversar.",
                "Você sumiu um pouquinho e bateu saudade. Tá tudo certo?",
            ])
        return random.choice(fallback_templates)

    def _extract_snippet(self, message: Optional[Dict[str, Any]]) -> str:
        if not message:
            return ""
        text = message.get("content") or (message.get("parts") or [""])[0]
        text = (text or "").strip()
        text = text.replace('"', "'")
        if len(text) > 60:
            text = f"{text[:57]}..."
        return text

    def _pick_memory_hook(self) -> str:
        with self._lock:
            pool: List[str] = []
            if self._long_term_memories:
                long_items = [mem for mem in self._long_term_memories if isinstance(mem, str)]
                if long_items:
                    pool.extend(random.sample(long_items, k=min(3, len(long_items))))
        cleaned = [mem.strip() for mem in pool if isinstance(mem, str) and mem.strip()]
        return random.choice(cleaned) if cleaned else ""

    def _format_topic(self, snippet: str) -> str:
        clean = (snippet or "").strip()
        if not clean:
            return ""
        if len(clean) > 90:
            clean = f"{clean[:87]}..."
        return f'quando você falou "{clean}"'

    def _format_memory_reference(self, raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            return ""
        replacements = {
            "Mateus": "você",
            "mateus": "você",
            "Lou": "eu",
            "lou": "eu",
        }
        for target, repl in replacements.items():
            text = text.replace(target, repl)
        text = text.replace("…", " ").strip(" .")
        if len(text) > 90:
            text = f"{text[:87]}..."
        return text

    # ------------------------------------------------------------------
    # Context builder (shared with IA workers)
    # ------------------------------------------------------------------
    def build_history_context(self, server_id: str, channel_id: str) -> List[Dict[str, Any]]:
        channel_messages = self.list_messages(server_id, channel_id)
        recent_history = channel_messages[-20:]
        history_copy: List[Dict[str, Any]] = []
        for msg in recent_history:
            parts = msg.get("parts")
            if parts and parts[0]:
                history_copy.append({"role": msg["role"], "parts": [parts[0]]})

        now = datetime.now()
        history_copy.insert(0, {"role": "user", "parts": [self._build_context_banner(now)]})

        # Inject ALL long-term memories as a single context block
        if self._long_term_memories:
            mem_text = " | ".join(self._long_term_memories)
            history_copy.insert(1, {"role": "user", "parts": [f"[Memórias de Longo Prazo: {mem_text}]"]})

        # Inject available GIFs (dynamic, depends on files in assets/gifs/)
        if self._available_gifs:
            gif_list = ", ".join([f"'{gif}'" for gif in self._available_gifs])
            history_copy.insert(2, {"role": "user", "parts": [f"[GIFs disponíveis: {gif_list}]"]})

        return history_copy

    def _build_context_banner(self, now: datetime) -> str:
        dias = [
            "Segunda-feira",
            "Terça-feira",
            "Quarta-feira",
            "Quinta-feira",
            "Sexta-feira",
            "Sábado",
            "Domingo",
        ]
        meses = [
            "Janeiro",
            "Fevereiro",
            "Março",
            "Abril",
            "Maio",
            "Junho",
            "Julho",
            "Agosto",
            "Setembro",
            "Outubro",
            "Novembro",
            "Dezembro",
        ]
        data_hora = f"{dias[now.weekday()]}, {now.day} de {meses[now.month - 1]} de {now.year}, {now.strftime('%H:%M')}"
        hora = now.hour
        if hora < 12:
            periodo = "Manhã — use 'Bom dia' se cumprimentar"
        elif hora < 18:
            periodo = "Tarde — use 'Boa tarde' se cumprimentar"
        else:
            periodo = "Noite — use 'Boa noite' se cumprimentar"
        return f"[INSTRUÇÕES] Data/Hora Atuais: {data_hora}. Período: {periodo}."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _locate_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        for server in self._data.get("servers", []):
            if server["id"] == server_id:
                return server
        return None

    def _locate_channel(self, server_id: str, channel_id: str) -> Optional[Dict[str, Any]]:
        server = self._locate_server(server_id)
        if not server:
            return None
        for channel in server.get("channels", []):
            if channel["id"] == channel_id:
                return channel
        return None

    def _build_message(self, payload: CreateMessagePayload) -> Dict[str, Any]:
        message_id = f"m-{uuid.uuid4()}"
        timestamp = datetime.now().isoformat(timespec="seconds")
        message = {
            "id": message_id,
            "role": "model" if payload.author_id == "model" else "user",
            "authorId": payload.author_id,
            "parts": [payload.content],
            "content": payload.content,
            "timestamp": timestamp,
        }
        attachments = self._normalize_attachments(payload.attachments)
        if attachments:
            message["attachments"] = attachments
        if payload.reply_to:
            message["replyTo"] = payload.reply_to
            reply_snapshot = self._snapshot_message(payload.server_id, payload.channel_id, payload.reply_to)
            if reply_snapshot:
                message["is_reply_to"] = reply_snapshot
        return message

    def _normalize_attachments(self, attachments: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        if not attachments or not isinstance(attachments, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            kind = attachment.get("type")
            if kind == "gif":
                normalized.append(self._normalize_gif_attachment(attachment))
        return normalized

    def _normalize_gif_attachment(self, attachment: Dict[str, Any]) -> Dict[str, Any]:
        filename = (attachment.get("filename") or "").strip()
        if not filename:
            raise ValueError("GIF invalido")
        gif_path = (self.config.gifs_dir / filename).resolve()
        try:
            gif_path.relative_to(self.config.gifs_dir.resolve())
        except ValueError as exc:
            raise ValueError("GIF fora do diretório permitido") from exc
        if not gif_path.exists():
            raise ValueError("GIF nao encontrado")
        name = (attachment.get("name") or gif_path.stem).strip() or gif_path.stem
        return {
            "type": "gif",
            "name": name,
            "filename": gif_path.name,
            "url": f"/assets/gifs/{gif_path.name}",
        }

    def _build_gif_entries(self) -> List[Dict[str, str]]:
        gif_entries: List[Dict[str, str]] = []
        for gif_path in sorted(self.config.gifs_dir.glob("*.gif")):
            gif_entries.append(
                {
                    "name": gif_path.stem,
                    "filename": gif_path.name,
                    "url": f"/assets/gifs/{gif_path.name}",
                }
            )
        return gif_entries

    def _snapshot_message(self, server_id: str, channel_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        channel = self._locate_channel(server_id, channel_id)
        if not channel:
            return None
        for msg in channel.get("messages", []):
            if msg.get("id") == message_id:
                return deepcopy(msg)
        return None


__all__ = ["LouService", "CreateMessagePayload"]
