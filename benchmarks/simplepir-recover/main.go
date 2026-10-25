// SimplePIR/DoublePIR decode (Recover) time: runs the authors' full flow pir.RunPIR (real hint,
// query, answer, recover + correctness check), unmodified; RunPIR prints the time of each phase.
// Default 2^33 x 1-bit entries; optionally 2^LOG_N entries of D bits.
// Usage: go run . simple|double REPS [LOG_N D]
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
	if len(os.Args) == 5 {
		logN, _ := strconv.Atoi(os.Args[3])
		dd, _ := strconv.Atoi(os.Args[4])
		N, d = uint64(1)<<logN, uint64(dd)
	}
	p := pi.PickParams(N, d, 1<<10, 32) // SEC_PARAM and LOGQ of their pir_test.go
	DB := pir.MakeRandomDB(N, d, &p)
	for r := 0; r < reps; r++ {
		pir.RunPIR(pi, DB, p, []uint64{0}) // index 0, as in their benchmarks
	}
}
