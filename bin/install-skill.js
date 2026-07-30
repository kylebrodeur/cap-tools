#!/usr/bin/env node
"use strict";

/**
 * Installs agentskills.io-compliant skills from this repo's skills/ directory
 * into a target agent's real skills directory.
 *
 * Usage:
 *   npx github:kylebrodeur/cap-tools <skill-name> --target <codex|claude|cursor> [--dry-run]
 *   npx github:kylebrodeur/cap-tools --all --target <codex|claude|cursor> [--dry-run]
 *   npx github:kylebrodeur/cap-tools --list
 *
 * Target path convention mirrors CapSoftware/Cap's own `cap agents install`
 * (apps/cli/src/agents.rs, skill_path()):
 *   codex  -> $CODEX_HOME (default ~/.codex)/skills/<name>/
 *   claude -> ~/.claude/skills/<name>/
 *   cursor -> ~/.cursor/skills/<name>/
 */

const fs = require("fs");
const path = require("path");
const os = require("os");

const REPO_ROOT = path.join(__dirname, "..");
const SKILLS_DIR = path.join(REPO_ROOT, "skills");

function fail(message) {
  console.error(`✗ ${message}`);
  process.exit(1);
}

function parseArgs(argv) {
  const args = { target: null, dryRun: false, all: false, list: false, skillName: null };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--target") {
      args.target = argv[++i];
    } else if (arg === "--dry-run") {
      args.dryRun = true;
    } else if (arg === "--all") {
      args.all = true;
    } else if (arg === "--list") {
      args.list = true;
    } else if (arg === "--help" || arg === "-h") {
      args.help = true;
    } else {
      rest.push(arg);
    }
  }
  if (rest.length > 0) args.skillName = rest[0];
  return args;
}

function printUsage() {
  console.log(`Usage:
  npx github:kylebrodeur/cap-tools <skill-name> --target <codex|claude|cursor> [--dry-run]
  npx github:kylebrodeur/cap-tools --all --target <codex|claude|cursor> [--dry-run]
  npx github:kylebrodeur/cap-tools --list

Options:
  --target <agent>   Required (unless --list). One of: codex, claude, cursor.
  --dry-run          Show what would be installed without writing anything.
  --all              Install every skill found under skills/, not just one.
  --list             List discovered skills and exit (no --target needed).
`);
}

// --- Minimal frontmatter parsing (no YAML dependency by design, so this
// stays a fast, zero-dependency npx script). Only extracts the flat
// key: value pairs this validation needs (name, description) — nested
// maps like `metadata:` are intentionally not parsed here.
function parseFrontmatter(skillMdPath) {
  const content = fs.readFileSync(skillMdPath, "utf8");
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match) return null;
  const block = match[1];
  const fields = {};
  for (const line of block.split(/\r?\n/)) {
    const kv = line.match(/^([a-zA-Z0-9_-]+):\s*(.*)$/);
    if (kv && !line.startsWith(" ")) {
      fields[kv[1]] = kv[2].trim();
    }
  }
  return fields;
}

function discoverSkills() {
  if (!fs.existsSync(SKILLS_DIR)) return [];
  const entries = fs.readdirSync(SKILLS_DIR, { withFileTypes: true });
  const skills = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const skillDir = path.join(SKILLS_DIR, entry.name);
    const skillMd = path.join(skillDir, "SKILL.md");
    if (!fs.existsSync(skillMd)) continue;
    const frontmatter = parseFrontmatter(skillMd);
    const issues = [];
    if (!frontmatter) {
      issues.push("no valid YAML frontmatter found (missing --- delimiters)");
    } else {
      if (!frontmatter.name) issues.push("missing required 'name' field");
      if (!frontmatter.description) issues.push("missing required 'description' field");
      if (frontmatter.name && frontmatter.name !== entry.name) {
        issues.push(
          `'name: ${frontmatter.name}' does not match directory name '${entry.name}' (required by agentskills.io spec)`
        );
      }
    }
    skills.push({ name: entry.name, dir: skillDir, frontmatter, issues });
  }
  return skills;
}

