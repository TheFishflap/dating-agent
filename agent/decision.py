"""Ein Screenshot → eine strukturierte Entscheidung von Claude."""
from __future__ import annotations

import base64
import io
import json
import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from PIL import Image
from pydantic import BaseModel, Field, ValidationError

from agent.prompts import SYSTEM_PROMPT, build_user_prompt

log = logging.getLogger(__name__)

Action = Literal["swipe_right", "swipe_left", "skip"]
ScreenType = Literal["profile", "match_popup", "ad_or_paywall", "other"]
Smoking = Literal["no", "sometimes", "regularly", "unknown"]
BodyType = Literal["slim", "athletic", "average", "curvy", "overweight", "unknown"]


class ProfileFacts(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    distance_km: Optional[float] = None
    location: Optional[str] = None
    job: Optional[str] = None
    education: Optional[str] = None
    height_cm: Optional[int] = None
    looking_for: Optional[str] = None
    smoking: Smoking = "unknown"
    body_type: BodyType = "unknown"
    interests: list[str] = Field(default_factory=list)
    bio_excerpt: Optional[str] = None
    prompts: list[str] = Field(default_factory=list)
    verified: Optional[bool] = None
    red_flags: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    screen_type: ScreenType
    multiple_profiles_visible: bool
    attractiveness: Optional[int] = None
    dealbreaker_hit: bool = False
    action: Action
    reason: str
    confidence: float
    profile: ProfileFacts


def _nullable(t: str) -> dict:
    return {"type": [t, "null"]}


_STR_LIST = {"type": "array", "items": {"type": "string"}}

# Von Hand gepflegt (statt model_json_schema()), damit das Schema exakt den
# Anforderungen von Structured Outputs entspricht: alles required,
# additionalProperties false, keine $refs.
DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "screen_type": {"type": "string", "enum": list(ScreenType.__args__)},
        "multiple_profiles_visible": {
            "type": "boolean",
            "description": "true, wenn die Screenshots mehr als ein Profil zeigen",
        },
        "attractiveness": {
            "type": ["integer", "null"],
            "description": "1–10, nur bei screen_type=profile, sonst null",
        },
        "dealbreaker_hit": {
            "type": "boolean",
            "description": "true, wenn der Profiltext einen der genannten Dealbreaker erfüllt",
        },
        "action": {"type": "string", "enum": list(Action.__args__)},
        "reason": {"type": "string", "description": "1–2 Sätze, Deutsch"},
        "confidence": {"type": "number", "description": "0.0 bis 1.0"},
        "profile": {
            "type": "object",
            "properties": {
                "name": _nullable("string"),
                "age": _nullable("integer"),
                "distance_km": _nullable("number"),
                "location": _nullable("string"),
                "job": _nullable("string"),
                "education": _nullable("string"),
                "height_cm": _nullable("integer"),
                "looking_for": _nullable("string"),
                "smoking": {"type": "string", "enum": list(Smoking.__args__)},
                "body_type": {"type": "string", "enum": list(BodyType.__args__)},
                "interests": _STR_LIST,
                "bio_excerpt": _nullable("string"),
                "prompts": _STR_LIST,
                "verified": _nullable("boolean"),
                "red_flags": _STR_LIST,
            },
            "required": list(ProfileFacts.model_fields),
            "additionalProperties": False,
        },
    },
    "required": list(Decision.model_fields),
    "additionalProperties": False,
}


class DecisionError(Exception):
    pass


class DecisionEngine:
    """Wählt das Backend aus der Config: `claude_cli` (Claude-Abo) oder `api` (API-Key)."""

    def __init__(self, agent_cfg: dict[str, Any], work_dir: Path | None = None):
        self.cfg = agent_cfg
        backend = agent_cfg.get("backend", "claude_cli")
        if backend == "claude_cli":
            self.backend: _Backend = ClaudeCliBackend(agent_cfg, work_dir or Path("data/tmp"))
        elif backend == "api":
            self.backend = ApiBackend(agent_cfg)
        else:
            raise ValueError(f"Unbekanntes Backend: {backend}")

    def decide(self, pngs: bytes | list[bytes]) -> tuple[Decision, dict[str, Any]]:
        """Bewertet ein Profil aus 1..n Screenshots (oben → unten).

        Gibt (Entscheidung, Metadaten wie Modell/Verbrauch) zurück.
        """
        if isinstance(pngs, bytes):
            pngs = [pngs]
        edge = int(self.cfg.get("max_image_edge", 1600))
        pngs = [_downscale(p, edge) for p in pngs]
        prompt = build_user_prompt(self.cfg.get("preferences", {}), n_images=len(pngs))
        data, meta = self.backend.decide(pngs, prompt)
        try:
            decision = Decision.model_validate(data)
        except ValidationError as e:
            raise DecisionError(f"Ungültige strukturierte Antwort: {e}") from e
        decision.confidence = max(0.0, min(1.0, decision.confidence))
        return decision, meta


class _Backend:
    def decide(self, pngs: list[bytes], user_prompt: str) -> tuple[dict, dict[str, Any]]:
        raise NotImplementedError


