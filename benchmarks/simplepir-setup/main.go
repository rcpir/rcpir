// SimplePIR/DoublePIR hint (Setup) time with the authors' code, unmodified: the timed section of
// their pir.RunPIR (pi.Init untimed, then pi.Setup timed, GC off as in RunPIR), without query, answer
// and recover, so no client ever holds the hint. Same output lines as RunPIR ("Setup...", "Elapsed:",
// "Offline download:"), plus the peak RSS of the process at the end.
// Usage: go run . simple|double REPS LOG_N D
package main

import (
	"fmt"
	"os"
	"runtime"
	"runtime/debug"
	"strconv"
	"strings"
	"time"

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
	debug.SetGCPercent(-1) // as in RunPIR
	for r := 0; r < reps; r++ {
		fmt.Printf("Executing %s\n", pi.Name())
		shared := pi.Init(DB.Info, p)
		fmt.Println("Setup...")
		start := time.Now()
		_, hint := pi.Setup(DB, shared, p)
		fmt.Printf("\tElapsed: %v\n", time.Since(start))
		fmt.Printf("\t\tOffline download: %f KB\n", float64(hint.Size()*uint64(p.Logq)/(8.0*1024.0)))
		pi.Reset(DB, p) // Setup squishes DB; RunPIR resets it the same way
		runtime.GC()
	}
	if status, err := os.ReadFile("/proc/self/status"); err == nil {
		for _, line := range strings.Split(string(status), "\n") {
			if strings.HasPrefix(line, "VmHWM:") {
				fmt.Println("Peak RSS:", strings.Join(strings.Fields(line)[1:], " "))
			}
		}
	}
}