function targetSkillsRoot(target) {
  const home = os.homedir();
  switch (target) {
    case "codex":
      return path.join(process.env.CODEX_HOME || path.join(home, ".codex"), "skills");
    case "claude":
      return path.join(home, ".claude", "skills");
    case "cursor":
      return path.join(home, ".cursor", "skills");
    default:
      return null;
  }
}

function copyDirRecursive(src, dest, { dryRun, plan }) {
  const entries = fs.readdirSync(src, { withFileTypes: true });
  if (!dryRun) fs.mkdirSync(dest, { recursive: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDirRecursive(srcPath, destPath, { dryRun, plan });
    } else {
      plan.push(destPath);
      if (!dryRun) {
        fs.copyFileSync(srcPath, destPath);
        // Preserve executable bit — several skills ship setup.sh/agent.sh
        // that must stay runnable after install.
        const mode = fs.statSync(srcPath).mode;
        fs.chmodSync(destPath, mode);
      }
    }
  }
}

function installSkill(skill, target, dryRun) {
  const root = targetSkillsRoot(target);
  const destDir = path.join(root, skill.name);
  const plan = [];
  copyDirRecursive(skill.dir, destDir, { dryRun, plan });
  return { destDir, plan };
}

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.help) {
    printUsage();
    process.exit(0);
  }

  const skills = discoverSkills();

  if (args.list) {
    if (skills.length === 0) {
      console.log("No skills found under skills/.");
      return;
    }
    console.log(`Found ${skills.length} skill(s):\n`);
    for (const skill of skills) {
      const status = skill.issues.length === 0 ? "✓" : "⚠";
      console.log(`  ${status} ${skill.name}`);
      if (skill.frontmatter && skill.frontmatter.description) {
        console.log(`      ${skill.frontmatter.description}`);
      }
      for (const issue of skill.issues) {
        console.log(`      ⚠ ${issue}`);
      }
    }
    return;
  }

  if (!args.target) {
    printUsage();
    fail("--target is required (codex, claude, or cursor)");
  }
  if (!["codex", "claude", "cursor"].includes(args.target)) {
    fail(`Unknown target '${args.target}' — must be one of: codex, claude, cursor`);
  }
  if (!args.all && !args.skillName) {
    printUsage();
    fail("Specify a skill name, or pass --all to install every skill found");
  }
  if (skills.length === 0) {
    fail(`No skills found under ${SKILLS_DIR}`);
  }

  let toInstall;
  if (args.all) {
    toInstall = skills;
  } else {
    const found = skills.find((s) => s.name === args.skillName);
    if (!found) {
      const names = skills.map((s) => s.name).join(", ");
      fail(`Skill '${args.skillName}' not found. Available: ${names}`);
    }
    toInstall = [found];
  }

  const blocking = toInstall.filter((s) => s.issues.length > 0 && (!s.frontmatter || !s.frontmatter.name || !s.frontmatter.description));
  if (blocking.length > 0) {
    for (const skill of blocking) {
      console.error(`✗ ${skill.name}: ${skill.issues.join("; ")}`);
    }
    fail("Refusing to install skill(s) missing required frontmatter fields.");
  }

  console.log(`${args.dryRun ? "[dry-run] " : ""}Installing to target: ${args.target}\n`);

  for (const skill of toInstall) {
    if (skill.issues.length > 0) {
      console.log(`⚠ ${skill.name}: ${skill.issues.join("; ")} (installing anyway — not blocking)`);
    }
    const { destDir, plan } = installSkill(skill, args.target, args.dryRun);
    console.log(`${args.dryRun ? "Would install" : "Installed"} '${skill.name}' -> ${destDir}`);
    for (const file of plan) {
      console.log(`    ${path.relative(destDir, file) === "" ? file : path.relative(path.dirname(destDir), file)}`);
    }
  }

  if (args.dryRun) {
    console.log("\nDry run only — nothing was written. Re-run without --dry-run to apply.");
  } else {
    console.log("\nDone.");
  }
}

main();
