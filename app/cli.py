from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Brain Gym active-reading app")
    parser.add_argument("--mode", choices=["live", "offline", "review", "mixed"], default="live")
    parser.add_argument("--url", help="URL to fetch and read")
    parser.add_argument("--youtube", help="YouTube video URL to transcribe")
    parser.add_argument("--file", help="Path to a local article file")
    parser.add_argument("--text", help="Pasted article text")
    parser.add_argument("--questions", type=int, default=5, help="Questions per round")
    parser.add_argument("--rounds", type=int, default=3, help="Maximum offline rounds")
    parser.add_argument("--target-score", type=float, default=4.5, help="Target score for a live answer to count as strong")
    parser.add_argument("--max-retries", type=int, default=2, help="Maximum retries per question")
    parser.add_argument("--model", help="Generation model override")
    parser.add_argument("--grade-model", help="Grading model override")
    return parser
