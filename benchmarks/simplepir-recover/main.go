// SimplePIR/DoublePIR decode (Recover) time: runs the authors' full flow pir.RunPIR (real hint,
// query, answer, recover + correctness check) on 2^33 x 1-bit entries, unmodified; RunPIR prints
// the time of each phase. Usage: go run . simple|double REPS
package main

import (
	"os"
	"strconv"

	"github.com/ahenzinger/simplepir/pir"
)

func main() {
	var pi pir.PIR = &pir.SimplePIR{}
	if os.Args[1] == "double" {
		pi = &pir.DoublePIR{}
	}
	reps, _ := strconv.Atoi(os.Args[2])
	N, d := uint64(1)<<33, uint64(1)
	p := pi.PickParams(N, d, 1<<10, 32) // SEC_PARAM and LOGQ of their pir_test.go
	DB := pir.MakeRandomDB(N, d, &p)
	for r := 0; r < reps; r++ {
		pir.RunPIR(pi, DB, p, []uint64{0}) // index 0, as in their benchmarks
	}
}
