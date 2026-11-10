#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

"""Freeze selected capabilities and prepare one harness phase's Agent workspace."""

import argparse
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile
from urllib.parse import quote

import yaml

from assemble_workflow import context_path, load_yaml, validate_context

# Keep machine-readable responses separate from diagnostic logs.
RESULT_LOGGER = logging.getLogger(__name__ + ".result")
RESULT_LOGGER.setLevel(logging.INFO)
RESULT_LOGGER.propagate = False
_RESULT_HANDLER = logging.StreamHandler(sys.stdout)
_RESULT_HANDLER.setFormatter(logging.Formatter("%(message)s"))
RESULT_LOGGER.addHandler(_RESULT_HANDLER)

PREFIX = "ops-direct-invoke-"
SKILL_DIRS = {"codex": ".agents/skills", "opencode": ".agents/skills",
              "cannbot": ".agents/skills", "claude": ".claude/skills",
              "dsh": ".dsh/skills", "pi": ".pi/skills", "trae": ".trae/skills",
              "trae-cn": ".trae-cn/skills", "codearts": ".codeartsdoer/skills"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"refusing to replace a symlink: {path}")
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as output:
        temporary = Path(output.name)
        try:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
        except BaseException:
            temporary.unlink()
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def metadata(directory):
    text = (Path(directory) / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---(?:\n|$)", text, re.S)
    data = yaml.safe_load(match.group(1)) if match else None
    if not isinstance(data, dict) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(data.get("name", ""))):
        raise ValueError(f"invalid Skill metadata: {directory}")
    return data


def digest(directory):
    result = hashlib.sha256()
    for path in sorted(Path(directory).rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if not path.is_file():
            continue
        result.update(str(path.relative_to(directory)).encode())
        result.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                result.update(chunk)
    return result.hexdigest()


def copy_resources(source, destination):
    # Dereference links: a running workflow must not follow subsequent source updates.
    shutil.copytree(source, destination, symlinks=False,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))


def relocate_text(root, old, new):
    """Relocate installer-generated absolute references in a private frozen copy."""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            if b"\0" in stream.read(8192):
                continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        if old in text:
            path.write_text(text.replace(old, new), encoding="utf-8")


def select_custom(root, config, language, engineering):
    root = Path(root) / "skills/custom-skills"
    platform, repo = config["platform"], config["repo"]
    if platform not in {"ascend", "kirin"} or repo not in {"cannbench", "common"}:
        raise ValueError("unsupported repository or platform")
    if repo == "cannbench" and platform != "ascend":
        raise ValueError("cannbench supports Ascend only; use the common repository guide for Kirin")
    languages = read_json(root / "env-check" / platform / "platform.json")["languages"]
    if language not in languages:
        raise ValueError(f"{platform} does not support language {language}")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", engineering):
        raise ValueError("invalid engineering selection")
    support = read_json(root / "engineering" / engineering / "support.json")
    if platform not in support["platforms"] or language not in support["languages"]:
        raise ValueError(f"engineering {engineering} does not support {platform}/{language}")
    selected = {"requirement": root / "requirement" / platform,
                "repo-guide": root / "repo-guide" / repo,
                "env-check": root / "env-check" / platform / language,
                "doc-templates": root / "doc-templates" / platform / language,
                "engineering": root / "engineering" / engineering}
    for name, source in selected.items():
        if metadata(source)["name"] != PREFIX + name:
            raise ValueError(f"Skill name mismatch: {source}")
    return selected


def skill_closure(names, available):
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        raise ValueError("phase skills must be a list of Skill names")
    selected, visiting = {}, set()

    def visit(name):
        if name in visiting:
            raise ValueError(f"cyclic Skill dependency: {name}")
        if name in selected:
            return
        if name not in available:
            raise ValueError(f"required Skill is not available in this selection: {name}")
        visiting.add(name)
        source = Path(available[name])
        data = metadata(source)
        if data["name"] != name:
            raise ValueError(f"registered Skill name mismatch: {source}")
        required = (data.get("metadata") or {}).get("required_skills", [])
        if not isinstance(required, list) or any(not isinstance(n, str) for n in required):
            raise ValueError(f"invalid required_skills: {source}")
        for dependency in required:
            visit(dependency)
        visiting.remove(name)
        selected[name] = source

    for name in names:
        visit(name)
    return selected


