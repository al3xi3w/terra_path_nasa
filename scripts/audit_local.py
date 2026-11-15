"""Offline entry point; never calls acquisition commands."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.audit import run_audit

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of',default='2026-11-14',help='Local date for incomplete-month checks')
    args=parser.parse_args()
    run_audit(as_of=args.as_of)
