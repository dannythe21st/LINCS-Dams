import "math"

option task = {name: "displacements", every: 5s}

from(bucket: "telegraf")
    |> range(start: -task.every)
    |> filter(fn: (r) => r["_measurement"] == "I1")
    |> filter(fn: (r) => int(v: r.n) > 0)
    |> filter(fn: (r) => r["_field"] == "aX")
    |> group(columns: ["_time"], mode: "by")
    // Data processing
    // new column with level of sensor (spacing of 0.5m and level=0 at sensor 1 (bottom))
    |> map(fn: (r) => ({r with n: r.n, level: 2.0 - 0.5 * float(v: r["n"])}))
    // new column with displacement calculated from angle
    |> map(fn: (r) => ({r with _value: r._value, dX: 0.5 * math.sin(x: r._value / 180.0 * math.pi)}))
    |> map(fn: (r) => ({r with dX: r.dX, cummulative_dX: r.dX}))
    |> sort(columns: ["level"], desc: false)
    |> cumulativeSum(columns: ["cummulative_dX"])
    |> to(
        bucket: "results",
        org: "lnec-ascendi",
        fieldFn: (r) => ({"level": r.level, "dX": r.dX, "cummulative_dX": r.cummulative_dX}),
    )

from(bucket: "telegraf")
    |> range(start: -task.every)
    |> filter(fn: (r) => r["_measurement"] == "I1")
    |> filter(fn: (r) => int(v: r.n) > 0)
    |> filter(fn: (r) => r["_field"] == "aY")
    |> group(columns: ["_time"], mode: "by")
    // Data processing
    // new column with level of sensor (spacing of 0.5m and level=0 at sensor 1 (bottom))
    |> map(fn: (r) => ({r with n: r.n, level: 2.0 - 0.5 * float(v: r["n"])}))
    // new column with displacement calculated from angle
    |> map(fn: (r) => ({r with _value: r._value, dY: 0.5 * math.sin(x: r._value / 180.0 * math.pi)}))
    |> map(fn: (r) => ({r with dY: r.dY, cummulative_dY: r.dY}))
    |> sort(columns: ["level"], desc: false)
    |> cumulativeSum(columns: ["cummulative_dY"])
    |> to(
        bucket: "results",
        org: "lnec-ascendi",
        fieldFn: (r) => ({"level": r.level, "dY": r.dY, "cummulative_dY": r.cummulative_dY}),
    )