def phase_skills(declaration, selection):
    names = declaration.get("skills")
    if not isinstance(names, list):
        raise ValueError("phase has no declared skill set")
    names = list(names)
    variants = declaration.get("skills_by_platform")
    if variants is not None:
        platform = selection["platform"]
        if not isinstance(variants, dict) or platform not in variants:
            raise ValueError(f"task does not support platform {platform}")
        if not isinstance(variants[platform], list):
            raise ValueError("platform skills must be a list")
        names.extend(variants[platform])
    return names


def register_snapshot_skills(stage, final, source, selected, overrides):
    available = {PREFIX + name: str(final / "plugin" / path.relative_to(source))
                 for name, path in selected.items()}
    for name, override in overrides.items():
        if name not in {PREFIX + "requirement", PREFIX + "repo-guide"}:
            raise ValueError(f"unsupported Skill override: {name}")
        if metadata(override)["name"] != name:
            raise ValueError(f"override name mismatch: {name}")
        copy_resources(Path(override), stage / "overrides" / name)
        available[name] = str(final / "overrides" / name)
    for path in sorted((stage / "external-skills").iterdir()):
        if not (path / "SKILL.md").is_file():
            continue
        name = metadata(path)["name"]
        if name in available:
            raise ValueError(f"duplicate Skill name: {name}")
        available[name] = str(final / "external-skills" / path.name)
    return available


def register_performance_skills(stage, final, registry):
    perf_registry = read_json(stage / "performance" / registry)
    perf_skills = {}
    for record in perf_registry.get("plugins", []):
        if record.get("plugin") != "ops-perf-optimize":
            continue
        for relative in record.get("skills", []):
            path = stage / "performance" / relative
            if not path.resolve().is_relative_to((stage / "performance").resolve()):
                raise ValueError("performance Skill path escapes installed workspace")
            name = metadata(path)["name"]
            perf_skills[name] = str(final / "performance" / relative)
    if "ops-perf-optimize-workflow" not in perf_skills:
        raise ValueError("performance workflow is not completely installed")
    return perf_skills


def validate_preparation(config, work, task, provider):
    if config.get("schema_version") != 1:
        raise ValueError("unsupported initialization configuration; run init first")
    if not task.strip():
        raise ValueError("task must describe the confirmed task kind")
    provider = provider or config["tool"]
    if provider not in SKILL_DIRS:
        raise ValueError(f"unsupported client: {provider}")
    if provider != config["tool"]:
        raise ValueError(f"client {provider} differs from initialized client {config['tool']}; "
                         "run init with the target client first")
    if any(os.path.lexists(work / name) for name in ["context.json", ".context", ".workflow/status.json"]):
        raise ValueError("run already exists; resume its frozen context or choose a new directory")
    return provider


