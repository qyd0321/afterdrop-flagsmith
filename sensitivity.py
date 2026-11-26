"""Run a secondary paired latency/interruption sweep over real local HTTP."""

import argparse
import csv
import itertools
import random
from pathlib import Path

from upload_lab import KIB, receiver, transmit


def run(path):
    cases = list(itertools.product((6, 35, 90), (0, 20, 70), range(4)))
    random.Random(314159).shuffle(cases)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as output, receiver() as server:
        writer = None
        for delay, cut, repetition in cases:
            identity = f"sweep-{delay}-{cut}-{repetition}"
            arms = ("whole", "resume") if repetition % 2 == 0 else ("resume", "whole")
            profile = (512 * KIB, 600 * KIB, delay / 1000, cut / 100 if cut else None)
            for arm in arms:
                row = transmit(server, identity, "sensitivity", arm, link_profile=profile)
                row.update(request_delay_ms=delay, disconnect_percent=cut, repetition=repetition)
                if writer is None:
                    writer = csv.DictWriter(output, fieldnames=row.keys())
                    writer.writeheader()
                writer.writerow(row)
                output.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new CSV path")
    run(parser.parse_args().output)
