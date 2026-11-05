"""`.incident.yml` parsing: the service map and runbook the investigation starts from.

The file lives in the investigated repository, on the branch that deploys. It
plays the part of AWS DevOps Agent's topology and runbooks: which services
exist, which files build each one, who calls whom, and what the team already
knows about failures.

    language: Spanish            # language of the report prose (default English)
    services:
      web:
        paths: [aplicaciones-contenedores/web/]
        depends_on: [api-clientes]
        notes: NGINX, the only public entrypoint.
    runbook:
      - If the deploy fails, desplegar.sh restores the previous version by itself.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_langgraph.domain.errors import ConfigError
from agent_langgraph.incidents.models import IncidentMap, ServiceSpec

DEFAULT_PATH = ".incident.yml"


class _ServiceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(default_factory=list, max_length=20)
    depends_on: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=500)


class _MapSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(default="English", max_length=30)
    services: dict[str, _ServiceSchema] = Field(default_factory=dict, max_length=30)
    runbook: list[str] = Field(default_factory=list, max_length=30)


def parse_incident_map(text: str) -> IncidentMap:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{DEFAULT_PATH} is not valid YAML") from exc
    if raw is None:
        return IncidentMap()
    if not isinstance(raw, dict):
        raise ConfigError(f"{DEFAULT_PATH} must be a mapping at the top level")
    try:
        parsed = _MapSchema.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise ConfigError(f"{DEFAULT_PATH}: {where}: {first['msg']}") from exc

    unknown = {
        dep
        for spec in parsed.services.values()
        for dep in spec.depends_on
        if dep not in parsed.services
    }
    if unknown:
        raise ConfigError(f"{DEFAULT_PATH}: depends_on names unknown services: {sorted(unknown)}")

    return IncidentMap(
        services=[
            ServiceSpec(name=name, paths=s.paths, depends_on=s.depends_on, notes=s.notes)
            for name, s in parsed.services.items()
        ],
        runbook=parsed.runbook,
        language=parsed.language,
    )


def load_incident_map(path: Path) -> tuple[IncidentMap, str | None]:
    """Return the map and, if it could not be used, a warning for the report."""
    if not path.exists():
        return IncidentMap(), f"{path} not found: investigating without a service map"
    try:
        return parse_incident_map(path.read_text(encoding="utf-8")), None
    except ConfigError as exc:
        return IncidentMap(), f"{exc}; investigating without a service map"