def prepare(config_path, work, language, task, engineering, code_dir, provider=None):
    config = read_json(config_path)
    work = Path(work).resolve()
    provider = validate_preparation(config, work, task, provider)
    source = Path(config["asset_root"]).resolve(strict=True)
    selected = select_custom(source, config, language, engineering)
    external = Path(config["external_skills_root"]).resolve(strict=True)
    performance = Path(config["performance_root"]).resolve(strict=True)
    work.mkdir(parents=True, exist_ok=True)
    final = work / ".context"
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=work) as temporary:
        stage = Path(temporary)
        plugin = stage / "plugin"
        for relative in ["agents", "docs", "orchestrations", "tools", "skills/custom-skills"]:
            copy_resources(source / relative, plugin / relative)
        copy_resources(external, stage / "external-skills")
        copy_resources(performance, stage / "performance")
        relocate_text(stage / "performance", str(performance), str(final / "performance"))
        overrides = config.get("skill_overrides", {})
        available = register_snapshot_skills(stage, final, source, selected, overrides)
        registry = Path(config["performance_registry"]).relative_to(performance)
        perf_skills = register_performance_skills(stage, final, registry)
        # Only the public entry is selectable by an outer task. Its complete
        # installation is mounted when that task executes the delegated workflow.
        available["ops-perf-optimize-workflow"] = perf_skills["ops-perf-optimize-workflow"]
        local_available = {name: path.replace(str(final), str(stage), 1)
                           for name, path in available.items()}
        skill_closure([PREFIX + name for name in selected], local_available)
        snapshot_names = ["plugin", "external-skills", "performance"] + (["overrides"] if overrides else [])
        context = {"schema_version": 1, "plugin": "ops-direct-invoke", "work_dir": str(work), "provider": provider,
                   "selection": {key: config[key] for key in ["repo", "platform", "chip", "preferences"]},
                   "code_dir": str(Path(code_dir).resolve()),
                   "project_root": str(Path(config_path).resolve().parent.parent),
                   "plugin_root": str(final / "plugin"),
                   "performance_root": str(final / "performance"),
                   "performance_skills": perf_skills, "skills": available,
                   "sources": {"plugin": str(source), "external-skills": str(external),
                               "performance": str(performance)},
                   "digests": {name: digest(stage / name) for name in snapshot_names}}
        context["selection"].update(language=language, task=task, engineering=engineering)
        # No user file is replaced. Publication is complete before context.json
        # becomes visible to the launcher.
        final.mkdir()
        for name in snapshot_names:
            os.rename(stage / name, final / name)
        write_json(work / "context.json", context)
    return context


def load_context(work, verify=True):
    work = Path(work).resolve()
    context = read_json(work / "context.json")
    if (context.get("schema_version") != 1 or context.get("plugin") != "ops-direct-invoke"
            or context.get("work_dir") != str(work)):
        raise ValueError("context belongs to another workflow; do not move an existing run")
    if context.get("plugin_root") != str(work / ".context/plugin"):
        raise ValueError("plugin root must be this run's frozen resource directory")
    if verify:
        for name, expected in context["digests"].items():
            path = work / ".context" / name
            if not path.is_dir() or digest(path) != expected:
                raise ValueError(f"frozen resources changed or missing: {path}")
    return context


def phase_identity(context, role, skills):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", role):
        raise ValueError(f"invalid role: {role}")
    identity = Path(context["plugin_root"]) / "agents" / (role + ".md")
    if role == "perf-optimize" and "ops-perf-optimize-workflow" in skills:
        identity = Path(context["performance_root"]) / ".cannbot/plugins/ops-perf-optimize/AGENTS.md"
    if not identity.is_file():
        raise ValueError(f"identity not in frozen resources: {role}")
    return identity


def validate_node_context(node, binding, task_id, sidecar, context, platforms):
    validate_context({"context": binding}, sidecar)
    for phase in ["execute", "verify"]:
        declaration = binding.get(phase, {})
        variants = declaration.get("skills_by_platform")
        if isinstance(variants, dict) and set(variants) - platforms:
            unknown = sorted(set(variants) - platforms)
            raise ValueError(f"unknown Skill platforms for {task_id}/{phase}: {unknown}")
        names = phase_skills(declaration, context["selection"])
        skills = skill_closure(names, context["skills"])
        role = node["executor" if phase == "execute" else "verifier"]
        phase_identity(context, role, skills)


def freeze_graph_inputs(path, workflow, graphs):
    if path.exists():
        previous = read_json(path)
        if previous["workflow"] != str(Path(workflow).resolve()):
            raise ValueError("resume must use the original workflow file")
        for name, expected in previous["graphs"].items():
            if graphs.get(name) != expected:
                raise ValueError(f"frozen workflow changed or missing: {name}")
    write_json(path, {"workflow": str(Path(workflow).resolve()), "graphs": graphs})


