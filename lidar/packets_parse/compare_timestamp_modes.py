#!/usr/bin/env python3
"""Compare timestamp CSVs by nearest frame end within a bounded alignment window.

Alignment is inferred, not a packet-identity proof. Review unmatched frames and
use the same source recording, range, calibration and invalid-point policy.
"""
import argparse
import csv
import json
from pathlib import Path
import statistics


def load_csv(path):
    with open(path) as stream:
        rows = [dict(frame_idx=int(r['frame_idx']), first=float(r['first_point_ts']),
                     last=float(r['last_point_ts']), points=int(r['point_count']),
                     partial=bool(int(r.get('partial', '0')))) for r in csv.DictReader(stream)]
    if not rows:
        raise ValueError(f'empty timestamp CSV: {path}')
    return rows


def describe(rows):
    gaps = [b['first'] - a['last'] for a,b in zip(rows,rows[1:])]
    return dict(frames=len(rows), partial_frames=sum(r['partial'] for r in rows),
                regressions=sum(gap < 0 for gap in gaps),
                reversed_frame_endpoints=sum(r['last'] < r['first'] for r in rows),
                min_boundary_gap_us=min(gaps)*1e6 if gaps else None,
                max_boundary_gap_us=max(gaps)*1e6 if gaps else None,
                mean_duration_ms=statistics.mean((r['last']-r['first'])*1000 for r in rows))


def compare(reference, candidate, tolerance_ms):
    remaining = set(range(len(candidate)))
    matched = []
    for row in reference:
        possible = [i for i in remaining if not row['partial'] and not candidate[i]['partial']
                    and row['points'] == candidate[i]['points']
                    and abs(row['last']-candidate[i]['last'])*1000 <= tolerance_ms]
        if len(possible) != 1:
            continue  # Ambiguous or absent match must not become a confident comparison.
        index = possible[0]; remaining.remove(index)
        other = candidate[index]
        matched.append(dict(reference_frame=row['frame_idx'], candidate_frame=other['frame_idx'],
                            first_delta_ms=(other['first']-row['first'])*1000,
                            last_delta_ms=(other['last']-row['last'])*1000))
    return dict(reference=describe(reference), candidate=describe(candidate), matched=matched,
                unmatched_reference=len(reference)-len(matched), unmatched_candidate=len(remaining),
                alignment='inferred from end timestamp and equal point count; not packet identity')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path)
    parser.add_argument('candidates',nargs='+',type=Path)
    parser.add_argument('--max-alignment-ms',type=float,default=50)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.max_alignment_ms <= 0: parser.error('alignment tolerance must be positive')
    try:
        reference=load_csv(args.reference)
        report={str(path):compare(reference,load_csv(path),args.max_alignment_ms) for path in args.candidates}
        rendered=json.dumps(report,indent=2,allow_nan=False)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(rendered+'\n')
    except (OSError,ValueError,KeyError) as error:
        parser.exit(1,f'error: {error}\n')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
