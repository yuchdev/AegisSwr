"""Typed, frozen configuration objects parsed from ``agents.yaml``.

This module is pure Python + stdlib + PyYAML. It has **no** ``litellm`` (or any
model-client) dependency so configuration can be validated in isolation, e.g.
at process startup or in tests, without pulling in heavy SDKs.

The public entry point is :meth:`RouterConfig.from_yaml`, which loads the YAML
file, resolves ``${ENV_VAR}`` placeholders from the environment, and enforces
the validation contract documented in the 0003 roadmap (rules R1-R4).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from aegis_swr.router.exceptions import ConfigValidationError

# Matches a ``${VAR_NAME}`` placeholder anywhere inside a string value.
_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

# Documented defaults applied when an agent omits an optional field.
_DEFAULT_TIMEOUT_S = 30.0
_DEFAULT_RETRY_ATTEMPTS = 2
_DEFAULT_RETRY_BACKOFF_S = 1.0


@dataclass(frozen=True)
class RetryPolicy:
    """Retry behaviour for a single agent's model calls.

    :ivar attempts: Number of attempts per model before moving on.
    :ivar backoff_s: Base backoff delay between attempts, in seconds.
    """

    attempts: int = _DEFAULT_RETRY_ATTEMPTS
    backoff_s: float = _DEFAULT_RETRY_BACKOFF_S


@dataclass(frozen=True)
class ProviderConfig:
    """Resolved credentials and endpoint for a single model provider.

    :ivar name: The provider key as it appears in ``providers:``.
    :ivar api_key: API key resolved from the environment; may be an empty
        string for unauthenticated self-hosted endpoints.
    :ivar base_url: Optional base URL; ``None`` for providers with a
        vendor-fixed endpoint (e.g. Anthropic).
    """

    name: str
    api_key: str = field(repr=False)
    base_url: Optional[str] = None


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a single role-bound agent.

    :ivar role: The role name this agent fulfils (e.g. ``primary_reasoning``).
    :ivar model: LiteLLM model string, e.g. ``anthropic/claude-sonnet-4-6``.
        ``None`` for roles whose model is chosen elsewhere (e.g.
        ``openclaude_agent``, whose model is OpenClaude's concern).
    :ivar fallback: Ordered fallback model strings (tuple for hashability).
    :ivar timeout_s: Per-call timeout, in seconds.
    :ivar retry: The :class:`RetryPolicy` governing retries.
    :ivar provider: Explicit provider name, set directly from the YAML
        ``provider:`` key. Every existing role's provider is inferred from its
        ``model`` string prefix against the ``providers:`` block (Milestone
        0003); that inference has nothing to key off when ``model`` is ``None``,
        as it is for ``openclaude_agent``. This field is ``None`` for all
        pre-existing roles (they keep using prefix inference) and is populated
        only for roles that set ``provider:`` explicitly in YAML, which today is
        ``openclaude_agent`` alone.
    :ivar enabled_when: Name of an environment variable that gates this role's
        inclusion. When set and the named variable is absent or empty in the
        process environment, :meth:`RouterConfig.from_yaml` silently omits this
        role from :attr:`RouterConfig.agents` - no
        :class:`ConfigValidationError` is raised. Roles without ``enabled_when``
        are always included (unchanged behaviour).
    """

    role: str
    model: Optional[str]
    fallback: tuple[str, ...] = ()
    timeout_s: float = _DEFAULT_TIMEOUT_S
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    provider: Optional[str] = None
    enabled_when: Optional[str] = None


