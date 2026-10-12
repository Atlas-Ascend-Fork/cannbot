// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import { existsSync, realpathSync, statSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";

export const SHARED_SKILLS_PATH = "vendor/cannbot-skills";

export function isInside(root, path) {
  const pathFromRoot = relative(root, path);
  return pathFromRoot === "" || (!pathFromRoot.startsWith("..") && !isAbsolute(pathFromRoot));
}

export function gitOutput(repository, args) {
  const result = spawnSync("git", ["-C", repository, ...args], { encoding: "utf8" });
  return result.status === 0 ? result.stdout.trim() : null;
}

export function gitCommit(repository, revision = "HEAD") {
  return gitOutput(repository, ["rev-parse", "--verify", `${revision}^{commit}`]);
}

function isRepositoryRoot(repository) {
  if (!existsSync(repository) || !statSync(repository).isDirectory()) return false;
  const top = gitOutput(repository, ["rev-parse", "--show-toplevel"]);
  return top !== null && realpathSync(top) === realpathSync(repository);
}

function runGit(repository, args) {
  const result = spawnSync("git", ["-C", repository, ...args], { stdio: ["ignore", 2, 2] });
  if (result.error || result.status !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${result.error?.message ?? result.status}`);
  }
}

export function usesSharedSkills(repositoryRoot, definition) {
  if (!definition) return false;
  const root = resolve(repositoryRoot, definition.skillsRepository);
  const shared = resolve(repositoryRoot, SHARED_SKILLS_PATH);
  return definition.skills.some((skill) => typeof skill === "string" && isInside(shared, resolve(root, skill)));
}

export function resolveSkillSource(repositoryRoot, definition, skill, sharedRoot) {
  if (typeof skill !== "string" || !skill) throw new Error(`invalid Skill path in ${definition.definitionPath}`);
  const root = resolve(repositoryRoot, definition.skillsRepository);
  let source = resolve(root, skill);
  if (!isInside(root, source)) throw new Error(`Skill path escapes its repository root: ${skill}`);
  const shared = resolve(repositoryRoot, SHARED_SKILLS_PATH);
  if (sharedRoot && isInside(shared, source)) source = resolve(sharedRoot, relative(shared, source));
  if (!existsSync(resolve(source, "SKILL.md"))) throw new Error(`skill is missing SKILL.md: ${source}`);
  return source;
}

export function prepareSharedSkills(repositoryRoot, definition, requested) {
  if (!usesSharedSkills(repositoryRoot, definition)) {
    if (requested !== undefined) throw new Error("--skills requires a source plugin that declares cannbot-skills dependencies");
    return null;
  }
  if (requested !== undefined) {
    const local = resolve(requested);
    if (requested && existsSync(local)) {
      if (!isRepositoryRoot(local)) throw new Error(`--skills path must be a Git repository root: ${local}`);
      const commit = gitCommit(local);
      if (!commit) throw new Error(`--skills path has no checked-out commit: ${local}`);
      return { root: realpathSync(local), selection: "local-path", requested, commit,
        dirty: gitOutput(local, ["status", "--porcelain"]) !== "" };
    }
    if (!/^(?:[0-9a-f]{7,40}|[0-9a-f]{64})$/i.test(requested)) {
      throw new Error("--skills must be an existing local repository path or a Git SHA");
    }
  }
  const shared = resolve(repositoryRoot, SHARED_SKILLS_PATH);
  if (!isRepositoryRoot(shared)) {
    runGit(repositoryRoot, ["submodule", "update", "--init", "--depth", "1", SHARED_SKILLS_PATH]);
  }
  if (!isRepositoryRoot(shared)) throw new Error(`${SHARED_SKILLS_PATH} is not a Git repository root`);
  if (gitOutput(shared, ["status", "--porcelain"]) !== "") {
    throw new Error(`${SHARED_SKILLS_PATH} has uncommitted changes; commit, stash, or use --skills <path>`);
  }
  let commit;
  let branch;
  if (requested === undefined) {
    branch = gitOutput(repositoryRoot, ["branch", "--show-current"]) || "master";
    if (branch !== "master") {
      const remote = spawnSync("git", ["-C", shared, "ls-remote", "--exit-code", "--heads", "origin", `refs/heads/${branch}`],
        { encoding: "utf8" });
      if (remote.status === 2) branch = "master";
      else if (remote.error || remote.status !== 0) {
        throw new Error(`could not query cannbot-skills branch ${branch}: ${remote.error?.message ?? remote.stderr.trim()}`);
      }
    }
    runGit(shared, ["fetch", "--depth", "1", "origin", `refs/heads/${branch}`]);
    commit = gitCommit(shared, "FETCH_HEAD");
  } else {
    commit = gitCommit(shared, requested);
    if (!commit) {
      if (![40, 64].includes(requested.length)) {
        throw new Error("a short SHA must already exist locally; use a full SHA to fetch a missing commit");
      }
      runGit(shared, ["fetch", "--depth", "1", "origin", requested]);
      commit = gitCommit(shared, requested);
    }
  }
  if (!commit) throw new Error(`could not resolve cannbot-skills commit: ${requested ?? branch}`);
  runGit(shared, ["checkout", "--detach", commit]);
  runGit(shared, ["submodule", "update", "--init", "--recursive", "--depth", "1"]);
  return { root: shared, selection: requested === undefined ? "latest-branch" : "sha",
    requested: requested ?? branch, commit, dirty: false };
}

export function sourceRevisions(repositoryRoot, shared) {
  return {
    cannbot: gitCommit(repositoryRoot),
    ...(shared ? { "cannbot-skills": {
      selection: shared.selection, requested: shared.requested, commit: shared.commit, dirty: shared.dirty,
      ...(shared.selection === "local-path" ? { path: shared.root } : {}),
    } } : {}),
  };
}
