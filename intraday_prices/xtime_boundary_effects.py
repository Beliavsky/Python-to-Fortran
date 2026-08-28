# TRANSLATION NOTES: heavily simplified. The original buckets intraday
# returns/volume by clock second/minute (`.dt.second`, `.dt.minute`) via
# `.groupby(...).agg(...)` with several aggregators including a lambda
# quantile, builds several report DataFrames (dict[str, DataFrame]),
# prints them with `.to_string(float_format=...)`, and optionally writes
# each to CSV. None of `.dt.second`/`.dt.minute` (reading a field back out
# of a datetime index element), groupby+multi-agg, dict-of-DataFrames, or
# building/writing a new DataFrame are supported by xp2f.py -- its
# datetime index element is otherwise opaque (only read via
# pd.read_csv/.iloc/printing, see dataframe_index_datetime.f90's notes).
#
# What's kept is the same underlying technique -- bucket a value by a
# categorical key and compare a boundary bucket's avg against the rest --
# demonstrated on a bucket key xp2f.py CAN compute: row position modulo N
# (standing in for "minute-of-hour" the way every 12th 5-minute bar stands
# in for the top of the hour), rather than an actual clock field read back
# from the datetime index.
import math

import pandas as pd


def bucket_mean(values, bucket_id, n_buckets):
    """Per-bucket n_in_bucket and avg of `values`, grouped by `bucket_id[i]`
    in [0, n_buckets)."""
    n_in_bucket = [0] * n_buckets
    total = [0.0] * n_buckets
    n = len(values)
    for i in range(n):
        b = bucket_id[i]
        n_in_bucket[b] = n_in_bucket[b] + 1
        total[b] = total[b] + values[i]
    avg = [0.0] * n_buckets
    for b in range(n_buckets):
        if n_in_bucket[b] > 0:
            avg[b] = total[b] / n_in_bucket[b]
    return n_in_bucket, avg


def boundary_vs_other_mean(values, bucket_id, boundary_bucket):
    """Mean of `values` at the boundary bucket vs. all other buckets."""
    boundary_total = 0.0
    boundary_n = 0
    other_total = 0.0
    other_n = 0
    n = len(values)
    for i in range(n):
        if bucket_id[i] == boundary_bucket:
            boundary_total = boundary_total + values[i]
            boundary_n = boundary_n + 1
        else:
            other_total = other_total + values[i]
            other_n = other_n + 1
    boundary_mean = boundary_total / boundary_n if boundary_n > 0 else 0.0
    other_mean = other_total / other_n if other_n > 0 else 0.0
    return boundary_mean, other_mean


def main():
    df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    close = list(df["Close"])
    n = len(close) - 1

    ret_sq = [0.0] * n
    for i in range(n):
        r = math.log(close[i + 1]) - math.log(close[i])
        ret_sq[i] = r * r

    n_buckets = 12
    bucket_id = [0] * n
    for i in range(n):
        bucket_id[i] = i % n_buckets

    n_in_bucket, mean_ret_sq = bucket_mean(ret_sq, bucket_id, n_buckets)
    print("bucket, bars, avg squared return")
    for b in range(n_buckets):
        print(b, n_in_bucket[b], mean_ret_sq[b])

    boundary_mean, other_mean = boundary_vs_other_mean(ret_sq, bucket_id, 0)
    print()
    print("bucket 0 avg squared return:", boundary_mean)
    print("other buckets avg squared return:", other_mean)
    print("ratio:", boundary_mean / other_mean)


if __name__ == "__main__":
    main()