@dataclass(frozen=True)
class RouterConfig:
    """Validated, immutable view of ``agents.yaml``.

    :ivar providers: Mapping of provider key to :class:`ProviderConfig`.
    :ivar agents: Mapping of role name to :class:`AgentConfig`.
    """

    providers: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]

    @classmethod
    def from_yaml(cls, path: Path) -> RouterConfig:
        """Load and validate ``agents.yaml``, resolving ``${ENV_VAR}`` references.

        Validation is eager and enforces (see roadmap 0003):

        - **R1** - every ``${ENV_VAR}`` referenced in a provider ``api_key`` or
          ``base_url`` must be set in the environment; all missing names are
          reported together. A variable set to an empty string is valid.
        - **R2** - every agent ``model`` prefix must match a defined provider.
          A role that sets ``provider:`` explicitly is exempt: its provider
          identity is taken verbatim (its ``model`` may be ``null`` and its
          provider need not appear in the ``providers:`` block).

        Two additional rules govern role identity and conditional inclusion:

        - **Role key** - a YAML agent entry that omits ``role:`` defaults both
          its role name and its key in :attr:`agents` to the YAML *entry key*
          (this is how ``openclaude_agent`` becomes ``agents["openclaude_agent"]``).
          Entries with an explicit ``role:`` are keyed by that role value,
          unchanged.
        - **enabled_when** - if a role sets ``enabled_when``, the named
          environment variable is read once here; when it is unset or empty the
          role is omitted from :attr:`agents` entirely (no exception). Roles
          without ``enabled_when`` are always included.

        :param path: Path to the ``agents.yaml`` file.
        :return: A validated :class:`RouterConfig`.
        :raises ConfigValidationError: if env vars are missing (R1) or provider
            references are undefined (R2).
        """
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        raw_providers: dict[str, dict] = raw.get("providers", {}) or {}
        raw_agents: dict[str, dict] = raw.get("agents", {}) or {}

        providers = cls._build_providers(raw_providers)
        agents = cls._build_agents(raw_agents)
        cls._validate_provider_references(providers, agents)

        return cls(providers=providers, agents=agents)

    @staticmethod
    def _build_providers(
        raw_providers: dict[str, dict],
    ) -> dict[str, ProviderConfig]:
        """Resolve provider credentials, aggregating all missing env vars (R1).

        :param raw_providers: The raw ``providers`` mapping from YAML.
        :return: Mapping of provider key to resolved :class:`ProviderConfig`.
        :raises ConfigValidationError: if any referenced env var is unset.
        """
        missing: list[str] = []
        resolved: dict[str, ProviderConfig] = {}

        for name, spec in raw_providers.items():
            spec = spec or {}
            raw_api_key = spec.get("api_key")
            # A present-but-null ``api_key:`` is an empty (unauthenticated)
            # credential, not the literal string "None" (R1 semantics).
            api_key_template = "" if raw_api_key is None else str(raw_api_key)
            api_key = RouterConfig._resolve_env(api_key_template, missing)
            raw_base_url = spec.get("base_url")
            base_url: Optional[str] = None
            if raw_base_url is not None:
                base_url = RouterConfig._resolve_env(str(raw_base_url), missing)
            resolved[name] = ProviderConfig(name=name, api_key=api_key, base_url=base_url)

        if missing:
            # Preserve first-seen order while de-duplicating.
            seen: dict[str, None] = dict.fromkeys(missing)
            raise ConfigValidationError(f"Missing environment variables: {', '.join(seen)}")
        return resolved

    @staticmethod
    def _resolve_env(value: str, missing: list[str]) -> str:
        """Substitute ``${VAR}`` placeholders, recording any unset variables.

        An environment variable set to the empty string is treated as present
        (valid); only unset variables are recorded in ``missing``.

        :param value: The raw string value possibly containing placeholders.
        :param missing: Accumulator list, appended to for each unset var.
        :return: The value with all resolvable placeholders substituted.
        """

        def _replace(match: re.Match[str]) -> str:
            """Substitute one ``${VAR}`` match with its env value, tracking misses."""
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value is None:
                missing.append(var_name)
                return ""
            return env_value

        return _ENV_VAR_PATTERN.sub(_replace, value)

    @staticmethod
    def _build_agents(raw_agents: dict[str, dict]) -> dict[str, AgentConfig]:
        """Build agent configs keyed by role, applying documented defaults.

        An entry that omits ``role:`` defaults its role name (and key) to the
        YAML entry key. An entry whose ``enabled_when`` names an unset or empty
        environment variable is skipped entirely (not added, no exception).

        :param raw_agents: The raw ``agents`` mapping from YAML.
        :return: Mapping of role name to :class:`AgentConfig`.
        """
        agents: dict[str, AgentConfig] = {}
        for name, spec in raw_agents.items():
            spec = spec or {}
            enabled_when = spec.get("enabled_when")
            if enabled_when and not os.environ.get(enabled_when):
                # Gated role whose env var is unset/empty - omit it silently.
                continue
            role = spec.get("role", name)
            model = spec.get("model")
            provider = spec.get("provider")
            fallback = tuple(spec.get("fallback") or ())
            timeout_s = float(spec.get("timeout_s", _DEFAULT_TIMEOUT_S))
            raw_retry = spec.get("retry") or {}
            retry = RetryPolicy(
                attempts=int(raw_retry.get("attempts", _DEFAULT_RETRY_ATTEMPTS)),
                backoff_s=float(raw_retry.get("backoff_s", _DEFAULT_RETRY_BACKOFF_S)),
            )
            agents[role] = AgentConfig(
                role=role,
                model=model,
                fallback=fallback,
                timeout_s=timeout_s,
                retry=retry,
                provider=provider,
                enabled_when=enabled_when,
            )
        return agents

    @staticmethod
    def _validate_provider_references(
        providers: dict[str, ProviderConfig],
        agents: dict[str, AgentConfig],
    ) -> None:
        """Verify every agent model prefix matches a defined provider (R2).

        All violations are collected before raising so operators see every
        broken reference at once. A role that sets ``provider:`` explicitly is
        exempt from prefix inference: its provider identity is taken verbatim
        and need not appear in the ``providers:`` block (its ``model`` may be
        ``None``). A role that provides *neither* an explicit ``provider:`` nor
        a ``model`` to infer one from is an unresolvable configuration and is
        reported as a violation (rather than raising ``AttributeError``).

        :param providers: Resolved provider mapping.
        :param agents: Resolved agent mapping.
        :raises ConfigValidationError: if any agent references an unknown
            provider, or omits both ``provider:`` and ``model``.
        """
        defined = ", ".join(sorted(providers))
        violations: list[str] = []
        for role, agent in agents.items():
            if agent.provider is not None:
                # Explicit provider - exempt from model-prefix inference (R2).
                continue
            if agent.model is None:
                # No explicit provider and no model to infer one from: the
                # config is unresolvable rather than merely referencing an
                # unknown provider. Fail gracefully instead of AttributeError.
                violations.append(f"Agent '{role}' has model=null but no explicit 'provider:' key.")
                continue
            provider_prefix = agent.model.split("/", 1)[0]
            if provider_prefix not in providers:
                violations.append(
                    f"Agent '{role}' references unknown provider '{provider_prefix}'. Defined providers: {defined}"
                )
        if violations:
            raise ConfigValidationError(" ".join(violations))

    def agent_for_role(self, role: str) -> AgentConfig:
        """Return the :class:`AgentConfig` bound to ``role`` (R4 on miss).

        :param role: The role name (e.g. ``primary_reasoning``).
        :return: The matching :class:`AgentConfig`.
        :raises KeyError: if the role is unknown, with a message naming the
            requested role and the available roles.
        """
        try:
            return self.agents[role]
        except KeyError:
            available = ", ".join(self.agents)
            raise KeyError(f"Unknown role '{role}'. Available roles: {available}") from None
