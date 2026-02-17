# Traverse: SWE Harbor Take-Home Assignment

## Codebase Landscape

This repository is a fork of [Verifiers](https://github.com/PrimeIntellect-ai/verifiers), a framework by Prime Intellect for training and evaluating AI coding agents with reinforcement learning. The top-level structure:

```
take-home/
├── verifiers/              # The core Verifiers framework (library code — don't modify)
│   ├── envs/               # Built-in environment types (SingleTurnEnv, HarborEnv, etc.)
│   ├── rubrics/            # Reward/scoring infrastructure
│   ├── rl/                 # Reinforcement learning trainers
│   └── ...
├── environments/
│   └── swe_harbor/         # ← YOUR WORKING DIRECTORY
│       ├── swe_harbor.py   # Environment class that loads and runs tasks
│       ├── pyproject.toml  # Project config and dependencies
│       ├── RUBRIC.md       # How your work will be evaluated
│       └── tasks/          # ← Where you create tasks
│           ├── _template/              # Starter template to copy
│           ├── implement-linked-list/  # Example: greenfield implementation
│           ├── fix-flask-api/          # Example: debug existing code
│           └── implement-text-stats/   # Example: text analysis task
└── README.md               # ← You are here
```

You only need to work inside `environments/swe_harbor/tasks/`. Everything else is supporting infrastructure.

## The Environment

**SweHarborEnv** (`environments/swe_harbor/swe_harbor.py`) is a Harbor-format environment that evaluates AI coding agents. Here's what happens when a task runs:

1. The framework reads `task.toml` to get the Docker image and timeout settings.
2. It builds and starts a Docker container from `environment/Dockerfile`.
3. The task instruction (`instruction.md`) is mounted at `/task/instruction.md` inside the container.
4. A tool-use agent script is uploaded into the container. The agent has four tools: `bash`, `read_file`, `write_file`, and `str_replace`. It reads the instruction and works to solve the task.
5. When the agent finishes (or times out), `tests/test.sh` runs inside the container.
6. The test runner executes `test_solution.py` with pytest and writes a reward — `1` (all tests pass) or `0` (any test fails) — to `/logs/verifier/reward.txt`.

The agent never sees the tests. It only sees `instruction.md`.

## Your Task

Create **1-2 original software engineering tasks** in Harbor format. Place each task in its own directory under `environments/swe_harbor/tasks/`.

Each task directory must contain these files:

| File | Purpose |
|------|---------|
| `task.toml` | Task metadata — difficulty level, timeouts, Docker image |
| `instruction.md` | The problem statement the agent sees |
| `environment/Dockerfile` | Sets up the Docker container (and any starter code) |
| `solution/solve.sh` | Reference solution — a bash script that produces the correct answer |
| `tests/test_solution.py` | Pytest test cases that verify correctness |
| `tests/test.sh` | Test runner that executes pytest and writes the reward file |

**Requirements:**

1. The reference solution (`solve.sh`) must pass all tests (reward = 1)
2. Tests must **fail** without the solution applied (reward = 0)
3. Tests should catch incorrect or incomplete solutions, not just the happy path
4. At least one task should involve **multiple files**

See [`environments/swe_harbor/RUBRIC.md`](environments/swe_harbor/RUBRIC.md) for the full evaluation criteria.

### Getting Started

1. **Study the examples** — `environments/swe_harbor/tasks/implement-linked-list/` (greenfield), `environments/swe_harbor/tasks/fix-flask-api/` (debugging), and `environments/swe_harbor/tasks/implement-text-stats/` (text analysis)
2. **Copy the template** — `cp -r environments/swe_harbor/tasks/_template environments/swe_harbor/tasks/your-task-name`
3. **Fill in each file** — follow the TODO comments in the template
4. **Test locally** — verify your task end-to-end with Docker (see below)

### Task Design Guidelines

**Good task types:**

| Type | Example |
|------|---------|
| Debug existing code | Plant realistic bugs in a working app |
| Implement from a spec | Give interface requirements, agent writes the code |
| Build a small tool | CLI tool with argument parsing, file I/O, output formatting |
| Fix broken config/setup | Wrong dependency versions, misconfigured server |
| Refactor for correctness | Code with subtle edge-case bugs |

**Avoid:**

- Leetcode/competitive programming puzzles
- Tasks requiring internet access (containers are isolated)
- Subjective tasks with no deterministic pass/fail
- Trivially passable tests
- Overly broad scope ("build a web app")

**Scope:** A skilled engineer should be able to solve each task in 15-45 minutes.

## Running the Environment

### Prerequisites

- **Docker** — must be installed and running
- **`OPENROUTER_API_KEY`** — only needed for full framework runs (not Docker-only quick verification). Copy `.env.example` to `.env` and fill in your key:
  ```bash
  cp environments/swe_harbor/.env.example environments/swe_harbor/.env
  # then edit .env with your OpenRouter API key
  ```

### Quick Verification (Docker Only)

The fastest way to test a task. Run these commands from the `environments/swe_harbor/` directory.

```bash
cd environments/swe_harbor
```

**Step 1: Build the Docker image**

```bash
docker build -t my-task tasks/my-task-name/environment/
```

**Step 2: Run with your solution (expect reward = `1`)**

```bash
docker run --rm \
    -v $(pwd)/tasks/my-task-name/solution:/solution \
    -v $(pwd)/tasks/my-task-name/tests:/tests \
    my-task \
    bash -c "mkdir -p /logs/verifier && cd /app && bash /solution/solve.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

**Step 3: Run without your solution (expect reward = `0`)**

```bash
docker run --rm \
    -v $(pwd)/tasks/my-task-name/tests:/tests \
    my-task \
    bash -c "mkdir -p /logs/verifier && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

If Step 2 prints `1` and Step 3 prints `0`, your task works correctly. If both print `1`, your tests aren't actually checking the solution.

**Concrete example** using the included `implement-text-stats` task:

```bash
# Build
docker build -t text-stats tasks/implement-text-stats/environment/

# With solution (should print 1)
docker run --rm \
    -v $(pwd)/tasks/implement-text-stats/solution:/solution \
    -v $(pwd)/tasks/implement-text-stats/tests:/tests \
    text-stats \
    bash -c "mkdir -p /logs/verifier && cd /app && bash /solution/solve.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"

# Without solution (should print 0)
docker run --rm \
    -v $(pwd)/tasks/implement-text-stats/tests:/tests \
    text-stats \
    bash -c "mkdir -p /logs/verifier && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

### Full Framework Run (Optional)

To run tasks through the full Verifiers pipeline with an actual AI agent, you need additional setup.

**Install dependencies:**

```bash
# From the repo root
uv add verifiers
prime env install swe_harbor --path ./environments/swe_harbor
```

**Run an evaluation:**

```bash
prime eval run swe_harbor -m gpt-4
```

This spins up the full agent loop: the model reads `instruction.md`, uses its tools to solve the task, and then tests are run automatically. You need a configured API endpoint (see `configs/endpoints.toml` at the repo root).

## Harbor Format Reference

### `task.toml`

```toml
version = "1.0"

[metadata]
author_name = "Your Name"
author_email = "you@example.com"
difficulty = "easy"        # easy | medium | hard
category = "programming"
tags = ["python", "data-structures"]

[verifier]
timeout_sec = 120.0        # Max time for test execution

[agent]
timeout_sec = 300.0        # Max time for the agent to work

[environment]
docker_image = "python:3.11-slim"
```

### `instruction.md`

The problem statement the agent receives. Be specific about:

- What files to create or modify
- Expected function signatures, class interfaces, or CLI behavior
- Input/output examples where helpful
- Constraints or requirements

### `environment/Dockerfile`

Sets up the Docker container. For greenfield tasks:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
```

For tasks with pre-existing code, COPY files into the image:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install flask
COPY app/ /app/
```

### `solution/solve.sh`

A bash script that produces the correct solution. Runs inside the container at `/app`. It can write files (using heredocs), apply patches (with `sed` or `patch`), or run commands. Must be deterministic and pass all tests.

### `tests/test.sh`

Entry point for test execution. Standard pattern:

```bash
#!/bin/bash
cd /app
pip install pytest > /dev/null 2>&1
mkdir -p /logs/verifier
pytest /tests/test_solution.py -v 2>&1
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```

Must write `1` (pass) or `0` (fail) to `/logs/verifier/reward.txt`.

### `tests/test_solution.py`

Standard pytest test file. Test the happy path, edge cases, and error conditions. Keep tests independent with no shared mutable state.
