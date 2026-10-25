// SimplePIR/DoublePIR decode (Recover) time: runs the authors' full flow pir.RunPIR (real hint,
// query, answer, recover + correctness check), unmodified, on 2^LOG_N entries of D bits; RunPIR
// prints the time of each phase. Usage: go run . simple|double REPS LOG_N D
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
	logN, _ := strconv.Atoi(os.Args[3])
	d, _ := strconv.Atoi(os.Args[4])
	N := uint64(1) << logN
	p := pi.PickParams(N, uint64(d), 1<<10, 32) // SEC_PARAM and LOGQ of their pir_test.go
	DB := pir.MakeRandomDB(N, uint64(d), &p)
	for r := 0; r < reps; r++ {
		pir.RunPIR(pi, DB, p, []uint64{0}) // index 0, as in their benchmarks
	}
}
