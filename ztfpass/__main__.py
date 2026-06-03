"""Run the passthrough: `python -m ztfpass` or the `ztfpass` console script."""

from __future__ import annotations

import argparse

import uvicorn


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ZTF scheduler passthrough service")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=4000)
    p.add_argument(
        "--config", default=None, help="path to config.yaml (else $ZTFPASS_CONFIG)"
    )
    args = p.parse_args(argv)

    import os

    if args.config:
        os.environ["ZTFPASS_CONFIG"] = args.config
    # Import after env is set so settings load from the right file.
    from .app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
