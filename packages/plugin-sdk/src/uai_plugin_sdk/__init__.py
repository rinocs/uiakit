"""Trusted plugin SDK, independent of FastAPI, HTTP clients and database adapters."""
from .manifest import (PluginManifest, PluginDependency, Compatibility,
                       PluginPermissions, NetworkPermissions, resolve_manifests)
from .plugin import Plugin, PluginRegistrar, PluginHealth
from .skills import Skill, SkillLoader

__all__ = ['Plugin', 'PluginRegistrar', 'PluginHealth', 'PluginManifest', 'PluginDependency',
           'Compatibility', 'PluginPermissions', 'NetworkPermissions', 'resolve_manifests',
           'Skill', 'SkillLoader']