def validate_graph_context(workflow, work, context):
    """Validate capabilities before scheduling; freeze already materialized inputs."""
    work = Path(work).resolve()
    graphs, nodes, bindings, visiting = {}, {}, {}, set()
    platform_root = Path(context["plugin_root"]) / "skills/custom-skills/env-check"
    platforms = {path.parent.name for path in platform_root.glob("*/platform.json")}

    def visit_subgraph(node, task_id):
        child = (work / node["file"]).resolve()
        if not child.is_relative_to(work):
            raise ValueError(f"subgraph path escapes workflow: {child}")
        if child.exists():
            visit(child, task_id + "/")

    def visit(path, prefix=""):
        path = path.resolve(strict=True)
        if path in visiting:
            raise ValueError(f"recursive workflow file: {path}")
        visiting.add(path)
        data = load_yaml(path)
        sidecar = context_path(path)
        if not sidecar.is_file():
            raise ValueError(f"workflow context file missing: {sidecar}; assemble the workflow first")
        declarations = load_yaml(sidecar)
        normal_ids = {node["id"] for node in data["nodes"] if node.get("task_type") != "subgraph"}
        if not isinstance(declarations, dict) or set(declarations) != normal_ids:
            raise ValueError(f"workflow context must declare every normal node: {sidecar}")
        for source in (path, sidecar):
            graphs[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
        for node in data["nodes"]:
            task_id = prefix + node["id"]
            if node.get("task_type") == "subgraph":
                visit_subgraph(node, task_id)
                continue
            nodes[task_id] = node
            bindings[task_id] = declarations[node["id"]]
            validate_node_context(node, bindings[task_id], task_id, sidecar, context, platforms)
        visiting.remove(path)

    path = work / "run-inputs.json"
    with (work / ".context/inputs.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        visit(Path(workflow))
        for point in context["selection"]["preferences"].get("review_points", []):
            by_id = point in nodes and nodes[point].get("require_approval")
            by_prompt = any(isinstance(node.get("require_approval"), list)
                            and point in node["require_approval"] for node in nodes.values())
            if not by_id and not by_prompt:
                raise ValueError(f"requested review point is not bound to require_approval: {point}")
        freeze_graph_inputs(path, workflow, graphs)
    return bindings


def owned_directory(path):
    """Do not follow a user-created alias while constructing writable contexts."""
    path = Path(path).absolute()
    if path.resolve() != path:
        raise ValueError(f"phase directory must not traverse a symlink: {path}")
    path.mkdir(parents=True, exist_ok=True)


def link(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.is_symlink() and destination.resolve() == source.resolve():
        return
    if os.path.lexists(destination):
        raise ValueError(f"refusing to replace phase workspace file: {destination}")
    owned_directory(destination.parent)
    destination.symlink_to(source)


def mount_performance_configuration(perf, cwd):
    for path in perf.iterdir():
        if path.name not in {".agents", ".opencode", ".claude", ".codex", ".dsh",
                             ".trae", ".trae-cn", ".codeartsdoer"}:
            continue
        # Configuration must stay phase-local; skills themselves remain frozen.
        destination = cwd / path.name
        if destination.is_symlink():
            raise ValueError(f"phase configuration must be a private directory: {destination}")
        if not destination.exists():
            shutil.copytree(path, destination, ignore=shutil.ignore_patterns("skills"))
            relocate_text(destination, str(perf), str(cwd))
        if (path / "skills").is_dir():
            for skill in (path / "skills").iterdir():
                link(skill, destination / "skills" / skill.name)


def mount_performance_state(perf, cwd):
    # Generated configuration and runtime output are writable phase state;
    # installed dependencies and plugin resources continue to use the snapshot.
    state = cwd / ".cannbot"
    owned_directory(state)
    if not (perf / ".cannbot").is_dir():
        return
    for path in (perf / ".cannbot").iterdir():
        destination = state / path.name
        if path.name in {"plugins", "dependencies"}:
            link(path, destination)
            continue
        if os.path.lexists(destination):
            continue
        if path.is_dir():
            shutil.copytree(path, destination)
            relocate_text(destination, str(perf), str(cwd))
        else:
            shutil.copy2(path, destination)
            relocate_text(state, str(perf), str(cwd))


def mount_performance(perf, cwd):
    # Mount the original isolated installation, including dependency hooks
    # and configuration. Its own internal scheduling remains a black box.
    mount_performance_configuration(perf, cwd)
    mount_performance_state(perf, cwd)
    for path in perf.iterdir():
        if path.name not in {"AGENTS.md", "CLAUDE.md", ".cannbot"} and not os.path.lexists(cwd / path.name):
            link(path, cwd / path.name)


def link_phase_skills(cwd, skills, provider, identity, role):
    skill_dir = cwd / SKILL_DIRS[provider]
    for skill_name, source in skills.items():
        destination = skill_dir / skill_name
        link(source, destination)
    if provider == "claude":
        link(identity, cwd / "CLAUDE.md")
    if provider in {"opencode", "cannbot", "claude"}:
        client_dir = ".claude" if provider == "claude" else ".opencode"
        agent_file = cwd / client_dir / "agents" / (role + ".md")
        if not agent_file.exists():
            link(identity, agent_file)
    return skill_dir


def write_phase_context(cwd, envelope, skill_dir, prompt):
    manifest = cwd / "context.json"
    if manifest.exists() and read_json(manifest) != envelope:
        raise ValueError("phase bindings changed; use the original frozen run")
    write_json(manifest, envelope)
    env = envelope["env"]
    exports = "\n".join(f"export {key}={shlex.quote(value)}" for key, value in env.items() if key != "PWD")
    envelope["prompt"] = (f"当前阶段工作目录：{cwd}\n身份文件：{envelope['identity']}\n"
                          f"只使用本阶段技能目录：{skill_dir}\n共享路径（新 shell 沿用）：\n{exports}\n\n"
                          + prompt)
    return envelope


def prepare_phase(entry, work, context=None):
    work = Path(work).resolve()
    context = context or load_context(work)
    phase = entry["_phase"]
    if phase not in {"execute", "verify", "advice"}:
        raise ValueError(f"unknown harness phase: {phase}")
    task_id = entry["task_id"]
    if not isinstance(task_id, str) or not task_id or task_id in {".", ".."}:
        raise ValueError("invalid task id")
    name = "verifier" if phase == "verify" else phase
    cwd = work / "agents" / quote(task_id, safe="") / name
    role = entry["agent"] if phase != "advice" else "ops-direct-invoke-architect"
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", role):
        raise ValueError("invalid role name")
    inputs = read_json(work / "run-inputs.json")
    bindings = validate_graph_context(inputs["workflow"], work, context)
    if phase == "advice":
        names = []
    else:
        if task_id not in bindings:
            raise ValueError(f"task has no declared phase context: {task_id}")
        names = phase_skills(bindings[task_id].get(phase, {}), context["selection"])
    skills = skill_closure(names, context["skills"])
    identity = phase_identity(context, role, skills)
    delegated = "ops-perf-optimize-workflow" in skills
    if delegated:
        skills.update({name: Path(path) for name, path in context["performance_skills"].items()})
    owned_directory(cwd)
    link(identity, cwd / "AGENTS.md")
    if delegated:
        mount_performance(Path(context["performance_root"]), cwd)
    skill_dir = link_phase_skills(cwd, skills, context["provider"], identity, role)
    env = {"WORK_DIR": str(work), "CODE_DIR": context["code_dir"], "PWD": str(cwd),
           "PROJECT_ROOT": context["project_root"],
           "USER_PROMPT": str(work / ".workflow/user_prompt.md"),
           "OPS_DIRECT_INVOKE_ROOT": str(Path(context["plugin_root"])),
           "DOC_TEMPLATES_DIR": context["skills"][PREFIX + "doc-templates"],
           "HARNESS_SKILL_DIR": context["skills"]["workflow-orchestrator"]}
    envelope = {"task_id": task_id, "phase": phase, "role": role, "cwd": str(cwd),
                "identity": str(identity), "skills": {n: str(p) for n, p in skills.items()}, "env": env}
    return write_phase_context(cwd, envelope, skill_dir, entry["prompt"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--engineering", required=True)
    parser.add_argument("--code-dir", type=Path, required=True)
    parser.add_argument("--provider")
    args = parser.parse_args()
    try:
        context = prepare(args.config, args.work_dir, args.language, args.task,
                          args.engineering, args.code_dir, args.provider)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        parser.error(str(error))
    result = {"context": str(Path(context["work_dir"]) / "context.json"),
              "plugin_root": context["plugin_root"]}
    RESULT_LOGGER.info("%s", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
