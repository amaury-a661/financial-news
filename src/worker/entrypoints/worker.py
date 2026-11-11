import asyncio

import mistralai.workflows as workflows

workflow_classes = workflows.discover_all_workflows_in_package("worker.workflows")


async def main() -> None:
    await workflows.run_worker(workflow_classes)


if __name__ == "__main__":
    asyncio.run(main())
