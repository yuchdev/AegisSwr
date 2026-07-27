"""Base debate agents (the default panel) and shared agent primitives.

This subpackage holds the original four debate voters
(:class:`OSKernelAgent`, :class:`CodeAnalystAgent`, :class:`LogHistorianAgent`,
:class:`SkepticAgent`) plus the shared :class:`BaseAgent` abstraction and the
per-incident :class:`AgentSpec` model. It re-exports those public names so both
the package path (``aegis_swr.agents.base``) and the top-level
(``aegis_swr.agents``) re-export resolve them.

Category convention (see also ``forensic``/``synthesis`` packages):

===========  ====================  ============  ====================  ===============
Category     Package               Tier          Joins debate panel?   Weighted voter?
===========  ====================  ============  ====================  ===============
``base``     ``agents/base/``      debate        yes (default panel)   yes
``forensic`` ``agents/forensic/``  debate        yes (per fault)       yes
``synthesis````agents/synthesis/`` post-debate   no                    no
===========  ====================  ============  ====================  ===============
"""

from aegis_swr.agents.base.base import AgentCategory, AgentSpec, BaseAgent
from aegis_swr.agents.base.code_analyst import CodeAnalystAgent
from aegis_swr.agents.base.log_historian import LogHistorianAgent
from aegis_swr.agents.base.os_kernel import OSKernelAgent
from aegis_swr.agents.base.skeptic import SkepticAgent

__all__ = [
    "AgentCategory",
    "AgentSpec",
    "BaseAgent",
    "OSKernelAgent",
    "CodeAnalystAgent",
    "LogHistorianAgent",
    "SkepticAgent",
]
