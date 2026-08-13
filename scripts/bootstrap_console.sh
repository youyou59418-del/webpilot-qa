#!/usr/bin/env bash
set -euo pipefail

# Keep Node project-scoped: AutoDL base images are not assumed to contain Node.
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
node_version="v22.14.0"
node_dir="${project_root}/.tools/node"

if [[ ! -x "${node_dir}/bin/node" ]]; then
  if [[ -e "${node_dir}" ]]; then
    echo "${node_dir} exists but does not contain a usable Node runtime; inspect it before retrying." >&2
    exit 1
  fi
  archive="/tmp/webpilot-node-${node_version}.tar.xz"
  curl -fsSL "https://nodejs.org/dist/${node_version}/node-${node_version}-linux-x64.tar.xz" -o "${archive}"
  mkdir -p "${project_root}/.tools"
  tar -xJf "${archive}" -C "${project_root}/.tools"
  mv "${project_root}/.tools/node-${node_version}-linux-x64" "${node_dir}"
  rm -f "${archive}"
fi

export PATH="${node_dir}/bin:${PATH}"
npm --prefix "${project_root}/console" ci --no-audit --no-fund
npm --prefix "${project_root}/console" run typecheck
