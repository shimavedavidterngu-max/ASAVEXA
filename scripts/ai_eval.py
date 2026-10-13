"""Runs the assistant evaluation on the built-in labelled sample and prints the report. Exit code 1 if the criteria are not met.

    PYTHONPATH=src:tests python3 scripts/ai_eval.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "tests")]

from asavexa.ai import evaluation  # noqa: E402
from test_ai import engine, rich_world  # noqa: E402
from test_ai_evaluation import QUESTIONS, labels  # noqa: E402

w = rich_world()
result = evaluation.run_evaluation(engine(w), labels(w), QUESTIONS)
print(evaluation.format_report(result))
sys.exit(0 if result["meets_criteria"] else 1)