class ClaudeCliBackend(_Backend):
    """Ruft die Claude-Code-CLI headless auf (`claude -p`) und nutzt so das Claude-Abo.

    Der Screenshot wird als Datei abgelegt; die CLI darf nur das Read-Tool
    benutzen und nur in diesem Ordner lesen. Keine Session-Historie, keine
    Projekt-/User-Settings, keine MCP-Server.
    """

    def __init__(self, cfg: dict[str, Any], work_dir: Path):
        self.cfg = cfg
        self.bin = find_claude_cli(cfg.get("claude_cli_path"))
        self.work_dir = work_dir.resolve()
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def decide(self, pngs: list[bytes], user_prompt: str) -> tuple[dict, dict[str, Any]]:
        batch = uuid.uuid4().hex[:8]
        imgs = []
        for i, png in enumerate(pngs, 1):
            path = self.work_dir / f"screen_{batch}_{i}.png"
            path.write_bytes(png)
            imgs.append(path)
        listing = "\n".join(f"{i}. {p}" for i, p in enumerate(imgs, 1))
        prompt = (f"{user_prompt}\n\nScreenshots (in dieser Reihenfolge):\n{listing}\n"
                  "Lies alle mit dem Read-Tool und antworte im vorgegebenen JSON-Format.")
        cmd = [
            self.bin, "-p", prompt,
            "--output-format", "json",
            "--json-schema", json.dumps(DECISION_SCHEMA),
            "--system-prompt", SYSTEM_PROMPT,
            "--model", self.cfg.get("model", "claude-opus-5-5"),
            "--tools", "Read",
            "--allowedTools", f"Read({self.work_dir}/**)",
            "--add-dir", str(self.work_dir),
            "--no-session-persistence",
            "--setting-sources", "",
            "--strict-mcp-config",
        ]
        try:
            res = subprocess.run(cmd, cwd=self.work_dir, capture_output=True, text=True,
                                 timeout=int(self.cfg.get("cli_timeout_s", 180)))
        except subprocess.TimeoutExpired as e:
            raise DecisionError("Claude-CLI Timeout") from e
        finally:
            for path in imgs:
                path.unlink(missing_ok=True)

        try:
            out = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            hint = (res.stderr or res.stdout).strip()[-400:]
            raise DecisionError(f"Claude-CLI (Exit {res.returncode}): {hint}") from e
        if out.get("is_error") or res.returncode != 0:
            raise DecisionError(f"Claude-CLI Fehler: {str(out.get('result'))[:400]}")

        meta = {
            "backend": "claude_cli",
            "model": self.cfg.get("model"),
            "duration_ms": out.get("duration_ms"),
            "num_turns": out.get("num_turns"),
            "usage": out.get("usage"),
        }
        data = out.get("structured_output")
        if data is None:  # Fallback: JSON im Ergebnistext
            data = _extract_json(str(out.get("result", "")))
        return data, meta


class ApiBackend(_Backend):
    """Direkter Aufruf der Anthropic API (braucht ANTHROPIC_API_KEY)."""

    def __init__(self, cfg: dict[str, Any]):
        import anthropic
        self.cfg = cfg
        self.client = anthropic.Anthropic()

    def decide(self, pngs: list[bytes], user_prompt: str) -> tuple[dict, dict[str, Any]]:
        images = [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/png",
                "data": base64.standard_b64encode(png).decode("ascii")}}
            for png in pngs
        ]
        params: dict[str, Any] = dict(
            model=self.cfg["model"],
            max_tokens=int(self.cfg.get("max_tokens", 4000)),
            system=SYSTEM_PROMPT,
            output_config={
                "effort": self.cfg.get("effort", "low"),
                "format": {"type": "json_schema", "schema": DECISION_SCHEMA},
            },
            messages=[{
                "role": "user",
                "content": [*images, {"type": "text", "text": user_prompt}],
            }],
        )
        if self.cfg.get("refusal_fallbacks", True):
            response = self.client.beta.messages.create(
                **params,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        else:
            response = self.client.messages.create(**params)

        meta = {
            "backend": "api",
            "model": response.model,
            "stop_reason": response.stop_reason,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        if response.stop_reason == "refusal":
            raise DecisionError(f"Anfrage abgelehnt: {getattr(response, 'stop_details', None)}")
        if response.stop_reason == "max_tokens":
            raise DecisionError("Antwort abgeschnitten (max_tokens) — Wert erhöhen.")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise DecisionError(f"Kein Text in der Antwort (stop_reason={response.stop_reason}).")
        return _extract_json(text), meta


def find_claude_cli(configured: str | None = None) -> str:
    """Claude-Code-CLI finden: Config → PATH → von der Claude-Desktop-App mitgeliefert."""
    if configured and configured != "auto":
        return str(Path(configured).expanduser())
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    bundled = sorted(
        (Path.home() / "Library/Application Support/Claude/claude-code").glob(
            "*/*/claude.app/Contents/MacOS/claude"),
        key=lambda p: p.stat().st_mtime,
    )
    if bundled:
        return str(bundled[-1])
    raise DecisionError("Claude-Code-CLI nicht gefunden — agent.claude_cli_path in der Config setzen.")


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise DecisionError(f"Kein gültiges JSON in der Antwort: {text[:200]}")


def _downscale(png: bytes, max_edge: int) -> bytes:
    img = Image.open(io.BytesIO(png))
    if max(img.size) <= max_edge:
        return png
    img.thumbnail((max_edge, max_edge))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
