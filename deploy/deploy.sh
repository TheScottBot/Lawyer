#!/usr/bin/env bash
# Phased install and update of Lawyer in the homelab container.
#
# Run as root. With no arguments every phase runs in order; name phases to run
# only those, in the order given, for example after an update:
#   bash deploy.sh code dependencies start
# Every phase can be run again safely. A phase that needs something from the
# operator (the token, the built rulebooks) stops and says what, without printing
# any secret, and the run can resume from that phase.

set -euo pipefail

readonly INSTALL_DIRECTORY=/opt/Lawyer
readonly REPOSITORY_URL=https://github.com/TheScottBot/Lawyer.git
readonly SERVICE_NAME=lawyer
readonly SERVICE_USER=lawyer
readonly UNIT_FILE=deploy/lawyer.service
readonly LOCK_FILE=deploy/requirements-debian13-x86_64-py313.txt
# The lock's compiled wheels fit exactly this platform and no other.
readonly EXPECTED_MACHINE=x86_64
readonly EXPECTED_PYTHON_MINOR=3.13

readonly PHASES=(packages user code dependencies settings rules service start)

declare -A PHASE_DESCRIPTIONS=(
    [packages]="install git and python3-venv"
    [user]="create the lawyer system user"
    [code]="clone the repository, or fast forward an existing checkout"
    [dependencies]="create the virtual environment and install the hashed lock"
    [settings]="create .env from the example, keep the settings database in data/, check the token is set"
    [rules]="create rules/, data/ and logs/ and check the built rulebooks are present"
    [service]="install and enable the systemd unit"
    [start]="restart the service and show its status"
)

print_usage() {
    echo "Usage: bash deploy.sh [phase ...]"
    echo
    echo "Phases, run in this order when none are named:"
    for phase_name in "${PHASES[@]}"; do
        printf '  %-13s %s\n' "${phase_name}" "${PHASE_DESCRIPTIONS[${phase_name}]}"
    done
}

stop_with() {
    echo "deploy: $1" >&2
    exit 1
}

phase_packages() {
    apt-get install --yes git python3-venv
}

phase_user() {
    if id -u "${SERVICE_USER}" > /dev/null 2>&1; then
        echo "user ${SERVICE_USER} already exists"
        return
    fi
    useradd --system --home-dir "${INSTALL_DIRECTORY}" --shell /usr/sbin/nologin "${SERVICE_USER}"
}

phase_code() {
    if [[ -d "${INSTALL_DIRECTORY}/.git" ]]; then
        # Fast forward only: local edits on the host are never merged or discarded.
        git -C "${INSTALL_DIRECTORY}" pull --ff-only
    elif [[ -e "${INSTALL_DIRECTORY}" ]]; then
        stop_with "${INSTALL_DIRECTORY} exists but is not a git checkout; move it aside first"
    else
        git clone "${REPOSITORY_URL}" "${INSTALL_DIRECTORY}"
    fi
}

phase_dependencies() {
    local machine_name python_minor
    machine_name="$(uname -m)"
    python_minor="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    if [[ "${machine_name}" != "${EXPECTED_MACHINE}" || "${python_minor}" != "${EXPECTED_PYTHON_MINOR}" ]]; then
        stop_with "the lock is for ${EXPECTED_MACHINE} with Python ${EXPECTED_PYTHON_MINOR}; this host is ${machine_name} with Python ${python_minor}"
    fi
    if [[ ! -x "${INSTALL_DIRECTORY}/.venv/bin/python" ]]; then
        python3 -m venv "${INSTALL_DIRECTORY}/.venv"
    fi
    "${INSTALL_DIRECTORY}/.venv/bin/python" -m pip install --require-hashes --only-binary=:all: --no-deps \
        -r "${INSTALL_DIRECTORY}/${LOCK_FILE}"
}

phase_settings() {
    local env_file="${INSTALL_DIRECTORY}/.env"
    if [[ ! -f "${env_file}" ]]; then
        cp "${INSTALL_DIRECTORY}/.env.example" "${env_file}"
        echo "created ${env_file} from .env.example"
    fi
    # The service can only write data/ and logs/, so the settings database lives in data/.
    if ! grep --quiet '^DB_PATH=' "${env_file}"; then
        echo "DB_PATH=data/lawyer.db" >> "${env_file}"
        echo "set DB_PATH=data/lawyer.db in ${env_file}"
    fi
    # The service may read the token but not change it; nobody else may read it.
    chown "root:${SERVICE_USER}" "${env_file}"
    chmod 640 "${env_file}"
    if ! grep --quiet '^DISCORD_TOKEN=..*' "${env_file}" || grep --quiet '^DISCORD_TOKEN=your-bot-token-here' "${env_file}"; then
        stop_with "set DISCORD_TOKEN in ${env_file}, then run: bash deploy.sh settings rules service start"
    fi
    echo "DISCORD_TOKEN is set in ${env_file}"
}

phase_rules() {
    mkdir -p "${INSTALL_DIRECTORY}/rules" "${INSTALL_DIRECTORY}/data" "${INSTALL_DIRECTORY}/logs"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIRECTORY}/data" "${INSTALL_DIRECTORY}/logs"
    # The rulebooks are built from the PDFs on another machine; only what's built comes here.
    if ! compgen -G "${INSTALL_DIRECTORY}/rules/*.json" > /dev/null; then
        stop_with "copy the built rulebooks (rules/*.json) to ${INSTALL_DIRECTORY}/rules/, then run: bash deploy.sh rules service start"
    fi
    chmod 644 "${INSTALL_DIRECTORY}"/rules/*.json
    echo "rulebooks present: $(cd "${INSTALL_DIRECTORY}/rules" && ls -- *.json | tr '\n' ' ')"
}

phase_service() {
    install --mode=644 "${INSTALL_DIRECTORY}/${UNIT_FILE}" "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
}

phase_start() {
    systemctl restart "${SERVICE_NAME}"
    systemctl --no-pager status "${SERVICE_NAME}" || true
    echo "follow the log with: journalctl -u ${SERVICE_NAME} -f"
}

main() {
    if [[ "${1:-}" == "help" ]]; then
        print_usage
        return 0
    fi

    local requested_phases=("$@")
    if [[ ${#requested_phases[@]} -eq 0 ]]; then
        requested_phases=("${PHASES[@]}")
    fi
    # Every name is checked before any phase runs, so a typo changes nothing.
    for phase_name in "${requested_phases[@]}"; do
        if [[ -z "${PHASE_DESCRIPTIONS[${phase_name}]+known}" ]]; then
            echo "deploy: unknown phase: ${phase_name}" >&2
            print_usage >&2
            exit 2
        fi
    done

    if [[ "$(id -u)" -ne 0 ]]; then
        stop_with "run as root"
    fi

    for phase_name in "${requested_phases[@]}"; do
        echo "== ${phase_name}: ${PHASE_DESCRIPTIONS[${phase_name}]}"
        "phase_${phase_name}"
    done
    echo "== done"
}

main "$@"
