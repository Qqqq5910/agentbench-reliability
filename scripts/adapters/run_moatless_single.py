from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one pinned Moatless SWE-bench pilot cell.")
    parser.add_argument("--repo-dir", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    repo_dir = args.repo_dir.resolve()
    flow_path = repo_dir / ".moatless/flows/swebench_tools.json"
    if not flow_path.exists():
        raise SystemExit(f"missing Moatless flow: {flow_path}")

    work_dir = Path(os.environ.get("BENCHTRUST_RUN_DIR", f".benchtrust-moatless/{args.run_id}")).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    flow = json.loads(flow_path.read_text(encoding="utf-8"))
    flow["id"] = f"benchtrust_{args.run_id}".replace(":", "_")
    completion = flow["agent"]["completion_model"]
    completion["model"] = args.model
    completion["reasoning_effort"] = args.reasoning_effort
    completion["temperature"] = None
    completion["model_api_key"] = None
    completion["headers"] = {}
    completion["params"] = {}
    frozen_flow = work_dir / "flow.json"
    frozen_flow.write_text(json.dumps(flow, indent=2), encoding="utf-8")

    sys.path.insert(0, str(repo_dir))
    os.chdir(repo_dir)
    os.environ["MOATLESS_DIR"] = str(work_dir / "moatless")

    from moatless.evaluation.manager import EvaluationManager
    from moatless.flow.manager import FlowManager
    from moatless.runner.docker_runner import DockerRunner
    from moatless.runner.job_wrappers import run_evaluation_instance
    import moatless.settings as settings

    async def run() -> None:
        storage = await settings.get_storage()
        eventbus = await settings.get_event_bus()
        flow_manager = FlowManager(storage=storage, eventbus=eventbus)
        await flow_manager.save_flow(flow)
        runner = DockerRunner(moatless_source_dir=str(repo_dir))
        manager = EvaluationManager(
            runner=runner, storage=storage, eventbus=eventbus, flow_manager=flow_manager
        )
        evaluation = await manager.create_evaluation(
            evaluation_name=args.run_id.replace(":", "_"),
            flow_id=flow["id"],
            model_id="",
            litellm_model_name=args.model,
            instance_ids=[args.instance_id],
            dataset_name="instance_ids",
        )
        success = await runner.start_job(
            project_id=evaluation.evaluation_name,
            trajectory_id=args.instance_id,
            job_func=run_evaluation_instance,
        )
        if not success:
            raise RuntimeError("Moatless Docker runner failed to start")

    asyncio.run(run())


if __name__ == "__main__":
    main()
